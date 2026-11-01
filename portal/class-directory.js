(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const stages = [
        { name: "Introductorio", courses: ["CI-1", "CI-2"] },
        { name: "Filosofía", courses: ["1F-1", "1F-2", "2F-3", "2F-4", "3F-5", "3F-6"] },
        { name: "Teología", courses: ["1T-1", "1T-2", "2T-3", "2T-4", "3T-5", "3T-6", "4T-7", "4T-8"] }
    ];
    const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
    let profile, verify, opened = false, generation = 0, controller, snapshot, periodId = null, selected = null, busy = false;

    function node(tag, text, className) {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (className) element.className = className;
        return element;
    }
    function button(label, action, className = "back-link") {
        const element = node("button", label, className);
        element.type = "button";
        element.addEventListener("click", action);
        return element;
    }
    function status(text, error = false) {
        $("classDirectoryStatus").textContent = text;
        $("classDirectoryStatus").className = "control-message" + (error ? " error" : "");
    }
    function sync() {
        $("classDirectory").setAttribute("aria-busy", String(busy));
        for (const id of ["classDirectoryPeriod", "classDirectorySearch", "classDirectoryInactive", "classDirectoryAll", "classDirectoryCreate"])
            $(id).disabled = busy || !snapshot?.period_id;
        $("classDirectoryRefresh").disabled = busy;
    }
    function leave() {
        generation++;
        controller?.abort();
        controller = snapshot = undefined;
        opened = busy = false;
        $("classDirectory").hidden = true;
        $("classDirectoryGroups").replaceChildren();
        $("classDirectoryList").replaceChildren();
        $("classDirectoryPeriod").replaceChildren();
        $("classDirectoryCount").textContent = "";
        $("classDirectoryListTitle").textContent = "Elige un curso para ver sus clases";
        status("");
        sync();
    }
    function clear() {
        leave();
        profile = verify = undefined;
        periodId = selected = null;
        $("classDirectorySearch").value = "";
        $("classDirectoryInactive").checked = false;
    }
    async function load(period, notice = "") {
        if (!profile || !opened) return;
        const operation = ++generation;
        controller?.abort();
        controller = new AbortController();
        busy = true;
        snapshot = undefined;
        $("classDirectoryList").replaceChildren();
        $("classDirectoryGroups").replaceChildren();
        $("classDirectoryCount").textContent = "";
        status("Cargando clases del periodo…");
        sync();
        try {
            // La misma lectura completa que usa Materias y periodos, sin límite de 30/50 clases.
            const data = await window.PortalCourseOrganizer.readSnapshot(period, controller.signal);
            if (!opened || operation !== generation) return;
            snapshot = data;
            periodId = data.period_id;
            $("classDirectoryPeriod").replaceChildren(...data.periods.map(p => new Option(p.name, p.id)));
            $("classDirectoryPeriod").value = periodId || "";
            render();
            status(notice || (periodId ? "Elige un curso y después la clase. Desde ahí puedes inscribir alumnos o asignar profesores." : "Todavía no hay periodos académicos. Agrega uno en Materias y periodos."));
            if (notice) $("classDirectoryListTitle").focus({ preventScroll: true });
        } catch (error) {
            if (!opened || operation !== generation) return;
            if (error?.code === "42501" || [401, 403].includes(error?.status)) {
                const callback = verify;
                clear();
                if (callback) void callback();
                return;
            }
            status("No se pudieron cargar las clases. Pulsa Actualizar para reintentar.", true);
        } finally {
            if (operation === generation) {
                busy = false;
                sync();
            }
        }
    }
    function selectCourse(code) {
        selected = code;
        render();
        $("classDirectoryListTitle").focus({ preventScroll: true });
        $("classDirectoryResults").scrollIntoView({ block: "start", behavior: "instant" });
    }
    function tile(code, label, rows) {
        const element = button(label, () => selectCourse(code), "class-directory-tile");
        element.dataset.course = code;
        element.setAttribute("aria-pressed", String(selected === code));
        const count = rows.filter(row => (row.group_code || "none") === code).length;
        element.append(node("small", count + (count === 1 ? " clase" : " clases")));
        return element;
    }
    function classAction(action, row) {
        if (!profile || !opened || busy) return;
        const operation = generation;
        const messages = { enroll: "Alumno inscrito en ", assign: "Profesor asignado a ", class_state: "Estado actualizado de " };
        const done = result => {
            if (!opened || operation !== generation) return;
            void load(periodId, result?.notice || messages[action] + row.name + ".");
        };
        if (action === "enroll") window.PortalEnrollmentBatch?.open({ ...row, subject_name: row.name }, done);
        else window.PortalManagement?.openClassAction(action, { ...row, subject_name: row.name }, done);
    }
    function card(row) {
        const item = node("li", undefined, "class-directory-card");
        item.dataset.classId = row.id;
        item.append(node("p", row.group_code || "Sin curso asignado", "class-directory-course"), node("h4", row.name), node("p", row.period_name));
        item.append(node("span", row.active ? "Activa" : "Inactiva", "status-pill" + (row.active ? "" : " inactive")));
        const actions = node("div", undefined, "class-directory-actions");
        const enroll = button("Inscribir alumnos", () => classAction("enroll", row), "back-link control-create");
        const assign = button("Asignar profesor", () => classAction("assign", row));
        enroll.disabled = assign.disabled = !row.active;
        actions.append(enroll, assign);
        if (row.active) {
            const enter = node("a", "Entrar al curso", "class-directory-enter");
            enter.href = "#curso/" + row.id + "/inicio";
            actions.append(enter);
        }
        item.append(actions);
        const more = node("details", undefined, "class-directory-more");
        more.append(node("summary", "Más opciones"));
        const secondary = node("div", undefined, "class-directory-actions");
        secondary.append(button("Curso / semestre", () => window.PortalCourseGroups?.edit(row.id, () => { if (opened) void load(periodId); })),
            button(row.active ? "Desactivar clase" : "Reactivar clase", () => classAction("class_state", row)),
            button("Eliminar clase", () => window.PortalDeletion?.open("class", row.id, () => { if (opened) void load(periodId); })));
        more.append(secondary);
        item.append(more);
        return item;
    }
    function render() {
        if (!snapshot) return;
        const rows = snapshot.classes.filter(row => row.active || $("classDirectoryInactive").checked);
        const groups = $("classDirectoryGroups");
        groups.replaceChildren();
        for (const stage of stages) {
            const section = node("section", undefined, "class-directory-stage");
            section.append(node("h3", stage.name));
            const tiles = node("div", undefined, "class-directory-stage-grid");
            for (const code of stage.courses) tiles.append(tile(code, code, rows));
            section.append(tiles);
            groups.append(section);
        }
        if (snapshot.classes.some(row => row.group_code === null)) groups.append(tile("none", "Sin curso asignado", rows));
        $("classDirectoryAll").setAttribute("aria-pressed", String(selected === "all"));
        const title = $("classDirectoryListTitle"), list = $("classDirectoryList");
        list.replaceChildren();
        title.textContent = selected === null ? "Elige un curso para ver sus clases" : selected === "all" ? "Todas las clases del periodo" : selected === "none" ? "Clases sin curso asignado" : "Clases de " + selected;
        $("classDirectoryCount").textContent = "";
        if (selected === null) return;
        const needle = normalize($("classDirectorySearch").value.trim());
        const matches = rows.filter(row => (selected === "all" || (row.group_code || "none") === selected) && normalize(row.name + " " + (row.group_code || "")).includes(needle)).sort((a, b) => a.name.localeCompare(b.name, "es"));
        $("classDirectoryCount").textContent = matches.length + (matches.length === 1 ? " clase" : " clases");
        list.append(...matches.map(card));
        if (!matches.length) list.append(node("li", needle ? "No hay clases que coincidan con esta búsqueda en el curso seleccionado." : "Este curso todavía no tiene clases activas en el periodo seleccionado. Puedes organizarlas en Materias y periodos o incluir las inactivas.", "class-directory-empty"));
    }
    $("classDirectoryPeriod").addEventListener("change", () => {
        selected = null;
        $("classDirectorySearch").value = "";
        void load($("classDirectoryPeriod").value);
    });
    $("classDirectoryRefresh").addEventListener("click", () => void load(periodId));
    $("classDirectorySearch").addEventListener("input", () => { if (selected === null) selected = "all"; render(); });
    $("classDirectoryInactive").addEventListener("change", render);
    $("classDirectoryAll").addEventListener("click", () => selectCourse("all"));
    $("classDirectoryCreate").addEventListener("click", () => {
        if (busy || !snapshot) return;
        const period = snapshot.periods.find(p => p.id === periodId), operation = generation;
        window.PortalManagement?.createClass(period, data => {
            if (!opened || operation !== generation) return;
            selected = "none";
            void load(data.period_id, "Clase abierta. Usa Más opciones → Curso / semestre para asignarle su bloque.");
        });
    });
    for (const event of ["portal-catalog-changed", "portal-academic-deleted"]) window.addEventListener(event, () => { if (opened && !busy) void load(periodId); });
    window.PortalClassDirectory = Object.freeze({
        clear, leave,
        show(value, check) { clear(); if (value.role === "control_escolar") { profile = value; verify = check; } },
        openRoute() { if (!profile || opened) return; opened = true; $("classDirectory").hidden = false; void load(periodId); }
    });
})();
