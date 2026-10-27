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
    const scoreFormat = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 2 });
    let version = 0;
    let controller;
    let offset = 0;
    let loading = false;
    let hasGradeError = false;
    let recheckAccess;

    function clear() {
        version += 1;
        controller?.abort();
        controller = undefined;
        loading = false;
        offset = 0;
        hasGradeError = false;
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
            typeof enrollment.id !== "string" ||
            !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(enrollment.id) ||
            !subject || !period ||
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
        const grade = document.createElement("p");
        grade.className = "subject-grade";
        grade.textContent = "Consultando calificación…";
        item.append(grade);
        const enter = document.createElement("button");
        enter.type = "button";
        enter.className = "course-enter";
        enter.textContent = "Entrar al curso";
        enter.setAttribute("aria-label", "Entrar al curso " + subject.name + ", " + period.name);
        enter.addEventListener("click", function () {
            if (section.hidden) return;
            if (window.PortalLearning) window.PortalLearning.openByCard({ code: subject.code, period: period.name });
            else status.textContent = "El aula no está disponible. Recarga la página para reintentar.";
        });
        item.append(enter);
        return item;
    }

    async function loadGrades(enrollments, cards, operation, signal) {
        if (!enrollments.length) return true;
        const ids = enrollments.map(enrollment => enrollment.id);
        try {
            // La consulta separada conserva las materias si fallan las notas.
            // PostgreSQL solo devuelve las notas publicadas del alumno activo.
            const { data, error } = await window.PortalAuth.getClient()
                .from("enrollment_grades")
                .select("enrollment_id, score")
                .in("enrollment_id", ids)
                .abortSignal(signal);
            if (operation !== version || section.hidden) return null;
            if (error) throw error;
            if (!Array.isArray(data)) throw new Error("Respuesta de calificaciones inválida");
            const grades = new Map();
            for (const grade of data) {
                if (
                    !grade || !ids.includes(grade.enrollment_id) || grades.has(grade.enrollment_id) ||
                    typeof grade.score !== "number" || !Number.isFinite(grade.score) ||
                    grade.score < 0 || grade.score > 100
                ) throw new Error("Calificación inválida");
                grades.set(grade.enrollment_id, grade.score);
            }
            cards.forEach((card, index) => {
                const id = ids[index];
                card.querySelector(".subject-grade").textContent = grades.has(id)
                    ? "Calificación publicada: " + window.PortalGradeScale.format(grades.get(id)) + " / 10"
                    : "Sin calificación publicada";
            });
            return true;
        } catch {
            if (operation !== version || section.hidden) return null;
            cards.forEach(card => {
                const grade = card.querySelector(".subject-grade");
                grade.textContent = "No fue posible consultar la calificación.";
                grade.classList.add("error");
            });
            return false;
        }
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
            const enrollments = data.slice(0, pageSize);
            const cards = enrollments.map(subjectCard);
            list.append(...cards);
            offset += cards.length;
            more.hidden = data.length <= pageSize;
            const gradesLoaded = await loadGrades(enrollments, cards, operation, controller.signal);
            if (operation !== version || section.hidden) return;
            if (gradesLoaded === false) hasGradeError = true;
            status.textContent = offset
                ? offset + (offset === 1 ? " materia mostrada." : " materias mostradas.")
                : "Todavía no tienes materias inscritas.";
            if (hasGradeError) {
                status.textContent += " No fue posible consultar las calificaciones.";
                status.classList.add("error");
                retry.hidden = false;
            }
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
