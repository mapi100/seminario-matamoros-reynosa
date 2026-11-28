(function () {
    "use strict";

    const $ = id => document.getElementById(id);
    const periodSelect = $("groupFinalPeriod");
    const groupSelect = $("groupFinalGroup");
    const scroll = $("groupFinalTable");
    const draftValues = new Map();
    const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
    const groupCode = /^(CI-[12]|[1-3]F-[1-6]|[1-4]T-[1-8])$/;
    const scale = window.PortalGradeScale;
    const minimum = scale.minimum * 10;
    let access, catalog, model, controller, dialog, downloadUrl;
    let generation = 0, editing = false, busy = false, saving = false;

    function node(tag, text, className) {
        const element = document.createElement(tag);
        if (text != null) element.textContent = text;
        if (className) element.className = className;
        return element;
    }

    function button(label, run, primary = false) {
        const b = node("button", label, "back-link" + (primary ? " control-create" : ""));
        b.type = "button";
        b.addEventListener("click", run);
        return b;
    }

    function status(text, type = "") {
        const target = $("groupFinalStatus");
        target.textContent = text;
        target.className = "control-message" + (type ? " " + type : "");
    }

    function errorText(error) {
        if (["PGRST202", "42883", "42P01"].includes(error?.code)) {
            return "Falta instalar la actualización de calificaciones por grupo en Supabase.";
        }
        if (["22023", "PT409"].includes(error?.code) && typeof error.message === "string") {
            return window.PortalTerms.seminarian(error.message);
        }
        return "No se confirmó la operación. Actualiza el grupo para comprobar las notas.";
    }

    async function rpc(name, args) {
        const current = new AbortController();
        controller = current;
        const timeout = window.setTimeout(() => current.abort(), 25000);
        try {
            const r = await window.PortalAuth.getClient().rpc(name, args).retry(false).abortSignal(current.signal);
            if (r.error) throw { ...r.error, status: r.status };
            return r.data;
        } finally {
            window.clearTimeout(timeout);
            if (controller === current) controller = undefined;
        }
    }

    function closeDialog() {
        if (dialog) {
            dialog.close();
            dialog.remove();
            dialog = undefined;
        }
    }

    function clearSheet() {
        model = undefined;
        editing = false;
        draftValues.clear();
        $("groupFinalSummary").replaceChildren();
        $("groupFinalNotice").hidden = true;
        $("groupFinalNotice").textContent = "";
        scroll.replaceChildren();
        scroll.hidden = true;
    }

    function leave() {
        generation++;
        access = undefined;
        controller?.abort();
        closeDialog();
        if (downloadUrl) URL.revokeObjectURL(downloadUrl);
        downloadUrl = undefined;
        catalog = undefined;
        busy = saving = false;
        clearSheet();
        periodSelect.replaceChildren();
        groupSelect.replaceChildren();
        status("");
        sync();
    }

    function checkAccess(error) {
        if (error?.code !== "42501" && ![401, 403].includes(error?.status)) return false;
        const onDenied = access?.onDenied;
        leave();
        onDenied?.(error);
        return true;
    }

    function snapshotModel(snapshot, period, group) {
        if (snapshot?.period_id !== period || snapshot.group_code !== group || !/^[a-f0-9]{32}$/.test(snapshot.token) ||
            !Array.isArray(snapshot.students) || snapshot.students.length > 500 ||
            !Array.isArray(snapshot.courses) || snapshot.courses.length > 100 ||
            snapshot.students.length * snapshot.courses.length > 10000 ||
            !Array.isArray(snapshot.cells) || snapshot.cells.length > snapshot.students.length * snapshot.courses.length ||
            !Number.isSafeInteger(snapshot.outside_count) || snapshot.outside_count < 0) {
            throw new Error("Grupo de calificaciones inválido");
        }

        const students = new Map();
        for (const student of snapshot.students) {
            if (!uuid.test(student.id) || students.has(student.id) || typeof student.name !== "string" ||
                typeof student.editable !== "boolean" ||
                (student.student_number !== null && typeof student.student_number !== "string")) throw new Error("Seminarista inválido");
            students.set(student.id, { ...student, cells: new Map() });
        }
        const courses = new Map();
        for (const course of snapshot.courses) {
            if (!uuid.test(course.id) || courses.has(course.id) || typeof course.name !== "string" ||
                typeof course.active !== "boolean") throw new Error("Materia inválida");
            courses.set(course.id, { ...course, scores: [] });
        }
        const cellIndex = new Map();
        for (const cell of snapshot.cells) {
            const student = students.get(cell.student_id);
            const course = courses.get(cell.course_id);
            if (!uuid.test(cell.enrollment_id) || cellIndex.has(cell.enrollment_id) || !student || !course ||
                student.cells.has(course.id) || (cell.score !== null && !scale.valid(cell.score)) ||
                cell.editable !== (student.editable && course.active) || typeof cell.requires_reason !== "boolean") {
                throw new Error("Calificación inválida");
            }
            student.cells.set(course.id, cell);
            cellIndex.set(cell.enrollment_id, { cell, student, course });
            course.scores.push(cell.score);
        }

        const rows = Array.from(students.values());
        for (const student of rows) {
            const scores = Array.from(student.cells.values(), cell => cell.score);
            student.average = scores.includes(null) || scores.length === 0 ? null : average(scores);
        }
        const complete = rows.map(student => student.average).filter(value => value !== null);
        const notes = Array.from(cellIndex.values(), row => row.cell.score);
        return {
            snapshot, students: rows, courses: Array.from(courses.values()), cells: cellIndex,
            average: complete.length ? average(complete.map(n => Math.round(n * 10))) : null,
            stats: counts(notes)
        };
    }

    function average(scores) {
        return scores.length ? Math.round(scores.reduce((sum, score) => sum + Math.round(score), 0) / scores.length) / 10 : null;
    }

    function counts(scores) {
        const published = scores.filter(score => score !== null);
        const passed = published.filter(score => score >= minimum).length;
        return {
            average: average(published), published: published.length, passed,
            failed: published.length - passed, pending: scores.length - published.length
        };
    }

    function parseCatalog(data, requestedPeriod, requestedGroup) {
        if (!data || !Array.isArray(data.periods) || !Array.isArray(data.groups) ||
            data.periods.some(p => !uuid.test(p.id) || typeof p.name !== "string") ||
            data.groups.some(g => !groupCode.test(g.code) || typeof g.stage !== "string") ||
            new Set(data.periods.map(p => p.id)).size !== data.periods.length ||
            new Set(data.groups.map(g => g.code)).size !== data.groups.length ||
            (data.period_id === null ? data.periods.length > 0 : !data.periods.some(p => p.id === data.period_id)) ||
            (requestedPeriod && data.period_id !== requestedPeriod) ||
            (requestedGroup && data.snapshot?.group_code !== requestedGroup)) throw new Error("Periodo inválido");
        if (!data.snapshot) {
            if (data.groups.length > 0) throw new Error("Falta seleccionar un grupo");
            return null;
        }
        if (!data.groups.some(g => g.code === data.snapshot.group_code)) throw new Error("Grupo inválido");
        return snapshotModel(data.snapshot, data.period_id, data.snapshot.group_code);
    }

    function formatScore(value) {
        if (value === null) return "Pendiente";
        // No mostrar como aprobatoria una histórica inferior a 7 que redondea a 7.0.
        return value < minimum && Math.round(value) >= minimum
            ? (value / 10).toFixed(3).replace(/0$/, "") : scale.format(value);
    }

    function formatAverage(value) {
        return value === null ? "—" : value.toFixed(1);
    }

    function updateSelects() {
        const periods = catalog?.periods ?? [];
        const groups = catalog?.groups ?? [];
        periodSelect.replaceChildren(...(periods.length
            ? periods.map(p => new Option(p.name, p.id)) : [new Option("Sin periodos", "")]));
        groupSelect.replaceChildren(...(groups.length
            ? groups.map(g => new Option(g.code + " · " + g.stage, g.code)) : [new Option("Sin grupos", "")]));
        periodSelect.value = catalog?.period_id ?? "";
        groupSelect.value = model?.snapshot.group_code ?? groupSelect.options[0].value;
    }

    function canLeave() {
        return !saving && (draftValues.size === 0 || window.confirm("Hay notas sin publicar. ¿Deseas descartar esos cambios?"));
    }

    function selectedScope() {
        return { p_period: periodSelect.value || null, p_group: groupSelect.value || null };
    }

    async function load(period = null, group = null) {
        if (!access || busy) return;
        const version = generation;
        busy = true;
        clearSheet();
        status("Cargando calificaciones finales…");
        sync();
        try {
            const data = await rpc("portal_group_final_grades_read", { p_period: period, p_group: group });
            if (version !== generation) return;
            model = parseCatalog(data, period, group);
            catalog = data;
            updateSelects();
            draw();
            status(model ? "" : (data.period_id ? "Este periodo todavía no tiene grupos con seminaristas o materias." : "Todavía no hay periodos académicos."));
        } catch (error) {
            if (version !== generation || checkAccess(error)) return;
            if (!catalog && ["PGRST202", "42883", "42P01"].includes(error?.code)) access.onUnavailable?.();
            if (version === generation) {
                updateSelects();
                status(errorText(error), "error");
            }
        } finally {
            if (version === generation) {
                busy = false;
                sync();
            }
        }
    }

    function readChanges() {
        const changes = [];
        let invalid = false;
        for (const [id, value] of draftValues) {
            const item = model.cells.get(id);
            try {
                const score = draftScore(value, item.cell.score);
                if (score !== item.cell.score) changes.push({ ...item, score });
            } catch {
                invalid = true;
            }
        }
        return { changes, invalid };
    }

    function draftScore(value, previous) {
        return value === "" ? null : scale.toWire(value.replace(",", "."), previous);
    }

    function sync() {
        const group = model?.snapshot.group_code;
        periodSelect.disabled = busy || !catalog?.periods.length;
        groupSelect.disabled = busy || !catalog?.groups.length;
        $("groupFinalRefresh").disabled = busy;
        $("groupFinalExcel").disabled = busy || editing || !group || !model.students.length;
        $("groupFinalEdit").disabled = busy || editing || !group || !Array.from(model.cells.values()).some(c => c.cell.editable);
        $("groupFinalEdit").setAttribute("aria-pressed", String(editing));
        $("groupFinalEdit").textContent = editing ? "Editando finales" : "Editar finales";
        $("groupFinalReviewBar").hidden = !editing;
        $("groupFinalCancel").disabled = busy;
        const { changes, invalid } = readChanges();
        $("groupFinalDraftStatus").textContent = invalid ? "Corrige las notas marcadas. Usa valores de 0 a 10 con un decimal."
            : changes.length > 500 ? "Publica un máximo de 500 notas por vez."
            : changes.length ? changes.length + (changes.length === 1 ? " cambio sin publicar" : " cambios sin publicar")
            : "Captura una nota o borra el número para dejarla pendiente.";
        $("groupFinalReview").disabled = busy || !changes.length || changes.length > 500 || invalid;
    }

    function headingCell(text, scope) {
        const th = node("th", text);
        th.scope = scope;
        return th;
    }

    function editCell(td, cell, student, course) {
        const editor = node("span", null, "group-grade-editor");
        const input = node("input", null, "group-grade-input");
        input.type = "text";
        input.inputMode = "decimal";
        input.maxLength = 5;
        input.autocomplete = "off";
        input.spellcheck = false;
        input.placeholder = "Pendiente";
        input.setAttribute("aria-label", "Final de " + student.name + " en " + course.name);
        const original = cell.score === null ? "" : formatScore(cell.score);
        input.value = original;
        function changed() {
            let marked = false;
            let invalid = false;
            const text = input.value.trim();
            draftValues.delete(cell.enrollment_id);
            if (text !== original) {
                try { marked = draftScore(text, cell.score) !== cell.score; }
                catch { invalid = true; }
                if (marked || invalid) draftValues.set(cell.enrollment_id, text);
            }
            td.classList.toggle("group-grade-changed", marked);
            td.classList.toggle("group-grade-failed", !marked && !invalid && cell.score !== null && cell.score < minimum);
            input.setAttribute("aria-invalid", String(invalid));
            sync();
        }
        input.addEventListener("input", changed);
        input.addEventListener("blur", () => { if (!input.value.trim()) input.value = ""; });
        td.classList.add("group-grade-editable");
        td.classList.toggle("group-grade-failed", cell.score !== null && cell.score < minimum);
        editor.append(input);
        td.replaceChildren(editor);
    }

    function draw() {
        if (!model) return;
        const summary = $("groupFinalSummary");
        const notices = [];
        if (model.snapshot.outside_count > 0) {
            notices.push("Hay " + model.snapshot.outside_count + " inscripciones fuera de este grupo. Consúltalas en Por seminarista.");
        }
        if (model.students.some(s => !s.editable) || model.courses.some(c => !c.active)) {
            notices.push("Las cuentas y materias inactivas se muestran solo para consulta.");
        }
        if (Array.from(model.cells.values()).some(({ cell }) => cell.score !== null && cell.score < minimum && Math.round(cell.score) >= minimum)) {
            notices.push("Una nota histórica cercana a 7.0 se muestra con su precisión guardada.");
        }
        if (!model.students.length || !model.courses.length) {
            notices.push(!model.students.length ? "Todavía no hay seminaristas asignados a este grupo." : "Todavía no hay materias asignadas a este grupo.");
        }
        $("groupFinalNotice").textContent = notices.join(" ");
        $("groupFinalNotice").hidden = notices.length === 0;
        summary.replaceChildren(...[
            ["Seminaristas", model.students.length],
            ["Promedio grupal", formatAverage(model.average)],
            ["Notas pendientes", model.stats.pending]
        ].map(([label, value]) => {
            const box = node("div");
            box.append(node("span", label), node("strong", value));
            return box;
        }));
        if (!model.students.length) {
            scroll.hidden = true;
            return;
        }

        const table = node("table", null, "group-finals-table");
        table.style.minWidth = (269 + 94 * model.courses.length) + "px";
        const columns = node("colgroup");
        for (let i = 0; i < model.courses.length + 2; i++) columns.append(node("col"));
        table.append(columns);
        const head = table.createTHead().insertRow();
        head.append(headingCell("Seminarista", "col"));
        for (const course of model.courses) {
            const th = headingCell(course.name, "col");
            if (!course.active) th.append(node("small", "Inactiva"));
            head.append(th);
        }
        head.append(headingCell("Promedio", "col"));
        const body = table.createTBody();
        for (const student of model.students) {
            const row = body.insertRow();
            const name = headingCell(student.name, "row");
            if (student.student_number || !student.editable) name.append(node("small",
                [student.student_number, student.editable ? "" : "Solo lectura"].filter(Boolean).join(" · ")));
            row.append(name);
            for (const course of model.courses) {
                const td = row.insertCell();
                const cell = student.cells.get(course.id);
                if (!cell) {
                    td.className = "group-grade-none";
                    td.textContent = "—";
                    td.title = "Sin inscripción activa";
                } else if (editing && cell.editable) {
                    editCell(td, cell, student, course);
                } else if (cell.score === null) {
                    td.className = "group-grade-pending";
                    td.append(node("span", "Pendiente"));
                } else {
                    td.classList.toggle("group-grade-failed", cell.score < minimum);
                    td.textContent = formatScore(cell.score);
                }
            }
            row.insertCell().textContent = formatAverage(student.average);
        }
        scroll.replaceChildren(table);
        scroll.hidden = false;
    }

    function setEditing(value) {
        draftValues.clear();
        editing = value;
        status("");
        draw();
        sync();
        if (value) scroll.querySelector("input")?.focus();
    }

    function review() {
        const { changes, invalid } = readChanges();
        if (!editing || invalid || changes.length < 1 || changes.length > 500 || busy || dialog) return;
        const version = generation;
        const snapshot = model.snapshot;
        const d = node("dialog", null, "learning-dialog group-finals-dialog");
        dialog = d;
        const title = node("h2", "Confirmar calificaciones finales");
        title.id = "groupFinalConfirmTitle";
        d.setAttribute("aria-labelledby", title.id);
        const list = node("ul", null, "group-finals-changes");
        for (const { student, course, cell, score } of changes) {
            const li = node("li");
            li.append(node("strong", student.name), node("span", " · " + course.name + " · " + formatScore(cell.score) + " → " + formatScore(score)));
            list.append(li);
        }
        const hasPending = changes.some(({ score }) => score === null);
        const needsReason = changes.some(({ cell, score }) => score !== null && cell.requires_reason);
        const reasonLabel = node("label", needsReason ? "Motivo de la captura o corrección" : "Motivo (opcional)", "group-finals-reason");
        const reason = node("textarea");
        reason.maxLength = 1000;
        reason.rows = 2;
        reason.autocomplete = "off";
        if (needsReason) {
            reason.required = true;
            reason.minLength = 10;
            reason.placeholder = "Escribe al menos 10 caracteres.";
        }
        reasonLabel.append(reason);
        const confirmed = node("input");
        confirmed.type = "checkbox";
        const confirmLabel = node("label", null, "school-confirm");
        confirmLabel.append(confirmed, node("span", "He revisado estas notas y confirmo su publicación."));
        const notice = node("p", "", "control-message");
        notice.setAttribute("role", "status");
        const actions = node("div", null, "group-finals-actions");
        let needsRefresh = false;
        const cancel = button("Volver", dismiss);
        const submitText = hasPending
            ? changes.length === 1 ? "Confirmar cambio" : "Confirmar cambios"
            : "Publicar " + changes.length + (changes.length === 1 ? " final" : " finales");
        const submit = button(submitText, () => void publish(), true);
        function syncDialog() {
            submit.disabled = busy || needsRefresh || (!hasPending && !confirmed.checked) ||
                (needsReason && reason.value.trim().length < 10);
            confirmed.disabled = reason.disabled = busy || needsRefresh;
            cancel.disabled = busy;
        }
        function dismiss() {
            if (busy) return;
            closeDialog();
            if (needsRefresh) void load(snapshot.period_id, snapshot.group_code);
            else $("groupFinalReview").focus();
        }
        confirmed.addEventListener("change", syncDialog);
        reason.addEventListener("input", syncDialog);
        const periodName = catalog.periods.find(p => p.id === snapshot.period_id).name;
        actions.append(cancel, submit);
        d.append(title, node("p", snapshot.group_code + " · " + periodName), list);
        if (!hasPending || needsReason) d.append(reasonLabel);
        if (!hasPending) d.append(confirmLabel);
        d.append(notice, actions);
        d.addEventListener("cancel", event => { event.preventDefault(); dismiss(); });
        document.body.append(d);
        syncDialog();
        d.showModal();

        async function publish() {
            if (version !== generation || busy || submit.disabled) return;
            busy = saving = true;
            sync();
            syncDialog();
            notice.className = "control-message";
            notice.textContent = "Guardando cambios en las calificaciones finales…";
            try {
                const result = await rpc("portal_group_final_grades_save", {
                    p_period: snapshot.period_id, p_group: snapshot.group_code, p_token: snapshot.token,
                    p_items: changes.map(({ cell, score }) => ({ enrollment_id: cell.enrollment_id, score })),
                    p_reason: reason.value.trim(), p_confirmed: true
                });
                if (version !== generation || d !== dialog) return;
                if (result?.saved !== true || result.changed !== changes.length) throw new Error("Publicación sin confirmar");
                const updated = snapshotModel(result.snapshot, snapshot.period_id, snapshot.group_code);
                if (changes.some(({ cell, score }) => updated.cells.get(cell.enrollment_id)?.cell.score !== score)) {
                    throw new Error("Calificación publicada sin confirmar");
                }
                model = updated;
                closeDialog();
                setEditing(false);
                const savedText = hasPending
                    ? "Cambios guardados en las calificaciones finales."
                    : changes.length === 1 ? "Calificación final publicada." : "Calificaciones finales publicadas.";
                status(savedText, "success");
            } catch (error) {
                if (version !== generation || checkAccess(error)) return;
                needsRefresh = true;
                cancel.textContent = "Cerrar y actualizar";
                notice.className = "control-message error";
                notice.textContent = errorText(error);
            } finally {
                if (version === generation) {
                    busy = saving = false;
                    sync();
                    if (d === dialog) syncDialog();
                    else $("groupFinalEdit").focus();
                }
            }
        }
    }

    function decimal(value, failed = false) {
        return value === null ? "Pendiente" : { decimal: value, failed };
    }

    function workbook(periodName) {
        const group = model.snapshot.group_code;
        const gradeRows = [
            ["Calificaciones finales", periodName, group],
            ["Escala", 10, "Mínima aprobatoria", decimal(scale.minimum)],
            ["Seminarista", "Matrícula", ...model.courses.map(c => c.name), "Promedio semestral"]
        ];
        for (const student of model.students) {
            const grades = model.courses.map(course => {
                const cell = student.cells.get(course.id);
                return cell ? decimal(cell.score === null ? null : Number(formatScore(cell.score)), cell.score !== null && cell.score < minimum) : "Sin inscripción";
            });
            gradeRows.push([student.name, student.student_number, ...grades, decimal(student.average)]);
        }
        const summary = [
            ["Estadísticas de finales", periodName, group],
            ["Seminaristas", model.students.length],
            ["Promedio grupal", decimal(model.average)],
            ["Publicadas", model.stats.published],
            ["Aprobadas", model.stats.passed],
            ["Reprobadas", model.stats.failed],
            ["Pendientes", model.stats.pending],
            ["El promedio grupal usa los promedios semestrales completos."],
            [],
            ["Materia", "Promedio", "Publicadas", "Aprobadas", "Reprobadas", "Pendientes"]
        ];
        for (const course of model.courses) {
            const stats = counts(course.scores);
            summary.push([course.name, decimal(stats.average), stats.published, stats.passed, stats.failed, stats.pending]);
        }
        return window.PortalGradeWorkbook.create([
            { name: "Calificaciones", rows: gradeRows, headingRow: 3, freezeColumns: 2, widths: [36, 18, ...model.courses.map(() => 24), 20] },
            { name: "Estadísticas", rows: summary, headingRow: 10, widths: [46, 18, 14, 14, 14, 14] }
        ]);
    }

    async function exportExcel() {
        if (!model || editing || busy) return;
        const version = generation;
        const scope = selectedScope();
        busy = true;
        sync();
        status("Preparando el Excel con las finales publicadas…");
        try {
            const data = await rpc("portal_group_final_grades_read", scope);
            if (version !== generation) return;
            model = parseCatalog(data, scope.p_period, scope.p_group);
            catalog = data;
            updateSelects();
            draw();
            if (!model.students.length) {
                status("Este grupo todavía no tiene seminaristas para exportar.");
                return;
            }
            const period = catalog.periods.find(p => p.id === scope.p_period).name;
            const filename = (scope.p_group + "_" + period).normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9_-]+/gi, "_");
            const file = workbook(period);
            if (downloadUrl) URL.revokeObjectURL(downloadUrl);
            const url = URL.createObjectURL(file);
            downloadUrl = url;
            const a = node("a");
            a.href = url;
            a.download = "Calificaciones_" + filename + ".xlsx";
            document.body.append(a);
            a.click();
            a.remove();
            window.setTimeout(() => {
                if (downloadUrl === url) {
                    URL.revokeObjectURL(url);
                    downloadUrl = undefined;
                }
            }, 3000);
            status("Excel preparado con las notas publicadas y las estadísticas del grupo.", "success");
        } catch (error) {
            if (version === generation && !checkAccess(error)) status(errorText(error), "error");
        } finally {
            if (version === generation) {
                busy = false;
                sync();
            }
        }
    }

    periodSelect.addEventListener("change", () => {
        if (canLeave()) void load(periodSelect.value);
        else updateSelects();
    });
    groupSelect.addEventListener("change", () => {
        if (canLeave()) void load(periodSelect.value, groupSelect.value);
        else updateSelects();
    });
    $("groupFinalRefresh").addEventListener("click", () => {
        if (canLeave()) {
            const scope = selectedScope();
            void load(scope.p_period, scope.p_group);
        }
    });
    $("groupFinalEdit").addEventListener("click", () => setEditing(true));
    $("groupFinalCancel").addEventListener("click", () => { if (canLeave()) setEditing(false); });
    $("groupFinalReview").addEventListener("click", review);
    $("groupFinalExcel").addEventListener("click", () => void exportExcel());
    window.addEventListener("beforeunload", event => {
        if (saving || draftValues.size > 0) {
            event.preventDefault();
            event.returnValue = "";
        }
    });

    window.PortalGroupFinals = Object.freeze({
        open(options) { leave(); access = options; void load(); },
        leave,
        canLeave
    });
}());
