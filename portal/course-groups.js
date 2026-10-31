(function () {
    "use strict";
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const groupPattern = /^(CI-[12]|[1-3]F-[1-6]|[1-4]T-[1-8])$/;
    const key = (code, period) => JSON.stringify([code, period]);
    let profile, generation = 0, controller, loading, loaded = false, failed = false, dialog;
    let byClass = new Map(), byCard = new Map();
    function repaint() {
        for (const element of document.querySelectorAll("[data-course-subject-code]")) {
            const value = byCard.get(key(element.dataset.courseSubjectCode, element.dataset.coursePeriodName));
            const text = value?.group_code || (failed ? "Curso no disponible" : loaded ? "Curso por asignar" : "Curso");
            if (element.textContent !== text) element.textContent = text;
        }
        window.dispatchEvent(new Event("portal-course-groups-loaded"));
    }
    function bind(element, code, period) {
        if (!element) return;
        element.dataset.courseSubjectCode = code;
        element.dataset.coursePeriodName = period;
        element.textContent = byCard.get(key(code, period))?.group_code || (failed ? "Curso no disponible" : loaded ? "Curso por asignar" : "Curso");
    }
    function clear() {
        generation++; profile = undefined; controller?.abort(); controller = undefined; loading = undefined;
        loaded = failed = false; byClass.clear(); byCard.clear();
        if (dialog) { dialog.remove(); dialog = undefined; }
        // Las pantallas de la sesión anterior se limpian desde panel.js.
    }
    async function reload() {
        if (!profile) return;
        const g = generation; controller?.abort(); controller = new AbortController(); failed = false;
        try {
            const {data, error} = await window.PortalAuth.getClient().rpc("portal_course_groups_read").retry(false).abortSignal(controller.signal);
            if (g !== generation || !profile) return;
            if (error) throw error;
            if (!Array.isArray(data?.items) || data.items.length > 10000 || data.items.some(x =>
                !uuid.test(x.course_id) || typeof x.code !== "string" || typeof x.period_name !== "string" ||
                !groupPattern.test(x.group_code) || !Number.isInteger(x.revision) || x.revision < 1)) throw new Error("Respuesta inválida");
            byClass = new Map(data.items.map(x => [x.course_id,x]));
            byCard = new Map(data.items.map(x => [key(x.code,x.period_name),x]));
            loaded = true;
        } catch { if (g === generation) { failed = true; loaded = false; byClass.clear(); byCard.clear(); } }
        if (g === generation) repaint();
    }
    async function edit(id, changed) {
        if (profile?.role !== "control_escolar" || !uuid.test(id) || dialog) return;
        await loading;
        if (profile?.role !== "control_escolar") return;
        if (!loaded) { await reload(); if (!loaded || !profile) return; }
        const g = generation, current = byClass.get(id);
        const d = document.createElement("dialog"), form = document.createElement("form"), heading = document.createElement("h2");
        dialog = d; d.className = "learning-dialog course-group-dialog"; heading.textContent = "Curso de la clase";
        const label = document.createElement("label"), select = document.createElement("select"), status = document.createElement("p");
        label.textContent = "Etapa y semestre"; select.id = "classFormationCourse"; label.htmlFor = select.id; select.required = true;
        select.append(new Option("Selecciona un curso", ""));
        for (const [stage, count, prefix] of [["Introductorio",2,"CI"],["Filosofía",6,"F"],["Teología",8,"T"]]) {
            for (let n=1;n<=count;n++) { const code = (prefix === "CI" ? "CI" : Math.ceil(n/2)+prefix)+"-"+n; select.append(new Option(code+" · "+stage+" · Semestre "+n,code)); }
        }
        select.value = current?.group_code || ""; status.setAttribute("role","status");
        const info = document.createElement("p");
        info.textContent = "Clasifica esta clase sin cambiar las inscripciones, notas ni el semestre registrado de los alumnos.";
        if (current?.planned_professor) { const p = document.createElement("p"); p.textContent = "Docente previsto en el Excel: "+current.planned_professor; form.append(p); }
        const save = document.createElement("button"), cancel = document.createElement("button");
        save.type = "submit"; save.textContent = "Guardar curso"; save.className = "learning-button";
        cancel.type = "button"; cancel.textContent = "Cancelar"; cancel.className = "learning-button secondary";
        let busy = false;
        function close() { if (busy) return; d.close(); d.remove(); if (dialog===d) dialog = undefined; }
        cancel.addEventListener("click",close); d.addEventListener("cancel",e=>{e.preventDefault();close();});
        form.append(heading,info,label,select,status,save,cancel);d.append(form);document.body.append(d);d.showModal();select.focus();
        form.addEventListener("submit", async event => {
            event.preventDefault(); if (busy || !select.reportValidity()) return;
            busy = true; save.disabled = cancel.disabled = select.disabled = true;
            try {
                const {data,error} = await window.PortalAuth.getClient().rpc("portal_course_group_save",{p_course:id,p_group:select.value,p_revision:current?.revision||0}).retry(false);
                if (g !== generation || dialog !== d) return;
                if (error) throw error;
                if (data?.saved !== true) throw new Error("Guardado sin confirmar");
                busy = false; close(); await reload(); if (g === generation) changed?.();
            } catch(error) {
                if (g !== generation || dialog !== d) return;
                status.textContent = ["22023","PT409","42501"].includes(error?.code) ? error.message : "No se confirmó la respuesta. Cierra y actualiza antes de volver a guardar.";
                busy = false; cancel.disabled = false; // Una operación incierta no se reenvía desde el mismo diálogo.
            }
        });
    }
    window.addEventListener("hashchange",()=>{if(dialog){dialog.remove();dialog=undefined;}});
    window.addEventListener("portal-academic-deleted",()=>{if(profile)loading=reload();});
    window.PortalCourseGroups = Object.freeze({bind,clear,reload,edit,get:id=>byClass.get(id),show(value){clear();profile=value;loading=reload();}});
})();
