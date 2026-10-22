(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const dialog = $("deletionDialog"), form = $("deletionForm"), confirmation = $("deletionConfirmation"), save = $("deletionSave");
    const labels = {class: "clase", subject: "materia", period: "periodo"};
    const countLabels = {classes: "clases", enrollments: "inscripciones", professors: "asignaciones de profesores", announcements: "anuncios", modules: "unidades", topics: "contenidos", assignments: "tareas", submissions: "entregas", grades: "calificaciones y borradores", events: "eventos", stored_files: "archivos almacenados"};
    let active = false, recheck, version = 0, cleanupVersion = 0, controller, target, callback, returnFocus, busy = false, uncertain = false, cleaning = false, cleanupRequested = false, cleanupPrefix = "";
    const api = () => window.PortalAuth.getClient();
    function message(value) { $("deletionMessage").textContent = value; }
    function notice(value, retry = false) {
        $("deletionNoticeText").textContent = value;
        $("deletionNotice").hidden = !value;
        $("deletionCleanupRetry").hidden = !retry;
    }
    function close() {
        version++; controller?.abort(); controller = undefined; target = undefined; callback = undefined; busy = false; uncertain = false;
        if (dialog.open) dialog.close();
        form.reset(); message(""); $("deletionCounts").replaceChildren(); $("deletionTarget").textContent = ""; save.disabled = true;
        if (returnFocus?.isConnected) returnFocus.focus(); returnFocus = undefined;
    }
    function clear() { active = false; recheck = undefined; cleanupVersion++; cleaning = false; cleanupRequested = false; cleanupPrefix = ""; close(); notice(""); }
    function denied(error) {
        if (error?.code !== "42501" && ![401, 403].includes(error?.status)) return false;
        const verify = recheck; clear(); if (verify) void verify(); return true;
    }
    async function rpc(name, args, signal) {
        let query = api().rpc(name, args).retry(false);
        if (signal) query = query.abortSignal(signal);
        const response = await query;
        if (response.error) throw {...response.error, status: response.status};
        return response.data;
    }
    function sync() {
        save.disabled = busy || uncertain || !target || confirmation.value !== "ELIMINAR";
        confirmation.disabled = busy || !target;
        $("deletionClose").disabled = busy; $("deletionCancel").disabled = busy;
        form.setAttribute("aria-busy", String(busy));
    }
    async function open(kind, id, after) {
        if (!active || !Object.hasOwn(labels, kind) || busy) return;
        close(); returnFocus = document.activeElement; callback = after;
        const operation = version; controller = new AbortController();
        $("deletionTitle").textContent = "Eliminar " + labels[kind] + " definitivamente";
        $("deletionDescription").textContent = (kind === "class" ? "Se borrará esta clase de este periodo." : kind === "subject" ? "Se borrarán la materia del catálogo y todas sus clases en todos los periodos." : "Se borrarán el periodo y todas sus clases.") + " Se eliminarán sus inscripciones, contenidos, entregas, calificaciones y adjuntos. Las cuentas de las personas se conservarán. Esta acción no se puede deshacer.";
        message("Calculando los datos que se eliminarán…"); sync(); dialog.showModal();
        try {
            const preview = await rpc("portal_admin_delete_preview", {p_kind: kind, p_id: id}, controller.signal);
            if (!active || operation !== version) return;
            if (!preview || preview.id !== id || preview.kind !== kind || typeof preview.label !== "string" || !/^[a-f0-9]{32}$/.test(preview.token) || !preview.counts || !Object.keys(countLabels).every(key => Number.isSafeInteger(preview.counts[key]) && preview.counts[key] >= 0)) throw new Error("Vista previa inválida");
            target = preview; $("deletionTarget").textContent = preview.label;
            for (const [key, label] of Object.entries(countLabels)) {
                const item = document.createElement("li"); item.textContent = label.charAt(0).toUpperCase() + label.slice(1) + ": " + preview.counts[key]; $("deletionCounts").append(item);
            }
            message("Revisa el alcance antes de confirmar."); sync(); confirmation.focus();
        } catch (error) {
            if (!active || operation !== version || denied(error)) return;
            message(error?.code === "22023" ? error.message : "No se pudo calcular la eliminación. Cierra y vuelve a intentarlo."); sync();
        }
    }
    function validQueue(data) {
        return data && (data.bucket_id === undefined || ["portal-coursework", "portal-content"].includes(data.bucket_id)) && Number.isSafeInteger(data.remaining) && data.remaining >= 0 && Array.isArray(data.paths) && data.paths.length <= 100 && data.paths.length <= data.remaining && data.paths.every(path => typeof path === "string" && path.length <= 400 && /^[0-9a-f-]{36}\//i.test(path));
    }
    async function cleanup(remove = false, prefix = "") {
        if (!active) return;
        if (cleaning) { if (remove) { cleanupRequested = true; cleanupPrefix = prefix; } return; }
        const operation = ++cleanupVersion; cleaning = true; $("deletionCleanupRetry").disabled = true;
        try {
            let queue = await rpc("portal_admin_cleanup_files", {p_ack: true});
            if (!active || operation !== cleanupVersion) return;
            if (!validQueue(queue)) throw new Error("Lista de limpieza inválida");
            if (remove && queue.remaining) notice(prefix + " Eliminando archivos almacenados…");
            // Lotes acotados. Si hay más de 1.000 archivos se puede continuar con Reintentar.
            for (let batch = 0; remove && queue.remaining && batch < 10; batch++) {
                if (!queue.paths.length) throw new Error("Limpieza incompleta");
                const previous = queue.remaining;
                const response = await api().storage.from(queue.bucket_id || "portal-coursework").remove(queue.paths);
                if (!active || operation !== cleanupVersion) return;
                if (response.error) throw response.error;
                queue = await rpc("portal_admin_cleanup_files", {p_ack: true});
                if (!active || operation !== cleanupVersion) return;
                if (!validQueue(queue) || queue.remaining >= previous) throw new Error("Storage no confirmó el borrado");
            }
            notice(queue.remaining ? (prefix || "El registro fue eliminado.") + " Quedan " + queue.remaining + " archivos por borrar del almacenamiento. Pulsa Reintentar; el avance se conserva aunque cierres el portal." : prefix, queue.remaining > 0);
        } catch (error) {
            if (!active || operation !== cleanupVersion || denied(error)) return;
            notice((prefix ? prefix + " " : "") + "No se pudo comprobar la limpieza de archivos. Pulsa Reintentar para consultar y completar cualquier borrado pendiente.", true);
        } finally {
            if (operation === cleanupVersion) { cleaning = false; $("deletionCleanupRetry").disabled = false; if (cleanupRequested && active) { const nextPrefix = cleanupPrefix; cleanupRequested = false; cleanupPrefix = ""; void cleanup(true, nextPrefix); } }
        }
    }
    async function submit() {
        if (!active || busy || uncertain || !target || confirmation.value !== "ELIMINAR" || !form.reportValidity()) return;
        const operation = version, selected = target, after = callback; busy = true; sync(); message("Eliminando…");
        try {
            const response = await rpc("portal_admin_delete", {p_kind: selected.kind, p_id: selected.id, p_token: selected.token, p_confirmation: confirmation.value}, controller.signal);
            if (!active || operation !== version) return;
            if (response?.saved !== true || response.id !== selected.id) throw new Error("Eliminación no confirmada");
            close(); notice("Registro eliminado definitivamente.");
            if (after) after();
            window.dispatchEvent(new Event("portal-academic-deleted"));
            await cleanup(true, "Registro eliminado definitivamente.");
        } catch (error) {
            if (!active || operation !== version || denied(error)) return;
            uncertain = true;
            message(["22023", "PT409"].includes(error?.code) ? error.message : "No se pudo confirmar la eliminación. Cierra y actualiza la lista antes de repetirla.");
        } finally { if (operation === version) { busy = false; sync(); } }
    }
    confirmation.addEventListener("input", sync);
    form.addEventListener("submit", event => { event.preventDefault(); void submit(); });
    dialog.addEventListener("cancel", event => { event.preventDefault(); if (!busy) close(); });
    for (const id of ["deletionClose", "deletionCancel"]) $(id).addEventListener("click", () => { if (!busy) close(); });
    $("deletionCleanupRetry").addEventListener("click", () => void cleanup(true));
    window.PortalDeletion = Object.freeze({clear, leave() { if (!busy) close(); }, open, show(verify) { clear(); active = true; recheck = verify; void cleanup(); }});
})();
