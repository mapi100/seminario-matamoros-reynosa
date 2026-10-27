(function () {
    "use strict";
    const bucket = "portal-content", maxSize = 10 * 1024 * 1024, maxFiles = 5;
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const types = Object.freeze({pdf:"application/pdf",doc:"application/msword",docx:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",ppt:"application/vnd.ms-powerpoint",pptx:"application/vnd.openxmlformats-officedocument.presentationml.presentation",xls:"application/vnd.ms-excel",xlsx:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",rtf:"application/rtf",txt:"text/plain",jpg:"image/jpeg",jpeg:"image/jpeg",png:"image/png",webp:"image/webp",zip:"application/zip"});
    const states = new Set();
    const api = () => window.PortalAuth.getClient();
    function node(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
    function button(text, action) { const el = node("button", text, "learning-button secondary compact"); el.type = "button"; el.addEventListener("click", action); return el; }
    function clear(scope) {
        for (const state of [...states]) if (!scope || scope === state.container || scope.contains(state.container)) {
            state.alive = false; state.previewVersion++; state.pdf?.destroy(); state.controller.abort(); state.container.replaceChildren();
            for (const url of state.urls) URL.revokeObjectURL(url); states.delete(state);
        }
    }
    function render(container, options) {
        clear(container);
        const state = {container, courseId:options.courseId, topicId:options.topicId, alive:true, controller:new AbortController(), items:[], pending:[], selected:[], urls:new Set(), previewVersion:0, previewURL:null, previewLoading:false, pdf:null, busy:false, locked:false, loaded:!options.topicId};
        states.add(state); container.classList.add("content-files");
        container.classList.toggle("content-files-reader", Boolean(options.preview)); container.classList.remove("content-files-preview-open");
        const heading = node("h4", "Archivos del tema"), list = node("ul", undefined, "content-file-list"), message = node("p", "", "learning-status content-file-message");
        message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite");
        container.append(heading, list, message);
        const viewer = node("section", undefined, "content-preview"); viewer.hidden = true; viewer.setAttribute("aria-label", "Vista previa del documento");
        container.append(viewer);
        const input = node("input"); input.type = "file"; input.multiple = true; input.accept = Object.keys(types).map(ext => "." + ext).join(","); input.setAttribute("aria-label", "Seleccionar archivos desde la computadora");
        const selectedList = node("ul", undefined, "content-file-list"), cleanup = button("Limpiar subidas incompletas", () => void cleanPending()), refresh = button("Actualizar archivos", () => void load());
        cleanup.hidden = true; refresh.hidden = !options.topicId;
        if (options.edit) {
            const label = node("label", "Subir archivos desde la computadora"); label.append(input);
            container.append(label, node("p", "Word, PDF, PowerPoint, Excel, imágenes, TXT, RTF o ZIP. Hasta 10 MB por archivo y 5 archivos por tema. Se suben al guardar.", "learning-meta"), selectedList, cleanup, refresh);
        }
        function live() { if (!state.alive) throw new DOMException("Operación cancelada", "AbortError"); }
        function note(text, error = false) { if (state.alive) { message.textContent = text; message.classList.toggle("error", error); } }
        function busy(value) {
            state.busy = value; container.setAttribute("aria-busy", String(value)); input.disabled = value || state.locked || !state.loaded;
            for (const control of container.querySelectorAll("button:not(.content-pdf-control)")) control.disabled = value || state.locked;
        }
        function validateRows(rows) {
            if (!Array.isArray(rows) || rows.length > maxFiles || rows.some(f => !f || !uuid.test(f.id) || typeof f.name !== "string" || !f.name || f.name.length > 160 || !Number.isSafeInteger(f.size) || f.size < 1 || f.size > maxSize || typeof f.object_path !== "string" || f.object_path.length > 400 || !f.object_path.startsWith(state.courseId + "/" + state.topicId + "/"))) throw new Error("Archivos inválidos");
            return rows;
        }
        async function rpc(action, data = {}) {
            const response = await api().rpc("portal_content_files", {p_action:action,p_course:state.courseId,p_topic:state.topicId,p_data:data}).retry(false).abortSignal(state.controller.signal);
            if (response.error) throw {...response.error,status:response.status}; return response.data;
        }
        async function download(file) {
            if (state.busy) return; busy(true); note("Preparando descarga…");
            try {
                const response = await api().storage.from(bucket).download(file.object_path); live();
                if (response.error || !(response.data instanceof Blob) || response.data.size > maxSize) throw response.error || new Error("Descarga inválida");
                const url = URL.createObjectURL(new Blob([response.data], {type:"application/octet-stream"})); state.urls.add(url);
                const anchor = node("a"); anchor.href = url; anchor.download = file.name; anchor.hidden = true; container.append(anchor); anchor.click(); anchor.remove();
                setTimeout(() => { URL.revokeObjectURL(url); state.urls.delete(url); }, 1000); note("Descarga preparada.");
            } catch { note("No se pudo descargar el archivo. Comprueba tu conexión y tu acceso al curso.", true); }
            finally { if (state.alive) busy(false); }
        }
        function isPDF(file) { return file.mimetype === "application/pdf" || /\.pdf$/i.test(file.name); }
        function closePreview() {
            state.previewVersion++; state.pdf?.destroy(); state.pdf = null; viewer.replaceChildren(); viewer.hidden = true;
            container.classList.remove("content-files-preview-open");
            if (state.previewURL) { URL.revokeObjectURL(state.previewURL); state.urls.delete(state.previewURL); state.previewURL = null; }
            if (state.previewLoading) { state.previewLoading = false; busy(false); }
        }
        async function preview(file) {
            if (state.busy || state.locked) return;
            closePreview(); const version = state.previewVersion;
            viewer.hidden = false; viewer.append(node("p", "Cargando vista previa de " + file.name + "…", "learning-status"));
            viewer.setAttribute("aria-busy", "true"); state.previewLoading = true; busy(true);
            try {
                const response = await api().storage.from(bucket).download(file.object_path); live();
                if (version !== state.previewVersion) return;
                if (response.error || !(response.data instanceof Blob) || response.data.size < 1 || response.data.size > maxSize) throw new Error("Vista previa no disponible");
                // El tipo lo fija el lector; nunca se incrusta HTML ni una URL pública de Storage.
                const signature = await response.data.slice(0, 1024).text(); live();
                if (version !== state.previewVersion) return;
                if (!signature.includes("%PDF-")) throw new Error("El archivo no es un PDF");
                const pdfBlob = new Blob([response.data], {type:"application/pdf"}), url = URL.createObjectURL(pdfBlob);
                state.urls.add(url); state.previewURL = url;
                const bar = node("div", undefined, "content-preview-toolbar"), tools = node("div", undefined, "content-file-actions");
                bar.append(node("span", file.name, "content-preview-name"));
                const open = node("a", "Abrir PDF en otra pestaña", "learning-button secondary compact");
                open.href = url; open.target = "_blank"; open.rel = "noopener noreferrer";
                if (options.preview && state.items.length === 1) {
                    const get = button("Descargar " + file.name, () => void download(file)); get.disabled = state.busy; tools.append(get);
                }
                tools.append(open, button("Ampliar PDF", async () => {
                    try { if (document.fullscreenElement === viewer) await document.exitFullscreen(); else await viewer.requestFullscreen(); }
                    catch { note("Puedes ampliar el documento abriéndolo en otra pestaña."); }
                }), button("Cerrar vista previa", () => { closePreview(); list.querySelector("button")?.focus(); }));
                bar.append(tools);
                const pages = node("div", undefined, "content-pdf-document"); pages.setAttribute("aria-label", "Vista previa de " + file.name);
                viewer.replaceChildren(bar, pages);
                container.classList.add("content-files-preview-open");
                state.pdf = window.PortalPDFPreview.render(pages, pdfBlob); await state.pdf.ready; live();
                if (version !== state.previewVersion) return;
                note("Vista previa del PDF disponible.");
            } catch {
                if (state.alive && version === state.previewVersion) {
                    container.classList.remove("content-files-preview-open");
                    state.pdf?.destroy(); state.pdf = null;
                    if (state.previewURL) { URL.revokeObjectURL(state.previewURL); state.urls.delete(state.previewURL); state.previewURL = null; }
                    viewer.replaceChildren(node("p", "No se pudo mostrar el PDF. Comprueba tu conexión y tu acceso al curso; también puedes intentar descargarlo.", "learning-status error"), button("Reintentar vista previa", () => void preview(file)));
                }
            } finally { if (state.alive && version === state.previewVersion) { state.previewLoading = false; viewer.setAttribute("aria-busy", "false"); busy(false); } }
        }
        function draw() {
            list.replaceChildren();
            container.classList.toggle("content-files-single-pdf", state.items.length === 1 && isPDF(state.items[0]));
            for (const file of state.items) {
                const li = node("li"), info = node("span", file.name + " · " + Math.ceil(file.size / 1024) + " KB"), actions = node("div", undefined, "content-file-actions");
                if (isPDF(file)) actions.append(button("Ver PDF: " + file.name, () => void preview(file)));
                actions.append(button("Descargar " + file.name, () => void download(file)));
                if (options.edit) actions.append(button("Quitar", () => void remove(file)));
                li.append(info, actions); list.append(li);
            }
            cleanup.hidden = !state.pending.length; note(state.items.length ? state.items.length + " archivos disponibles." : "Todavía no hay archivos adjuntos. También puedes añadir un enlace.");
        }
        async function load() {
            if (!state.topicId || state.busy || state.locked) return; busy(true); note("Consultando archivos…");
            closePreview();
            try {
                const data = await rpc("list"); live(); state.items = validateRows(data?.items);
                if (!Array.isArray(data.pending) || data.pending.length > maxFiles || data.pending.some(path => typeof path !== "string" || !path.startsWith(state.courseId + "/" + state.topicId + "/") || path.length > 400)) throw new Error("Subidas inválidas");
                state.pending = data.pending; state.loaded = true; draw();
            } catch (error) { state.loaded = false; note(["42883","PGRST202","42P01"].includes(error?.code) ? "La subida de archivos todavía necesita habilitarse. Puedes guardar texto y enlaces." : "No se pudieron consultar los archivos. Pulsa Actualizar archivos.", true); }
            finally { if (state.alive) busy(false); }
        }
        async function remove(file) {
            if (state.busy || state.locked || !window.confirm("¿Quitar " + file.name + " de este tema?")) return;
            busy(true); note("Quitando archivo…"); let removed = false;
            closePreview();
            try {
                const result = await rpc("remove", {id:file.id}); live(); if (result?.saved !== true) throw new Error("Cambio no confirmado"); removed = true;
                const response = await api().storage.from(bucket).remove([file.object_path]); live();
                busy(false); await load();
                if (response.error) note("El archivo se quitó del tema. Control Escolar podrá completar la limpieza del almacenamiento desde el aviso de archivos pendientes.", true);
            } catch { if (state.alive) { busy(false); await load(); note(removed ? "El archivo fue retirado; puede quedar una limpieza pendiente." : "No se pudo confirmar el cambio. Revisa la lista antes de repetirlo.", true); } }
            finally { if (state.alive) busy(false); }
        }
        async function cleanPending() {
            if (!state.pending.length || state.busy || state.locked) return; busy(true); note("Limpiando subidas incompletas…");
            try { const response = await api().storage.from(bucket).remove(state.pending); live(); if (response.error) throw response.error; busy(false); await load(); }
            catch { note("No se pudo completar la limpieza. Actualiza los archivos e inténtalo de nuevo.", true); }
            finally { if (state.alive) busy(false); }
        }
        function selected() {
            selectedList.replaceChildren();
            for (const entry of state.selected) { const item = node("li", entry.file.name + (entry.done ? " · Subido" : " · Pendiente")); selectedList.append(item); }
        }
        input.addEventListener("change", () => { if (state.locked) return; state.selected = [...input.files].map(file => ({file,done:false})); selected(); validate(); });
        function validate() {
            if (state.busy) { note("Espera a que termine la operación de archivos.", true); return false; }
            if (!state.selected.length) return true;
            if (!state.loaded) { note("Primero actualiza la lista de archivos.", true); return false; }
            if (state.items.length + state.selected.length > maxFiles) { note("Cada tema admite hasta 5 archivos. Selecciona menos archivos o quita uno existente.", true); return false; }
            for (const {file} of state.selected) {
                const name = file.name.normalize("NFC").trim(), extension = name.split(".").pop().toLowerCase();
                if (!Object.hasOwn(types, extension) || !name || name.length > 160 || /[\u0000-\u001f\u007f/\\]/u.test(name) || file.size < 1 || file.size > maxSize) { note("Revisa " + file.name + ": usa un formato admitido y un tamaño entre 1 byte y 10 MB.", true); return false; }
            }
            return true;
        }
        async function uploadTo(topicId) {
            live(); if (!validate() || !uuid.test(topicId)) throw new Error("Revisa los archivos seleccionados");
            state.topicId = topicId; state.locked = true; busy(true);
            try {
                for (const entry of state.selected) {
                    live(); if (entry.done) continue;
                    const name = entry.file.name.normalize("NFC").trim(), extension = name.split(".").pop().toLowerCase();
                    const attach = async () => { const result = await rpc("attach", {object_path:entry.path,name}); live(); if (result?.saved !== true || !uuid.test(result.id)) throw new Error("Registro no confirmado"); entry.done = true; selected(); };
                    if (entry.path) {
                        try { await attach(); continue; } catch (error) { if (error?.code !== "PT404") throw error; }
                    } else entry.path = [state.courseId, topicId, crypto.randomUUID(), crypto.randomUUID() + "." + extension].join("/");
                    note("Subiendo " + name + "…");
                    const response = await api().storage.from(bucket).upload(entry.path, entry.file, {contentType:types[extension],upsert:false,cacheControl:"0"}); live();
                    if (response.error) throw Object.assign(new Error(response.error.message || "No se pudo subir"), {source:"storage",status:response.error.status});
                    note("Registrando " + name + "…"); await attach();
                }
            } finally { if (state.alive) busy(false); }
        }
        if (options.items) { try { state.items = validateRows(options.items); draw(); } catch { note("No se pudieron mostrar los archivos del tema.", true); } }
        else draw();
        if (options.edit && state.topicId) void load(); else { state.loaded = true; busy(false); }
        if (options.preview && !options.edit) { const first = state.items.find(isPDF); if (first) void preview(first); }
        return Object.freeze({validate,uploadTo,hasSelection:() => state.selected.length > 0});
    }
    window.PortalContentFiles = Object.freeze({render,clear});
})();
