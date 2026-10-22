(function () {
    "use strict";

    const section = document.getElementById("teachingSection");
    const link = document.getElementById("teachingLink");
    const status = document.getElementById("teachingStatus");
    const list = document.getElementById("teachingList");
    const retry = document.getElementById("teachingRetry");
    const more = document.getElementById("teachingMore");
    const roster = document.getElementById("rosterSection");
    const rosterTitle = document.getElementById("rosterTitle");
    const rosterPeriod = document.getElementById("rosterPeriod");
    const rosterStatus = document.getElementById("rosterStatus");
    const rosterList = document.getElementById("rosterList");
    const rosterRetry = document.getElementById("rosterRetry");
    const rosterMore = document.getElementById("rosterMore");
    const pageSize = 20;
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    let version = 0;
    let rosterVersion = 0;
    let controller;
    let rosterController;
    let loading = false;
    let rosterLoading = false;
    let offset = 0;
    let rosterOffset = 0;
    let activeCourse;
    let activeButton;
    let recheckAccess;
    const shownStudents = new Set();

    function clearRoster() {
        rosterVersion += 1;
        window.PortalGradeEditor?.clear();
        rosterController?.abort();
        rosterController = undefined;
        rosterLoading = false;
        rosterOffset = 0;
        activeCourse = undefined;
        activeButton = undefined;
        shownStudents.clear();
        roster.hidden = true;
        roster.setAttribute("aria-busy", "false");
        rosterTitle.textContent = "";
        rosterPeriod.textContent = "";
        rosterStatus.textContent = "";
        rosterStatus.className = "teaching-status";
        rosterList.replaceChildren();
        rosterRetry.hidden = true;
        rosterMore.hidden = true;
        for (const button of list.querySelectorAll(".teaching-open")) {
            button.setAttribute("aria-expanded", "false");
        }
    }

    function clear() {
        version += 1;
        controller?.abort();
        controller = undefined;
        loading = false;
        offset = 0;
        recheckAccess = undefined;
        clearRoster();
        section.hidden = true;
        link.hidden = true;
        section.setAttribute("aria-busy", "false");
        list.replaceChildren();
        status.textContent = "";
        status.className = "teaching-status";
        retry.hidden = true;
        more.hidden = true;
    }

    function courseCard(course) {
        if (
            !course || typeof course.id !== "string" || !uuid.test(course.id) ||
            !course.subjects || !course.academic_periods ||
            ![course.subjects.code, course.subjects.name, course.academic_periods.name]
                .every(value => typeof value === "string" && value.trim())
        ) throw new Error("Asignación incompleta");

        const item = document.createElement("li");
        item.className = "teaching-card";
        for (const [tag, className, text] of [
            ["span", "teaching-code", course.subjects.code],
            ["h3", "teaching-name", course.subjects.name],
            ["p", "teaching-period", course.academic_periods.name]
        ]) {
            const element = document.createElement(tag);
            element.className = className;
            element.textContent = text;
            item.append(element);
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "back-link teaching-open";
        button.textContent = "Ver alumnos";
        button.setAttribute("aria-expanded", "false");
        button.setAttribute("aria-controls", "rosterSection");
        button.setAttribute("aria-label", "Ver alumnos de " + course.subjects.name + ", " + course.academic_periods.name);
        button.addEventListener("click", function () {
            if (section.hidden) return;
            clearRoster();
            activeCourse = course;
            activeButton = button;
            button.setAttribute("aria-expanded", "true");
            rosterTitle.textContent = "Alumnos de " + course.subjects.name;
            rosterPeriod.textContent = course.academic_periods.name;
            roster.hidden = false;
            void loadRoster();
            roster.scrollIntoView({ block: "nearest" });
        });
        const enter = document.createElement("button");
        enter.type = "button";
        enter.className = "course-enter";
        enter.textContent = "Entrar al curso";
        enter.setAttribute("aria-label", "Entrar al curso " + course.subjects.name + ", " + course.academic_periods.name);
        enter.addEventListener("click", function () {
            if (section.hidden) return;
            if (window.PortalLearning) window.PortalLearning.openByCard({ code: course.subjects.code, period: course.academic_periods.name });
            else status.textContent = "El aula no está disponible. Recarga la página para reintentar.";
        });
        item.append(enter, button);
        return item;
    }

    async function loadCourses() {
        if (loading || section.hidden) return;
        const operation = version;
        controller = new AbortController();
        loading = true;
        section.setAttribute("aria-busy", "true");
        more.disabled = true;
        retry.hidden = true;
        status.className = "teaching-status";
        status.textContent = offset ? "Cargando más materias…" : "Cargando tus materias asignadas…";
        try {
            const { data, error } = await window.PortalAuth.getClient()
                .from("teaching_assignments")
                .select("id, subjects(code, name), academic_periods(name, starts_on, ends_on)")
                .order("created_at", { ascending: false })
                .order("id", { ascending: true })
                .range(offset, offset + pageSize)
                .abortSignal(controller.signal);
            if (operation !== version || section.hidden) return;
            if (error) throw error;
            if (!Array.isArray(data)) throw new Error("Respuesta de asignaciones inválida");
            const cards = data.slice(0, pageSize).map(courseCard);
            list.append(...cards);
            offset += cards.length;
            more.hidden = data.length <= pageSize;
            status.textContent = offset
                ? offset + (offset === 1 ? " materia asignada mostrada." : " materias asignadas mostradas.")
                : "Todavía no tienes materias asignadas.";
        } catch {
            if (operation !== version || section.hidden) return;
            // Un error puede significar que cambiaron las asignaciones; retirar
            // también el listado de alumnos que hubiera quedado abierto.
            clearRoster();
            status.className = "teaching-status error";
            status.textContent = "No fue posible consultar tus materias asignadas. Comprueba tu conexión y vuelve a intentarlo.";
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

    async function loadRoster() {
        if (rosterLoading || section.hidden || roster.hidden || !activeCourse) return;
        const operation = ++rosterVersion;
        const sessionVersion = version;
        rosterController = new AbortController();
        rosterLoading = true;
        roster.setAttribute("aria-busy", "true");
        rosterMore.disabled = true;
        rosterRetry.hidden = true;
        rosterStatus.className = "teaching-status";
        rosterStatus.textContent = rosterOffset ? "Cargando más alumnos…" : "Cargando alumnos…";
        try {
            // RPC de solo lectura: PostgreSQL vuelve a comprobar que el profesor
            // está activo y tiene esta materia y periodo asignados.
            const { data, error } = await window.PortalAuth.getClient()
                .rpc("get_teaching_roster", {
                    p_assignment_id: activeCourse.id,
                    p_offset: rosterOffset,
                    p_limit: pageSize + 1
                })
                .abortSignal(rosterController.signal);
            if (operation !== rosterVersion || sessionVersion !== version || roster.hidden) return;
            if (error) throw error;
            if (!Array.isArray(data)) throw new Error("Respuesta de alumnos inválida");
            const students = data.slice(0, pageSize);
            const pageIds = new Set();
            const items = students.map(student => {
                if (
                    !student || typeof student.enrollment_id !== "string" || !uuid.test(student.enrollment_id) ||
                    typeof student.student_name !== "string" || !student.student_name.trim() ||
                    shownStudents.has(student.enrollment_id) || pageIds.has(student.enrollment_id)
                ) throw new Error("Alumno inválido");
                pageIds.add(student.enrollment_id);
                const item = document.createElement("li");
                item.className = "roster-row";
                const name = document.createElement("span");
                name.className = "roster-student";
                name.textContent = student.student_name;
                const button = document.createElement("button");
                button.type = "button";
                button.className = "back-link grade-open";
                button.textContent = "Calificar";
                button.setAttribute("aria-label", "Calificar a " + student.student_name);
                button.setAttribute("aria-controls", "gradeEditor");
                const selectedCourse = activeCourse;
                button.addEventListener("click", function () {
                    if (section.hidden || roster.hidden || activeCourse !== selectedCourse) return;
                    if (window.PortalGradeEditor) {
                        window.PortalGradeEditor.open({
                            assignmentId: selectedCourse.id,
                            enrollmentId: student.enrollment_id,
                            studentName: student.student_name,
                            courseName: selectedCourse.subjects.name,
                            recheckAccess
                        });
                    } else {
                        rosterStatus.textContent = "La captura de calificaciones no está disponible. Recarga la página para reintentar.";
                    }
                });
                item.append(name, button);
                return item;
            });
            rosterList.append(...items);
            for (const id of pageIds) shownStudents.add(id);
            rosterOffset += items.length;
            rosterMore.hidden = data.length <= pageSize;
            rosterStatus.textContent = rosterOffset
                ? rosterOffset + (rosterOffset === 1 ? " alumno mostrado." : " alumnos mostrados.")
                : "No hay alumnos activos inscritos en esta materia y periodo.";
        } catch {
            if (operation !== rosterVersion || sessionVersion !== version || roster.hidden) return;
            window.PortalGradeEditor?.clear();
            rosterList.replaceChildren();
            shownStudents.clear();
            rosterOffset = 0;
            rosterStatus.className = "teaching-status error";
            rosterStatus.textContent = "No fue posible consultar la lista de alumnos. Actualiza tus materias y vuelve a abrir la lista.";
            rosterRetry.hidden = false;
            rosterMore.hidden = true;
        } finally {
            if (operation === rosterVersion && sessionVersion === version) {
                rosterLoading = false;
                roster.setAttribute("aria-busy", "false");
                rosterMore.disabled = false;
            }
        }
    }

    function show(verifyAccess) {
        clear();
        recheckAccess = verifyAccess;
        section.hidden = false;
        link.hidden = false;
        void loadCourses();
    }

    retry.addEventListener("click", function () {
        if (!loading && recheckAccess) void recheckAccess();
    });
    more.addEventListener("click", function () { void loadCourses(); });
    rosterRetry.addEventListener("click", function () {
        if (!rosterLoading && recheckAccess) void recheckAccess();
    });
    rosterMore.addEventListener("click", function () { void loadRoster(); });
    document.getElementById("rosterClose").addEventListener("click", function () {
        const button = activeButton;
        clearRoster();
        if (button?.isConnected) button.focus();
    });

    window.PortalTeaching = Object.freeze({ clear, show });
})();
