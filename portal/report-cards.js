(function () {
    "use strict";
    const $ = id => document.getElementById(id), root = $("reportCards");
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const months = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"];
    const ordinals = ["", "PRIMERO", "SEGUNDO", "TERCERO", "CUARTO", "QUINTO", "SEXTO", "SÉPTIMO", "OCTAVO"];
    const groups = { introductorio: "CI", filosofia: "FILOSOFÍA", teologia: "TEOLOGÍA" };
    let generation = 0, revision = 0, student, source, preview, verify, pending, busy = false, timer, offset = 0, title;
    const controllers = new Set();
    function el(tag, text, cls) { const e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }
    function button(text, action) { const b = el("button", text, "back-link"); b.type = "button"; b.addEventListener("click", action); return b; }
    function note(text, error = false) { $("reportStatus").textContent = text; $("reportStatus").className = "control-message" + (error ? " error" : ""); }
    function missing(error) { return ["PGRST202", "42883", "42P01"].includes(error?.code); }
    function denied(error) { if (!["42501"].includes(error?.code) && ![401,403].includes(error?.status)) return false; const check = verify; clear(); if (check) void check(); return true; }
    function errorText(error) { return ["22023", "PT409"].includes(error?.code) ? String(error.message).slice(0, 350) : "No se pudo consultar la boleta. Comprueba tu conexión y actualiza la vista previa."; }
    async function rpc(name, args) {
        const c = new AbortController(); controllers.add(c);
        try { const r = await window.PortalAuth.getClient().rpc(name, args).retry(false).abortSignal(c.signal); if (r.error) throw { ...r.error, status: r.status }; return r.data; }
        finally { controllers.delete(c); }
    }
    function read(resource, args = {}) { return rpc("portal_report_card_read", { p_resource: resource, p_student: student, p_period: $("reportPeriod").value || null, p_options: options(), p_issue: null, p_offset: 0, ...args }); }
    function options() { return { cycle: $("reportCycle").value.trim(), rector_name: $("reportRector").value.trim(), prefect_name: $("reportPrefect").value.trim() }; }
    function cleanupPrint() { $("reportPrintRoot")?.remove(); document.body.classList.remove("report-printing"); if (title !== undefined) document.title = title; title = undefined; }
    function clear() {
        generation++; revision++; clearTimeout(timer); controllers.forEach(c => c.abort()); controllers.clear(); cleanupPrint();
        student = source = preview = verify = pending = undefined; busy = false; root.hidden = true;
        for (const id of ["reportPreview", "reportReasons", "reportIssues", "reportPeriod"]) $(id).replaceChildren();
        for (const id of ["reportCycle", "reportRector", "reportPrefect"]) $(id).value = "";
        $("reportReviewed").checked = false; note(""); sync();
    }
    function sync() {
        for (const e of root.querySelectorAll("input,select,button")) e.disabled = busy || Boolean(pending);
        $("reportIssue").disabled = busy || !preview?.ready || !preview?.token || !$("reportReviewed").checked;
        $("reportIssue").textContent = pending ? "Comprobar / reintentar emisión" : "Emitir boleta revisada";
        if (pending && !busy) $("reportIssue").disabled = false;
    }
    function cycle(period) { const year = Number(period.starts_on.slice(0, 4)) - (Number(period.starts_on.slice(5, 7)) < 8 ? 1 : 0); return year + "-" + (year + 1); }
    function valid(d) { return d?.version === 1 && d.scale === 10 && d.decimals === 1 && d.pass_mark === 7 && uuid.test(d.student?.id) && typeof d.student.full_name === "string" && uuid.test(d.period?.id) && typeof d.cycle === "string" && Array.isArray(d.reasons) && typeof d.ready === "boolean" && Array.isArray(d.rows) && d.rows.length <= 10000 && d.rows.every(r => typeof r.name === "string" && (r.score === null || typeof r.score === "number" && Number.isFinite(r.score) && r.score >= 0 && r.score <= 10)); }
    function fallback() {
        const period = source.periods.find(p => p.id === $("reportPeriod").value), form = source.formation_history?.find(f => f.period_id === period.id);
        const rows = source.rows.filter(r => r.period_id === period.id).map(r => ({ ...r, source_score: r.score, score: r.score === null ? null : Number(window.PortalGradeScale.format(r.score)) }));
        const reasons = [];
        if (!rows.length) reasons.push("No hay materias inscritas en este periodo.");
        if (!source.student.student_number) reasons.push("Registra la matrícula en Datos del alumno.");
        if (!form) reasons.push("Asigna la etapa y el semestre del alumno para este periodo.");
        rows.filter(r => r.score === null).forEach(r => reasons.push("Falta publicar la calificación final de " + r.name + "."));
        return { version: 1, scale: 10, decimals: 1, pass_mark: 7, student: source.student, institution: { name: "SEMINARIO DE MATAMOROS-REYNOSA" }, period, formation: form, ...options(), rows, ready: false, reasons };
    }
    async function refresh() {
        if (!student || !$("reportPeriod").value || pending) return;
        const g = generation, r = ++revision; preview = undefined; $("reportReviewed").checked = false; $("reportPreview").replaceChildren(); $("reportReasons").replaceChildren(); sync(); note("Preparando boleta…");
        try {
            let result;
            try { result = await read("preview"); }
            catch (error) { if (!missing(error)) throw error; result = fallback(); result.reasons.push("La vista previa está disponible. Para emitir y guardar boletas falta habilitar este apartado en Supabase."); }
            if (g !== generation || r !== revision) return;
            if (!valid(result) || result.ready && !/^[a-f0-9]{32}$/.test(result.token) || result.student.id !== student || result.period.id !== $("reportPeriod").value) throw new Error("Respuesta inválida");
            preview = result; $("reportPreview").append(paper(result)); $("reportReasons").replaceChildren(...result.reasons.map(t => el("li", t)));
            note(result.ready ? "Boleta preparada. Revisa las materias, notas, ciclo y firmantes antes de emitir." : "La boleta todavía tiene requisitos pendientes."); sync();
        } catch (error) { if (g === generation && r === revision && !denied(error)) note(errorText(error), true); }
    }
    async function mount(record, check) {
        clear(); verify = check; student = record.student.id; root.hidden = false; const g = generation;
        try {
            const loaded = record.program ? await rpc("portal_kardex_read", { p_resource: "record", p_student: student, p_program: null, p_search: "", p_offset: 0, p_limit: 30, p_issue: null }) : record;
            if (g !== generation) return;
            source = loaded;
            const periods = new Map();
            for (const row of source.rows) periods.set(row.period_id, { id: row.period_id, name: row.period_name, starts_on: row.starts_on, ends_on: row.ends_on });
            for (const row of source.formation_history || []) periods.set(row.period_id, { id: row.period_id, name: row.period_name, starts_on: row.starts_on, ends_on: row.ends_on });
            source.periods = [...periods.values()].sort((a, b) => b.starts_on.localeCompare(a.starts_on));
            $("reportPeriod").replaceChildren(...source.periods.map(p => new Option(p.name, p.id)));
            $("reportRector").value = source.institution.rector_name || "";
            $("reportPrefect").value = source.institution.prefect_name || "";
            if (source.periods.length) { $("reportCycle").value = cycle(source.periods[0]); void refresh(); } else note("El alumno todavía no tiene periodos con materias o etapa registrada.");
            void loadIssues();
        } catch (error) { if (g === generation && !denied(error)) note(errorText(error), true); }
    }
    function datum(target, label, value) { const p = el("p"); p.append(el("strong", label + ":"), el("span", value || "PENDIENTE")); target.append(p); }
    function periodText(p) { const a = p.starts_on?.split("-"), b = p.ends_on?.split("-"); if (!a || !b) return p.name; return months[Number(a[1])-1] + (a[0] === b[0] ? " A " : " " + a[0] + " A ") + months[Number(b[1])-1] + " " + b[0]; }
    function paper(d, issued) {
        const doc = el("article", null, "report-paper"), header = el("header"), crest = el("img"); crest.src = "../images/escudo_seminario_nuevo-Photoroom.png"; crest.alt = "Escudo del Seminario"; crest.width = 70; crest.height = 86;
        header.append(crest, el("h2", d.institution.name));
        const stage = [d.formation?.stage_name, d.formation?.ecclesial_name].filter(Boolean).join(" - ");
        header.append(el("h3", stage || "ETAPA PENDIENTE"), el("h3", "BOLETA DE CALIFICACIONES"), el("h3", "CICLO " + d.cycle), el("p", periodText(d.period)));
        doc.append(header);
        if (!issued) doc.append(el("p", "VISTA PREVIA · SIN EMITIR", "report-draft"));
        const info = el("div", null, "report-student"), left = el("div"), right = el("div");
        datum(left, "NOMBRE", d.student.full_name); datum(left, "GRUPO", groups[d.formation?.stage_code]);
        datum(right, "MATRÍCULA", d.student.student_number); datum(right, "SEMESTRE", ordinals[d.formation?.semester]); info.append(left, right); doc.append(info);
        const table = el("table"), head = el("thead"), tr = el("tr"), body = el("tbody");
        for (const text of ["MATERIAS", "CALIFICACIÓN"]) { const th = el("th", text); th.scope = "col"; tr.append(th); } head.append(tr); table.append(head);
        for (const r of d.rows) { const row = el("tr"), subject = el("th", r.name); subject.scope = "row"; row.append(subject, el("td", r.score === null ? "PENDIENTE" : r.score.toFixed(1))); body.append(row); }
        table.append(body); doc.append(table);
        const signatures = el("div", null, "report-signatures");
        for (const [name, role] of [[d.rector_name, "Rector"], [d.prefect_name, "Prefecto de Estudios"]]) { const box = el("div"); box.append(el("p", name || "Nombre y firma"), el("p", role)); signatures.append(box); } doc.append(signatures);
        doc.append(el("footer", issued ? issued.folio + " · Emitida " + new Date(issued.issued_at).toLocaleDateString("es-MX") + " · Escala 0–10 · Mínima aprobatoria 7.0" : "Escala 0–10 · Un decimal · Mínima aprobatoria 7.0"));
        return doc;
    }
    async function loadIssues(more = false) {
        const g = generation, s = student; if (!s) return; if (!more) { offset = 0; $("reportIssues").replaceChildren(); } const from = offset;
        $("reportMore").disabled = true;
        try { const d = await read("issues", { p_offset: from }); if (g !== generation || s !== student) return;
            if (!Array.isArray(d.items) || d.items.length > 30 || typeof d.has_more !== "boolean") throw new Error("Lista inválida");
            for (const i of d.items) { if (!uuid.test(i.id) || typeof i.folio !== "string") throw new Error("Documento inválido"); const li = el("li"), info = el("div"); info.append(el("strong", i.folio), el("p", i.period_name)); li.append(info, button("Ver / imprimir boleta", () => void openIssue(i.id))); $("reportIssues").append(li); }
            offset += d.items.length; $("reportMore").hidden = !d.has_more; if (!offset) $("reportIssues").append(el("li", "Todavía no hay boletas emitidas para este alumno."));
        } catch (error) { if (g === generation && !denied(error)) { $("reportMore").hidden = true; $("reportIssues").append(el("li", missing(error) ? "El archivo de boletas estará disponible cuando se habilite este apartado." : "No se pudo consultar el archivo de boletas. Actualiza para volver a intentarlo.")); } }
        finally { if (g === generation) $("reportMore").disabled = false; }
    }
    async function issue() {
        if (!student || busy || (!pending && (!preview?.ready || !$("reportReviewed").checked))) return;
        const g = generation;
        pending ||= { p_student: student, p_period: preview.period.id, p_options: options(), p_token: preview.token, p_request_id: crypto.randomUUID() };
        busy = true; sync(); note("Guardando la boleta revisada…");
        try { const d = await rpc("portal_report_card_issue", pending); if (g !== generation) return;
            if (d?.saved !== true || !uuid.test(d.id) || typeof d.folio !== "string") throw new Error("Emisión sin confirmar");
            pending = undefined; $("reportReviewed").checked = false; note("Boleta emitida: " + d.folio + ". Puedes consultarla e imprimirla en Boletas emitidas."); void loadIssues(); await openIssue(d.id);
        } catch (error) { if (g !== generation || denied(error)) return;
            if (["22023", "PT409"].includes(error?.code) || missing(error)) { pending = undefined; preview = undefined; $("reportReviewed").checked = false; note(missing(error) ? "Falta habilitar la emisión de boletas. Actualiza la vista previa después de instalarla." : errorText(error), true); }
            else note("No se confirmó la respuesta. Usa Comprobar / reintentar emisión: la misma solicitud evita duplicados. También puedes consultar Boletas emitidas.", true);
        } finally { if (g === generation) { busy = false; sync(); } }
    }
    async function openIssue(id) {
        const g = generation;
        try { const d = await read("issue", { p_issue: id }); if (g !== generation) return;
            if (!d || d.id !== id || d.student_id !== student || !valid(d.snapshot) || typeof d.folio !== "string") throw new Error("Documento inválido");
            preview = undefined; $("reportReviewed").checked = false; sync();
            const previewArea = $("reportPreview"); previewArea.replaceChildren(paper(d.snapshot, d), button("Imprimir / Guardar PDF", () => print(d))); previewArea.scrollIntoView({ block: "start", behavior: "smooth" });
        } catch (error) { if (g === generation && !denied(error)) note(errorText(error), true); }
    }
    async function print(d) {
        const g = generation;
        try { // Revalidar permisos y recuperar la copia guardada antes de imprimir.
            const fresh = await read("issue", { p_issue: d.id }); if (g !== generation) return;
            if (fresh?.id !== d.id || fresh.student_id !== student || !valid(fresh.snapshot)) throw new Error("Documento inválido");
            cleanupPrint(); const printRoot = el("div"); printRoot.id = "reportPrintRoot"; printRoot.append(paper(fresh.snapshot, fresh)); document.body.append(printRoot); document.body.classList.add("report-printing"); title = document.title; document.title = fresh.folio;
            await Promise.all([...printRoot.querySelectorAll("img")].map(i => i.decode().catch(() => {}))); if (g !== generation) return; window.print();
        } catch (error) { cleanupPrint(); if (g === generation && !denied(error)) note(errorText(error), true); }
    }
    $("reportPeriod").addEventListener("change", () => { const p = source?.periods.find(p => p.id === $("reportPeriod").value); if (p) $("reportCycle").value = cycle(p); void refresh(); });
    for (const id of ["reportCycle", "reportRector", "reportPrefect"]) $(id).addEventListener("input", () => { revision++; preview = undefined; $("reportReviewed").checked = false; sync(); clearTimeout(timer); timer = setTimeout(() => void refresh(), 350); });
    $("reportRefresh").addEventListener("click", () => { void refresh(); void loadIssues(); });
    $("reportReviewed").addEventListener("change", sync); $("reportIssue").addEventListener("click", () => void issue()); $("reportMore").addEventListener("click", () => void loadIssues(true));
    window.addEventListener("afterprint", cleanupPrint);
    window.PortalReportCards = Object.freeze({ mount, clear });
}());
