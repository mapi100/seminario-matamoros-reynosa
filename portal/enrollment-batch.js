(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es");
    const stages = [{ code:"introductorio", name:"Introductorio", semesters:2 }, { code:"filosofia", name:"Filosofía", semesters:6 }, { code:"teologia", name:"Teología", semesters:8 }];
    let profile, verify, course, callback, controller, generation = 0, rows = [], selected = new Set(), loading = false, saving = false, uncertain = false, returnFocus, filtersReady = false;
    const dialog = $("batchEnrollmentDialog");
    function node(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
    function status(text, error = false) { $("batchEnrollmentStatus").textContent = text; $("batchEnrollmentStatus").className = "control-message" + (error ? " error" : ""); }
    function leave() {
        generation++; controller?.abort(); controller = course = callback = undefined;
        rows = []; selected.clear(); loading = saving = uncertain = filtersReady = false;
        $("batchEnrollmentList").replaceChildren(); $("batchEnrollmentSummary").replaceChildren(); $("batchEnrollmentSearch").value = "";
        $("batchEnrollmentStage").replaceChildren(); $("batchEnrollmentSemester").replaceChildren(); $("batchEnrollmentFormationHelp").textContent = "";
        status(""); $("batchEnrollmentCount").textContent = "";
        if (dialog.open) dialog.close();
        if (returnFocus?.isConnected) returnFocus.focus(); returnFocus = undefined;
    }
    function clear() { leave(); profile = verify = undefined; }
    function denied(error) {
        if (error?.code !== "42501" && ![401, 403].includes(error?.status)) return false;
        const check = verify; clear(); if (check) void check(); return true;
    }
    function groupLabel(stage,semester) { return stage === "introductorio" ? "CI-"+semester : Math.ceil(semester/2)+(stage === "filosofia" ? "F-" : "T-")+semester; }
    function targetGroup() { const match = /^(CI|[1-3]F|[1-4]T)-([1-8])$/.exec(course?.group_code || ""); if (!match) return null; const stage = match[1] === "CI" ? "introductorio" : match[1].endsWith("F") ? "filosofia" : "teologia", semester = Number(match[2]); return groupLabel(stage,semester) === course.group_code ? {stage,semester} : null; }
    function matches() {
        const needle = normalize($("batchEnrollmentSearch").value.trim()), stage = $("batchEnrollmentStage").value, semester = $("batchEnrollmentSemester").value;
        return rows.filter(row => (!stage || (stage === "none" ? row.stage_code === null : row.stage_code === stage)) && (!semester || row.semester === Number(semester)) && normalize(row.full_name + " " + (row.email || "")).includes(needle));
    }
    function semesterOptions(preferred = "") {
        const selectedStage = stages.find(stage => stage.code === $("batchEnrollmentStage").value), select = $("batchEnrollmentSemester");
        select.replaceChildren(new Option("Todos los semestres", ""));
        if (selectedStage) for (let i=1;i<=selectedStage.semesters;i++) select.append(new Option(groupLabel(selectedStage.code,i)+" ("+rows.filter(row => row.stage_code === selectedStage.code && row.semester === i).length+")",String(i)));
        select.value = [...select.options].some(option => option.value === String(preferred)) ? String(preferred) : "";
    }
    function stageOptions() {
        const previous = $("batchEnrollmentStage").value;
        $("batchEnrollmentStage").replaceChildren(new Option("Todas las etapas", ""), ...stages.map(stage => new Option(stage.name+" ("+rows.filter(row => row.stage_code === stage.code).length+")",stage.code)), new Option("Sin etapa asignada ("+rows.filter(row => row.stage_code === null).length+")","none"));
        $("batchEnrollmentStage").value = previous;
    }
    async function formation(period, signal) {
        const map = new Map(); let more = true;
        while (more) {
            if (map.size >= 10000) throw new Error("Lista de etapas demasiado grande");
            const result = await window.PortalAuth.getClient().rpc("portal_formation_read", { p_resource:"students", p_period:period, p_stage:"", p_search:"", p_offset:map.size, p_limit:100 }).retry(false).abortSignal(signal);
            if (result.error) throw { ...result.error, status:result.status };
            const data = result.data;
            if (!Array.isArray(data?.items) || data.items.length > 100 || typeof data.has_more !== "boolean" || data.has_more && !data.items.length) throw new Error("Lista de etapas inválida");
            for (const row of data.items) {
                const stage = stages.find(stage => stage.code === row?.stage_code);
                if (!uuid.test(row?.id) || map.has(row.id) || (row.stage_code === null ? row.semester !== null : !stage || !Number.isInteger(row.semester) || row.semester < 1 || row.semester > stage.semesters)) throw new Error("Etapa inválida");
                map.set(row.id, {stage_code:row.stage_code,semester:row.semester});
            }
            more = data.has_more;
        }
        return map;
    }
    function sync() {
        $("batchEnrollmentForm").setAttribute("aria-busy", String(loading || saving));
        $("batchEnrollmentSave").disabled = loading || saving || uncertain || !selected.size;
        $("batchEnrollmentSave").textContent = saving ? "Inscribiendo…" : "Inscribir " + selected.size + (selected.size === 1 ? " alumno" : " alumnos");
        $("batchEnrollmentSearch").disabled = loading || saving;
        $("batchEnrollmentStage").disabled = loading || saving || !filtersReady;
        $("batchEnrollmentSemester").disabled = loading || saving || !stages.some(stage => stage.code === $("batchEnrollmentStage").value);
        $("batchEnrollmentAllStages").disabled = loading || saving || !filtersReady;
        $("batchEnrollmentSelectAll").disabled = loading || saving || uncertain || !matches().some(row => row.status !== "enrolled");
        $("batchEnrollmentClear").disabled = loading || saving || uncertain || !selected.size;
        $("batchEnrollmentRefresh").disabled = loading || saving;
        for (const id of ["batchEnrollmentClose", "batchEnrollmentCancel"]) $(id).disabled = saving;
        const visible = matches(), visibleIds = new Set(visible.map(row => row.id)), outside = [...selected].filter(id => !visibleIds.has(id)).length;
        $("batchEnrollmentCount").textContent = selected.size + (selected.size === 1 ? " seleccionado" : " seleccionados") + (outside ? " ("+outside+" fuera del filtro)" : "") + " · " + visible.length + " mostrados";
    }
    function render() {
        const list = $("batchEnrollmentList"); list.replaceChildren();
        $("batchEnrollmentFormationHelp").hidden = !rows.some(row => row.stage_code === null) || $("batchEnrollmentStage").value !== "none" && matches().length > 0;
        let previousGroup;
        for (const row of matches()) {
            const key = row.stage_code === null ? "none" : row.stage_code+":"+row.semester;
            if (key !== previousGroup) { const heading = node("li", undefined, "batch-enrollment-group"); heading.append(node("h3",row.stage_code === null ? "Sin etapa asignada" : stages.find(stage => stage.code === row.stage_code).name+" · "+groupLabel(row.stage_code,row.semester))); list.append(heading); previousGroup = key; }
            const li = node("li"), label = node("label", undefined, "batch-enrollment-person"), check = node("input");
            check.type = "checkbox"; check.value = row.id; check.checked = selected.has(row.id) || row.status === "enrolled";
            check.disabled = loading || saving || uncertain || row.status === "enrolled";
            const info = node("span"); info.append(node("strong", row.full_name));
            if (row.email) info.append(node("small", row.email));
            const state = node("small", row.status === "enrolled" ? "Ya inscrito" : row.status === "inactive" ? "Se reactivará su inscripción" : "Disponible", "batch-enrollment-state");
            label.append(check, info, state); li.append(label); list.append(li);
            check.addEventListener("change", () => { if (check.checked) selected.add(row.id); else selected.delete(row.id); sync(); });
        }
        if (!list.children.length) list.append(node("li", rows.length ? "No hay alumnos que coincidan con la etapa, el semestre y la búsqueda. Puedes cambiar los filtros o ver todas las etapas." : "Todavía no hay alumnos activos disponibles.", "batch-enrollment-empty"));
        sync();
    }
    async function load() {
        if (!profile || !course || saving) return;
        const operation = ++generation; controller?.abort(); controller = new AbortController(); loading = true;
        $("batchEnrollmentList").replaceChildren(); status("Cargando alumnos y sus inscripciones…"); sync();
        try {
            const [result, formations] = await Promise.all([
                window.PortalAuth.getClient().rpc("portal_enrollment_candidates", { p_class: course.id }).retry(false).abortSignal(controller.signal),
                formation(course.period_id, controller.signal)
            ]);
            if (operation !== generation || !course) return;
            if (result.error) throw { ...result.error, status: result.status };
            const data = result.data, ids = new Set();
            if (data?.class_id !== course.id || !Array.isArray(data.items) || data.items.length > 10000 || data.items.some(row => {
                const invalid = !uuid.test(row?.id) || ids.has(row.id) || typeof row.full_name !== "string" || !row.full_name.trim() || row.full_name.length > 160 || row.email !== null && (typeof row.email !== "string" || row.email.length > 320) || !["available", "inactive", "enrolled"].includes(row.status);
                ids.add(row?.id); return invalid;
            })) throw new Error("Lista inválida");
            rows = data.items.map(row => ({...row,...(formations.get(row.id)||{stage_code:null,semester:null})}));
            rows.sort((a,b) => (a.stage_code === null ? 3 : stages.findIndex(stage => stage.code === a.stage_code)) - (b.stage_code === null ? 3 : stages.findIndex(stage => stage.code === b.stage_code)) || (a.semester||0)-(b.semester||0) || a.full_name.localeCompare(b.full_name,"es") || a.id.localeCompare(b.id));
            selected = new Set([...selected].filter(id => rows.some(row => row.id === id && row.status !== "enrolled")));
            const previousSemester = $("batchEnrollmentSemester").value; stageOptions();
            if (!filtersReady) { const target = targetGroup(); $("batchEnrollmentStage").value = rows.length && rows.every(row => row.stage_code === null) ? "none" : target?.stage || ""; semesterOptions($("batchEnrollmentStage").value === target?.stage ? target.semester : ""); filtersReady = true; }
            else semesterOptions(previousSemester);
            const missing = rows.filter(row => row.stage_code === null).length;
            $("batchEnrollmentFormationHelp").textContent = missing ? missing+" sin etapa en este periodo. Regístrala en Etapas y semestres para agruparlos." : "Etapas y semestres registrados para el periodo de esta clase.";
            uncertain = false; loading = false; render();
            status("Selecciona alumnos. Las bajas se reactivan y los ya inscritos se omiten.");
        } catch (error) {
            if (operation !== generation || denied(error)) return;
            controller?.abort();
            uncertain = true; status(["PGRST202", "42883"].includes(error?.code) ? "La inscripción múltiple todavía no está habilitada. Contacta al responsable del portal." : error?.code === "22023" ? error.message : "No se pudieron cargar los alumnos. Pulsa Actualizar lista para reintentar.", true);
        } finally { if (operation === generation) { loading = false; sync(); } }
    }
    async function save() {
        if (!profile || !course || loading || saving || uncertain || !selected.size) return;
        if (selected.size > 500) { status("Selecciona un máximo de 500 alumnos por operación.", true); return; }
        const operation = generation, ids = [...selected].sort(); saving = true; render(); status("Guardando " + ids.length + " inscripciones…");
        try {
            const result = await window.PortalAuth.getClient().rpc("portal_enroll_students", { p_class: course.id, p_students: ids }).retry(false).abortSignal(controller.signal);
            if (operation !== generation || !course) return;
            if (result.error) throw { ...result.error, status: result.status };
            const data = result.data;
            if (data?.saved !== true || data.class_id !== course.id || data.selected !== ids.length || [data.enrolled, data.reactivated, data.already_enrolled].some(n => !Number.isInteger(n) || n < 0) || data.enrolled + data.reactivated + data.already_enrolled !== ids.length) throw new Error("Guardado sin confirmar");
            const notice = data.enrolled + (data.enrolled === 1 ? " nuevo · " : " nuevos · ") + data.reactivated + (data.reactivated === 1 ? " reactivado · " : " reactivados · ") + data.already_enrolled + (data.already_enrolled === 1 ? " ya inscrito. Clase: " : " ya inscritos. Clase: ") + course.subject_name + ".";
            const done = callback; leave(); if (done) done({ ...data, notice });
        } catch (error) {
            if (operation !== generation || denied(error)) return;
            uncertain = true;
            status(error?.code === "22023" ? error.message + " Pulsa Actualizar lista." : "No se pudo confirmar la inscripción. Pulsa Actualizar lista para revisar quiénes quedaron inscritos antes de volver a guardar.", true);
        } finally { if (operation === generation) { saving = false; render(); } }
    }
    $("batchEnrollmentForm").addEventListener("submit", event => { event.preventDefault(); void save(); });
    $("batchEnrollmentSearch").addEventListener("input", render);
    $("batchEnrollmentStage").addEventListener("change", () => { semesterOptions(); render(); });
    $("batchEnrollmentSemester").addEventListener("change", render);
    $("batchEnrollmentAllStages").addEventListener("click", () => { $("batchEnrollmentStage").value = ""; semesterOptions(); $("batchEnrollmentSearch").value = ""; render(); });
    $("batchEnrollmentSelectAll").addEventListener("click", () => { for (const row of matches()) if (row.status !== "enrolled") selected.add(row.id); render(); });
    $("batchEnrollmentClear").addEventListener("click", () => { selected.clear(); render(); });
    $("batchEnrollmentRefresh").addEventListener("click", () => void load());
    for (const id of ["batchEnrollmentClose", "batchEnrollmentCancel"]) $(id).addEventListener("click", () => { if (!saving) leave(); });
    dialog.addEventListener("cancel", event => { event.preventDefault(); if (!saving) leave(); });
    window.PortalEnrollmentBatch = Object.freeze({
        clear, leave,
        show(value, check) { clear(); if (value.role === "control_escolar") { profile = value; verify = check; } },
        open(row, done) {
            if (!profile || !uuid.test(row?.id) || !uuid.test(row.period_id) || row.active !== true || typeof row.subject_name !== "string" || typeof row.period_name !== "string") return;
            leave(); course = { ...row }; callback = done; returnFocus = document.activeElement;
            $("batchEnrollmentSummary").append(node("strong", row.subject_name), node("p", (row.group_code ? row.group_code + " · " : "") + row.period_name));
            dialog.showModal(); $("batchEnrollmentSearch").focus(); void load();
        }
    });
})();
