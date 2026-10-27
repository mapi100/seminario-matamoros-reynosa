(function () {
    "use strict";
    const labels = { tasks: "Tareas", exams: "Exámenes", projects: "Proyectos", participation: "Participación", practice: "Práctica (no cuenta)" };
    const codes = ["tasks", "exams", "projects", "participation"];
    const format = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 2 });
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    let version = 0, current, dialog, restoreFocus, writing = false;
    const controllers = new Set();
    function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined && text !== null) e.textContent = String(text); if (cls) e.className = cls; return e; }
    function text(value, cls = "learning-meta") { return el("p", value, cls); }
    function btn(label, action, secondary = true) { const e = el("button", label, "learning-button" + (secondary ? " secondary" : "")); e.type = "button"; e.addEventListener("click", action); return e; }
    function num(value) { return typeof value === "number" && Number.isFinite(value) ? format.format(value) : "—"; }
    function score(value) { return typeof value === "number" && Number.isFinite(value) ? window.PortalGradeScale.format(value) + " / 10" : "Pendiente"; }
    function urlFor(id) { return "#curso/" + current.ctx.courseId + "/tareas/" + id; }
    function link(label, href) { const a = el("a", label); a.href = href; return a; }
    function message(target, value, error = false) { target.textContent = value; target.className = "learning-status " + (error ? "error" : "success"); target.setAttribute("role", "status"); }
    function errorText(error) {
        if (error?.code === "PT409") return "Los datos cambiaron. Cierra esta ventana y actualiza el libro antes de continuar.";
        if (error?.code === "22023" && typeof error.message === "string") return error.message.slice(0, 400);
        if (["PGRST202", "42883", "42P01"].includes(error?.code)) return "Falta instalar la actualización de ponderaciones en Supabase. Contacta al responsable del portal.";
        return "No se pudo confirmar la operación. Actualiza el libro para revisar el resultado antes de intentarlo otra vez.";
    }
    function close(force = false) {
        if (writing && !force) return;
        if (dialog) { window.PortalLearningFiles?.clear(dialog); if (dialog.open) dialog.close(); dialog.remove(); dialog = undefined; }
        if (!force && restoreFocus?.isConnected) restoreFocus.focus(); restoreFocus = undefined;
    }
    function clear() { version++; close(true); writing = false; current = undefined; for (const c of controllers) c.abort(); controllers.clear(); }
    async function rpc(name, args, write = false) {
        const controller = new AbortController(); controllers.add(controller);
        const timeout = setTimeout(() => controller.abort(), 25000);
        try {
            let request = window.PortalAuth.getClient().rpc(name, args).abortSignal(controller.signal);
            if (write) request = request.retry(false);
            const response = await request;
            if (response.error) throw { ...response.error, status: response.status };
            if (!response.data || typeof response.data !== "object" || Array.isArray(response.data)) throw new Error("Respuesta inválida");
            return response.data;
        } finally { clearTimeout(timeout); controllers.delete(controller); }
    }
    function modal(title, submitLabel, action) {
        close(); restoreFocus = document.activeElement;
        const d = el("dialog", null, "learning-dialog weighted-dialog"); dialog = d;
        const heading = el("div", null, "learning-dialog-heading"), h = el("h2", title); h.id = "weightedDialogTitle"; d.setAttribute("aria-labelledby", h.id);
        const x = btn("×", () => close()); x.setAttribute("aria-label", "Cerrar formulario"); heading.append(h, x);
        const form = el("form"), fields = el("div", null, "learning-fields"), status = text("", "learning-status"), actions = el("div", null, "learning-dialog-actions");
        const save = el("button", submitLabel, "learning-button"); save.type = "submit";
        actions.append(save, btn("Cancelar", () => close())); form.append(fields, status, actions); d.append(heading, form); document.body.append(d);
        const token = version;
        form.addEventListener("submit", async event => {
            event.preventDefault(); if (writing || token !== version || !form.reportValidity()) return;
            writing = true; save.disabled = true; form.setAttribute("aria-busy", "true"); message(status, "Guardando…");
            try {
                const result = await action();
                if (token !== version || dialog !== d) return;
                if (result?.saved !== true) throw new Error("Sin confirmación");
                writing = false; close(); await reload();
                if (result.reopen && current) configure();
            } catch (error) {
                if (token !== version || dialog !== d || current?.ctx.onUnauthorized(error)) return;
                message(status, errorText(error), true);
                // Una respuesta incierta o un conflicto requiere consultar de nuevo.
                save.disabled = error?.code !== "22023";
            } finally { if (token === version && dialog === d) { writing = false; form.setAttribute("aria-busy", "false"); } }
        });
        d.addEventListener("cancel", event => { event.preventDefault(); close(); });
        return { d, fields, actions, save, status, open() { d.showModal(); fields.querySelector("input,select,textarea,button")?.focus(); } };
    }
    function input(target, label, options = {}) {
        const group = el("div", null, "learning-field"), caption = el("label", label);
        const e = el(options.textarea ? "textarea" : "input"); e.id = "weighted-" + crypto.randomUUID(); caption.htmlFor = e.id;
        if (!options.textarea) e.type = options.type || "text";
        e.value = options.value ?? ""; e.required = Boolean(options.required); e.autocomplete = "off";
        if (e.type === "number") { e.min = "0"; e.max = options.grade ? "10" : "100"; e.step = options.grade ? "0.1" : "0.01"; }
        if (e.type === "checkbox") e.checked = Boolean(options.value);
        if (options.textarea) { e.rows = 3; e.maxLength = 1000; }
        if (e.type === "checkbox") { group.classList.add("learning-checkbox"); group.append(e, caption); } else group.append(caption, e);
        target.append(group); return e;
    }
    function select(target, label, choices, value) {
        const group = el("div", null, "learning-field"), caption = el("label", label), e = el("select");
        e.id = "weighted-" + crypto.randomUUID(); caption.htmlFor = e.id;
        for (const [key, name] of choices) { const option = el("option", name); option.value = key; e.append(option); }
        e.value = value; group.append(caption, e); target.append(group); return e;
    }
    function table(target, headings) {
        const scroll = el("div", null, "learning-table-scroll weighted-scroll"); scroll.tabIndex = 0; scroll.setAttribute("aria-label", "Tabla de calificaciones; desplázate para ver todas las columnas");
        const t = el("table", null, "learning-grades-table weighted-table"), head = el("thead"), row = el("tr"), body = el("tbody");
        for (const h of headings) { const cell = el("th", h); cell.scope = "col"; row.append(cell); } head.append(row); t.append(head, body); scroll.append(t); target.append(scroll); return body;
    }
    function publishedSummary(target, summary, finalScore) {
        const grid = el("div", null, "weighted-summary");
        for (const [title, value, help] of [["Promedio actual de la clase", score(summary.average), summary.configured ? "Evaluado y publicado: " + num(summary.coverage) + " % del curso" : "El profesor todavía no ha publicado las ponderaciones."], ["Calificación final publicada", score(finalScore), "Se confirma al terminar el curso y se incorpora al historial académico."]]) {
            const card = el("section", null, "learning-card weighted-result"); card.append(el("h3", title), text(value, "weighted-number"), text(help)); grid.append(card);
        }
        target.append(grid);
        const categories = el("div", null, "weighted-categories");
        for (const code of codes) {
            const c = summary.categories?.find(x => x.code === code), card = el("section", null, "learning-card weighted-category " + code);
            card.append(el("h3", labels[code]), text(c?.weight === 0 ? "No cuenta" : score(c?.average), "weighted-category-score"), text(c ? "Vale " + num(c.weight) + " % del curso" : "Sin ponderación")); categories.append(card);
        }
        target.append(categories);
        target.append(text("El promedio actual usa solo el peso de las actividades calificadas y publicadas. Las pendientes no son cero; las prácticas no cuentan."));
    }
    function own(target, data) {
        target.append(el("h2", "Mis calificaciones")); publishedSummary(target, data.summary, data.final_score);
        const card = el("section", null, "learning-card"); card.append(el("h3", "Mis actividades"));
        const body = table(card, ["Actividad", "Categoría", "Peso en la clase", "Estado", "Calificación", "Comentarios"]);
        for (const a of data.assignments) {
            const calculation = data.summary.items?.find(i => i.id === a.id), row = el("tr"), name = el("th"); name.scope = "row"; name.append(link(a.title, urlFor(a.id)));
            row.append(name, el("td", labels[a.category] || "Por clasificar"), el("td", a.category === "practice" ? "No cuenta" : calculation ? num(calculation.weight) + " %" : "Pendiente"),
                el("td", a.exempt ? "Exentada" : typeof a.score === "number" ? "Evaluada" : a.requires_submission === false ? "Evaluación del profesor" : a.submitted ? "Entregada, sin calificar" : "Sin entrega"),
                el("td", a.exempt ? "Exentada" : score(a.score)), el("td", a.feedback || "—")); body.append(row);
        }
        if (!data.assignments.length) card.append(text("Todavía no hay actividades publicadas.")); target.append(card);
    }
    function staff(target, data) {
        const bar = el("div", null, "weighted-toolbar"); bar.append(el("h2", "Libro de calificaciones"), btn("Configurar evaluación", configure, false), btn("Nueva actividad", newActivity), btn("Revisar y publicar finales", finals)); target.append(bar);
        const overview = el("section", null, "learning-card weighted-overview");
        overview.append(el("h3", data.published ? "Criterios publicados" : "Configura cómo se evalúa esta clase"));
        overview.append(text(data.published ? data.published.categories.map(c => labels[c.code] + ": " + num(c.weight) + " %").join(" · ") : "Reparte el 100 % entre tareas, exámenes, proyectos y participación. Después clasifica las actividades y publica tus criterios."));
        if (data.draft && JSON.stringify(data.draft) !== JSON.stringify(data.published)) overview.append(text("Hay un borrador de criterios pendiente de publicación. Los alumnos siguen viendo los criterios publicados."));
                if (data.published && data.assignments.some(a => !data.published.items.some(i => i.id === a.id))) overview.append(text("Hay actividades nuevas por clasificar. Revisa Configurar evaluación antes de publicar finales.", "learning-status error"));
        target.append(overview);
        const tools = el("div", null, "weighted-toolbar"); tools.append(btn("Actualizar libro", reload), btn("Exportar alumnos mostrados", exportCSV), btn(current.quick ? "Vista de consulta" : "Captura rápida", () => { current.quick = !current.quick; target.replaceChildren(); staff(target, data); })); target.append(tools);
        if (current.quick) {
            tools.append(btn("Guardar borradores", () => saveGrid(false)), btn("Guardar y publicar notas", () => saveGrid(true), false));
            target.append(text("Captura las notas directamente en la tabla. Los espacios vacíos siguen pendientes. Guardar borradores conserva las notas visibles del alumno; Guardar y publicar las actualiza."));
        }
        const body = table(target, ["Alumno", ...codes.map(c => labels[c]), "Promedio actual publicado", "Vista previa con borradores", "Peso evaluado", "Final publicada", ...data.assignments.map(a => a.title)]);
        for (const student of data.students) {
            const row = el("tr"), name = el("th", student.name); name.scope = "row"; row.append(name);
            for (const code of codes) row.append(el("td", score(student.summary.categories?.find(c => c.code === code)?.average)));
            row.append(el("td", score(student.summary.average)), el("td", score(student.draft_summary.average)), el("td", num(student.summary.coverage) + " %"), el("td", score(student.final_score)));
            for (const a of data.assignments) {
                const grade = student.grades.find(g => g.assignment_id === a.id), exempt = student.exemptions.find(e => e.id === a.id), cell = el("td");
                cell.append(text(exempt ? "Exentada" : "Publicada: " + score(grade?.published_score)), btn("Revisar / calificar", () => assessment(student, a)));
                if (current.quick) {
                    const mark = input(cell, "Calificación de " + student.name + ": " + a.title, { type: "number", grade: true, value: window.PortalGradeScale.format(grade?.score) });
                    mark.dataset.enrollment = student.enrollment_id; mark.dataset.assignment = a.id; mark.dataset.original = mark.value; mark.disabled = Boolean(exempt);
                }
                if (!a.published) cell.append(text("Actividad sin publicar")); row.append(cell);
            }
            body.append(row);
        }
        if (!data.students.length) target.append(text("Todavía no hay alumnos activos inscritos en esta clase."));
        const pagination = el("div", null, "weighted-toolbar");
        if (current.offset) pagination.append(btn("Anterior", () => reload(current.offset - 30)));
        pagination.append(text("Alumnos " + (data.students.length ? current.offset + 1 : 0) + "–" + (current.offset + data.students.length)));
        if (data.has_more) pagination.append(btn("Siguiente", () => reload(current.offset + 30))); target.append(pagination);
    }
    async function render(target, ctx, offset = 0, quick = false) {
        clear(); const token = version; current = { target, ctx, offset, quick }; target.replaceChildren();
        const status = text("Consultando calificaciones…", "learning-status"); status.setAttribute("role", "status"); target.append(status);
        try {
            const data = await rpc("portal_gradebook_read", { p_course: ctx.courseId, p_resource: ctx.canManage ? "book" : "own", p_offset: offset, p_limit: 30 });
            if (token !== version || !target.isConnected) return;
            if (!Array.isArray(data.assignments) || data.assignments.length > 100 || !data.assignments.every(a => uuid.test(a.id) && typeof a.title === "string")) throw new Error("Actividades inválidas");
            if (ctx.canManage && (!Array.isArray(data.students) || data.students.length > 30 || !data.students.every(s => uuid.test(s.enrollment_id) && Array.isArray(s.grades) && Array.isArray(s.exemptions) && s.summary && s.draft_summary))) throw new Error("Alumnos inválidos");
            if (!ctx.canManage && !data.summary) throw new Error("Promedio inválido");
            current.data = data; target.replaceChildren(); if (ctx.canManage) staff(target, data); else own(target, data);
        } catch (error) {
            if (token !== version || ctx.onUnauthorized(error)) return;
            message(status, errorText(error), true); target.append(btn("Reintentar", reload));
        }
    }
    async function reload(offset) { if (!current) return; const { target, ctx, quick } = current; return render(target, ctx, typeof offset === "number" ? offset : current.offset, quick); }
    function write(action, data) { return rpc("portal_gradebook_write", { p_course: current.ctx.courseId, p_action: action, p_data: data }, true); }
    function saveGrid(publish) {
        const changed = [...current.target.querySelectorAll("input[data-enrollment]")].filter(e => { const s = current.data.students.find(s => s.enrollment_id === e.dataset.enrollment), g = s.grades.find(g => g.assignment_id === e.dataset.assignment); return e.value !== e.dataset.original || publish && e.value !== "" && g?.score !== g?.published_score; });
        if (!changed.length) { const status = text("No hay notas modificadas para guardar."); current.target.prepend(status); return; }
        if (changed.some(e => e.value === "" || !e.checkValidity())) { current.target.prepend(text("Introduce notas entre 0 y 10 con un decimal. Para exentar una actividad, usa Revisar / calificar.", "learning-status error")); return; }
        const data = current.data;
        const form = modal(publish ? "Publicar notas capturadas" : "Guardar notas como borrador", publish ? "Guardar y publicar" : "Guardar borradores", () => write("assessments_save", { publish, items: changed.map(e => {
            const s = data.students.find(s => s.enrollment_id === e.dataset.enrollment), g = s.grades.find(g => g.assignment_id === e.dataset.assignment);
            return { enrollment_id: s.enrollment_id, assignment_id: e.dataset.assignment, token: s.summary.token, score: window.PortalGradeScale.toWire(e.value, g?.score), feedback: g?.feedback || "", revision: g?.revision || 0 };
        }) }));
        form.fields.append(text("Se guardarán " + changed.length + " notas modificadas. " + (publish ? "Los alumnos verán estas notas y se recalcularán sus promedios actuales." : "Las calificaciones publicadas de los alumnos conservarán sus valores."))); form.open();
    }
    function newActivity() {
        const form = modal("Nueva actividad evaluable", "Continuar", async () => ({})); form.save.type = "button";
        form.fields.append(text("Elige el tipo de actividad. Podrás indicar si requiere entregar archivos o si la califica directamente el profesor."));
        const choice = select(form.fields, "Tipo de actividad", codes.map(c => [c, labels[c]]), "tasks");
        form.save.addEventListener("click", () => { const ctx = current.ctx, category = choice.value; close(); ctx.newAssignment(category); }); form.open();
    }
    function configure() {
        const data = current.data, source = structuredClone(data.draft || data.published || { categories: codes.map((code, i) => ({ code, weight: [30,50,20,0][i], mode: "equal" })), items: [] });
        source.items = data.assignments.map(a => source.items.find(i => i.id === a.id) || { id: a.id, category: a.grading_category || "", share: 1 });
        const form = modal("Configurar evaluación", "Guardar borrador", async () => ({ ...await write("scheme_save", { schema: source, revision: data.revision }), reopen: true }));
        form.d.classList.add("weighted-configuration");
        form.fields.append(text("1. Reparte el 100 % · 2. Clasifica tus actividades · 3. Guarda, revisa y publica"));
        const categoryGrid = el("div", null, "weighted-categories"), total = text("", "weighted-total");
        for (const c of source.categories) {
            const card = el("section", null, "weighted-config-category " + c.code); card.append(el("h3", labels[c.code]));
            const weight = input(card, "Porcentaje de " + labels[c.code], { type: "number", required: true, value: c.weight });
            const mode = select(card, "Repartir " + labels[c.code], [["equal", "Por igual"], ["custom", "Pesos diferentes"]], c.mode);
            weight.addEventListener("input", () => { c.weight = weight.value === "" ? null : Number(weight.value); update(); }); mode.addEventListener("change", () => { c.mode = mode.value; update(); }); categoryGrid.append(card);
        }
        form.fields.append(categoryGrid, total, text("En Pesos diferentes, reparte el 100 % de esa categoría entre sus actividades. A la derecha verás cuánto aporta cada una a toda la clase."));
        const classify = btn("Clasificar pendientes como tareas", () => { for (const f of fields) if (!f.item.category) { f.item.category = "tasks"; f.category.value = "tasks"; } update(); }); form.fields.append(classify);
        const body = table(form.fields, ["Actividad", "Categoría", "Peso dentro de su categoría (%)", "Aporta a la clase"]), fields = [];
        for (const a of data.assignments) {
            const item = source.items.find(i => i.id === a.id), row = el("tr"), name = el("th", a.title); name.scope = "row";
            if (!a.published) name.append(text("Sin publicar"));
            const typeCell = el("td"), shareCell = el("td"), contribution = el("td");
            const category = select(typeCell, "Categoría de " + a.title, [["", "Selecciona"], ...Object.entries(labels)], item.category);
            const share = input(shareCell, "Peso de " + a.title, { type: "number", value: item.share }); share.min = "0.01";
            category.addEventListener("change", () => { item.category = category.value; update(); }); share.addEventListener("input", () => { item.share = share.value === "" ? null : Number(share.value); update(); });
            row.append(name, typeCell, shareCell, contribution); body.append(row); fields.push({ item, category, share, contribution });
        }
        if (!data.assignments.length) form.fields.append(text("Primero crea las tareas, exámenes o proyectos de esta clase. Puedes guardar estos porcentajes como borrador."));
        const preview = el("div", null, "weighted-validation"); form.fields.append(preview);
        const publish = btn("Revisar y publicar criterios", () => publishScheme(source, data), false); form.actions.prepend(publish);
        function update() {
            const sum = source.categories.reduce((n,c) => n + (Number(c.weight) || 0), 0); total.textContent = "Total: " + num(sum) + " % de 100 %"; total.classList.toggle("invalid", Math.abs(sum - 100) > 0.000001);
            const issues = [];
            if (sum !== 100) issues.push("Ajusta los porcentajes para sumar exactamente 100 %.");
            for (const c of source.categories) {
                const items = source.items.filter(i => i.category === c.code);
                if (c.weight > 0 && !items.length) issues.push(labels[c.code] + ": agrega al menos una actividad o cambia su peso a 0 %.");
                if (c.weight > 0 && c.mode === "custom" && items.reduce((s,i) => s + (Number(i.share) || 0), 0) !== 100) issues.push(labels[c.code] + ": los pesos internos deben sumar 100 %. ");
            }
            if (source.items.some(i => !i.category)) issues.push("Selecciona una categoría para cada actividad. Las prácticas no cuentan.");
            for (const f of fields) {
                const c = source.categories.find(c => c.code === f.item.category), count = source.items.filter(i => i.category === f.item.category).length;
                f.share.disabled = !c || c.mode === "equal"; f.share.required = Boolean(c && c.mode === "custom");
                f.share.value = c?.mode === "equal" ? num(100 / count).replace(/,/g, "") : f.item.share ?? "";
                f.contribution.textContent = !c ? "No cuenta" : num(c.weight * (c.mode === "equal" ? 1 / count : (Number(f.item.share) || 0) / 100)) + " %";
            }
            preview.replaceChildren(...issues.map(i => text(i, "learning-status error")));
            const saved = JSON.stringify(source) === JSON.stringify(data.draft);
            publish.disabled = !saved || issues.length > 0;
            if (!saved) preview.append(text("Guarda este borrador para revisarlo antes de publicar. Los promedios de los alumnos todavía no cambian."));
        }
        update(); form.open();
    }
    function publishScheme(schema, data) {
        const form = modal("Publicar criterios de evaluación", "Publicar criterios", () => {
            if (!confirm.checked) throw { code: "22023", message: "Confirma la publicación de los criterios." };
            return write("scheme_publish", { schema, revision: data.revision, confirmed: true, reason: reason.value.trim() });
        });
        for (const c of schema.categories) form.fields.append(text(labels[c.code] + ": " + num(c.weight) + " % · " + (c.mode === "equal" ? "Reparto por igual" : "Pesos diferentes")));
        form.fields.append(text("Al publicar se recalculan los promedios actuales. Las notas finales ya publicadas y los kardex emitidos conservan sus valores."));
        const changed = data.published && JSON.stringify(data.published) !== JSON.stringify(schema);
        const reason = input(form.fields, "Motivo del cambio" + (changed ? " (obligatorio)" : " (opcional)"), { textarea: true, required: Boolean(changed) }); if (changed) reason.minLength = 10;
        const confirm = input(form.fields, "He revisado los porcentajes y las actividades; deseo publicar estos criterios", { type: "checkbox", required: true }); form.open();
    }
    function assessment(student, a) {
        const g = student.grades.find(g => g.assignment_id === a.id) || { revision: 0 }, exemption = student.exemptions.find(e => e.id === a.id);
        const form = modal("Evaluar: " + a.title, "Guardar evaluación", () => {
            const value = Number(mark.value);
            if (!exempt.checked && (mark.value === "" || !Number.isFinite(value) || value < 0 || value > 10)) throw { code: "22023", message: "Introduce una calificación entre 0 y 10 con un decimal." };
            return write("assessment_save", { enrollment_id: student.enrollment_id, assignment_id: a.id, revision: g.revision || 0, token: student.summary.token,
                exempt: exempt.checked, reason: reason.value.trim(), score: exempt.checked ? null : window.PortalGradeScale.toWire(mark.value, g.score), feedback: feedback.value, publish: publish.checked });
        });
        form.fields.append(el("h3", student.name), text("Última calificación publicada: " + score(g.published_score)));
        if (g.submitted_at) form.fields.append(text("Entrega registrada: " + new Date(g.submitted_at).toLocaleString("es-MX")));
        if (g.body) form.fields.append(text(g.body, "learning-prose"));
        if (g.url) { try { const u = new URL(g.url); if (["https:", "http:"].includes(u.protocol) && !u.username && !u.password) { const a = link("Abrir trabajo entregado", u.href); a.target = "_blank"; a.rel = "noopener noreferrer"; form.fields.append(a); } } catch {} }
        if (a.requires_submission !== false) { const files = el("div"); form.fields.append(files); window.PortalLearningFiles?.render(files, { courseId: current.ctx.courseId, assignmentId: a.id, enrollmentId: student.enrollment_id, canManage: true }); }
        const mark = input(form.fields, "Calificación (0 a 10)", { type: "number", grade: true, value: window.PortalGradeScale.format(g.score) });
        const feedback = input(form.fields, "Comentarios para el alumno", { textarea: true, value: g.feedback || "" }); feedback.maxLength = 4000;
        const publish = input(form.fields, "Publicar esta calificación para el alumno", { type: "checkbox", value: true });
        const zero = btn("Registrar cero por no entregar", () => { mark.value = "0"; feedback.value = "No entregada. Calificación registrada por el profesor."; exempt.checked = false; toggle(); }); form.fields.append(zero);
        const exempt = input(form.fields, "Exentar esta actividad para este alumno", { type: "checkbox", value: Boolean(exemption) });
        const reason = input(form.fields, "Motivo de la exención", { textarea: true, value: exemption?.reason || "" }); reason.minLength = 5;
        form.fields.append(text("La exención se publica al guardar y redistribuye el peso entre las demás actividades de la misma categoría. Para quitarla, desmarca la opción y guarda una nota."));
        if (typeof g.published_score === "number" && !exemption) form.actions.prepend(btn("Retirar publicación", () => {
            const confirmation = modal("Retirar la nota publicada", "Retirar publicación", () => write("assessment_unpublish", { enrollment_id: student.enrollment_id, assignment_id: a.id, revision: g.revision || 0, token: student.summary.token }));
            confirmation.fields.append(text("La nota de " + a.title + " dejará de ser visible para " + student.name + ". Quedará como borrador y su promedio actual se recalculará.")); confirmation.open();
        }));
        function toggle() { mark.disabled = exempt.checked; mark.required = !exempt.checked; publish.disabled = exempt.checked; reason.required = exempt.checked; }
        exempt.addEventListener("change", toggle); toggle(); form.open();
    }
    function finals() {
        const students = current.data.students;
        const form = modal("Revisar calificaciones finales", "Publicar finales seleccionadas", () => {
            const selected = fields.filter(f => f.check.checked);
            if (!confirm.checked || !selected.length) throw { code: "22023", message: "Selecciona al menos un alumno y confirma las notas finales." };
            return write("final_publish", { confirmed: true, reason: reason.value.trim(), students: selected.map(f => ({ id: f.student.enrollment_id, token: f.student.summary.token, override: f.override.value === "" ? null : window.PortalGradeScale.toWire(f.override.value) })) });
        });
        form.d.classList.add("weighted-configuration"); form.fields.append(text("Se muestran los alumnos de esta página. Se comprueban nuevamente sus notas al publicar. Los pendientes impiden cerrar la calificación."));
        const body = table(form.fields, ["Seleccionar", "Alumno", "Calculada", "Final publicada", "Ajuste manual (opcional)", "Revisión"]), fields = [];
        for (const student of students) {
            const row = el("tr"), choice = el("td"), adjustment = el("td"), check = input(choice, "Seleccionar a " + student.name, { type: "checkbox", value: false }); check.disabled = !student.summary.ready;
            const override = input(adjustment, "Ajuste de " + student.name, { type: "number", grade: true }); override.disabled = !student.summary.ready;
            row.append(choice, el("th", student.name), el("td", score(student.summary.average)), el("td", score(student.final_score)), adjustment, el("td", student.summary.ready ? "Lista para publicar" : (student.summary.reasons || ["Sin criterios publicados"]).join(" "))); body.append(row); fields.push({ student, check, override });
        }
        const reason = input(form.fields, "Motivo de ajustes o correcciones (mínimo 10 caracteres si corresponde)", { textarea: true });
        const confirm = input(form.fields, "He revisado las notas seleccionadas y confirmo su publicación en el historial académico", { type: "checkbox", required: true }); form.open();
    }
    function exportCSV() {
        const data = current.data, rows = [["Alumno", ...codes.map(c => labels[c]), "Promedio actual publicado (0–10)", "Promedio con borradores (0–10)", "Peso evaluado (%)", "Final publicada (0–10)"]];
        for (const s of data.students) rows.push([s.name, ...codes.map(c => window.PortalGradeScale.format(s.summary.categories.find(x => x.code === c)?.average)), window.PortalGradeScale.format(s.summary.average), window.PortalGradeScale.format(s.draft_summary.average), s.summary.coverage, window.PortalGradeScale.format(s.final_score)]);
        const csv = rows.map(row => row.map(value => '"' + String(value ?? "").replace(/^[=+@\-\t\r]/, "'$&").replace(/"/g, '""') + '"').join(",")).join("\r\n");
        const url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" })), a = link("", url); a.download = "promedios-clase.csv"; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    window.PortalWeightedGrades = Object.freeze({ render, clear });
}());
