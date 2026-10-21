(function () {
    "use strict";

    const section = document.getElementById("subjectsSection");
    const link = document.getElementById("subjectsLink");
    const status = document.getElementById("subjectsStatus");
    const list = document.getElementById("subjectsList");
    const retry = document.getElementById("subjectsRetry");
    const more = document.getElementById("subjectsMore");
    const pageSize = 20;
    const dateFormat = new Intl.DateTimeFormat("es-MX", {
        day: "numeric", month: "short", year: "numeric", timeZone: "UTC"
    });
    let version = 0;
    let controller;
    let offset = 0;
    let loading = false;
    let recheckAccess;

    function clear() {
        version += 1;
        controller?.abort();
        controller = undefined;
        loading = false;
        offset = 0;
        recheckAccess = undefined;
        section.hidden = true;
        link.hidden = true;
        section.setAttribute("aria-busy", "false");
        list.replaceChildren();
        status.textContent = "";
        status.className = "subjects-status";
        retry.hidden = true;
        more.hidden = true;
    }

    function subjectCard(enrollment) {
        const subject = enrollment.subjects;
        const period = enrollment.academic_periods;
        if (
            typeof enrollment.id !== "string" || !subject || !period ||
            ![subject.code, subject.name, period.name].every(value => typeof value === "string" && value.trim()) ||
            ![period.starts_on, period.ends_on].every(value =>
                typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
                Number.isFinite(Date.parse(value)))
        ) throw new Error("Inscripción incompleta");

        const item = document.createElement("li");
        item.className = "subject-item";
        for (const [tag, className, text] of [
            ["span", "subject-code", subject.code],
            ["h3", "subject-name", subject.name],
            ["p", "subject-period", period.name],
            ["p", "subject-dates", dateFormat.format(new Date(period.starts_on)) + " – " + dateFormat.format(new Date(period.ends_on))]
        ]) {
            const element = document.createElement(tag);
            element.className = className;
            element.textContent = text;
            item.append(element);
        }
        return item;
    }

    async function loadPage() {
        if (loading || section.hidden) return;
        const operation = ++version;
        controller = new AbortController();
        loading = true;
        section.setAttribute("aria-busy", "true");
        more.disabled = true;
        retry.hidden = true;
        status.className = "subjects-status";
        status.textContent = offset ? "Cargando más materias…" : "Cargando tus materias…";

        try {
            // RLS filtra las inscripciones; la interfaz no decide qué alumno puede leerlas.
            const { data, error } = await window.PortalAuth.getClient()
                .from("enrollments")
                .select("id, subjects(code, name), academic_periods(name, starts_on, ends_on)")
                .order("created_at", { ascending: false })
                .order("id", { ascending: true })
                .range(offset, offset + pageSize)
                .abortSignal(controller.signal);
            if (operation !== version || section.hidden) return;
            if (error) throw error;
            if (!Array.isArray(data)) throw new Error("Respuesta de inscripciones inválida");

            // Validar la página completa antes de mostrarla; sin resultados parciales.
            const cards = data.slice(0, pageSize).map(subjectCard);
            list.append(...cards);
            offset += cards.length;
            more.hidden = data.length <= pageSize;
            status.textContent = offset
                ? offset + (offset === 1 ? " materia mostrada." : " materias mostradas.")
                : "Todavía no tienes materias inscritas.";
        } catch {
            if (operation !== version || section.hidden) return;
            status.className = "subjects-status error";
            status.textContent = offset
                ? "No fue posible cargar más materias. Comprueba tu conexión e inténtalo nuevamente."
                : "No fue posible cargar tus materias. Comprueba tu conexión e inténtalo nuevamente.";
            retry.hidden = false;
            more.hidden = true;
        } finally {
            if (operation === version) {
                loading = false;
                section.setAttribute("aria-busy", "false");
                more.disabled = false;
            }
        }
    }

    function show(verifyAccess) {
        clear();
        recheckAccess = verifyAccess;
        section.hidden = false;
        link.hidden = false;
        void loadPage();
    }

    retry.addEventListener("click", function () {
        if (!loading && recheckAccess) void recheckAccess();
    });
    more.addEventListener("click", function () {
        void loadPage();
    });

    window.PortalSubjects = Object.freeze({ clear, show });
})();
