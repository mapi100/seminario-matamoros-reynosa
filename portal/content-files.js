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
            state.alive = false; state.controller.abort(); for (const url of state.urls) URL.revokeObjectURL(url); state.container.replaceChildren(); states.delete(state);
        }
    }
    function render(container, options) {
        clear(container);
        const state = {container, courseId:options.courseId, topicId:options.topicId, alive:true, controller:new AbortController(), items:[], pending:[], selected:[], urls:new Set(), busy:false, locked:false, loaded:!options.topicId};
        states.add(state); container.classList.add("content-files");
        const heading = node("h4", "Archivos del tema"), list = node("ul", undefined, "content-file-list"), message = node("p", "", "learning-status content-file-message");
        message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite");
        container.append(heading, list, message);
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
            for (const control of container.querySelectorAll("button")) control.disabled = value || state.locked;
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
        function draw() {
            list.replaceChildren();
            for (const file of state.items) {
                const li = node("li"), info = node("span", file.name + " · " + Math.ceil(file.size / 1024) + " KB"), actions = node("div", undefined, "content-file-actions");
                actions.append(button("Descargar " + file.name, () => void download(file)));
                if (options.edit) actions.append(button("Quitar", () => void remove(file)));
                li.append(info, actions); list.append(li);
            }
            cleanup.hidden = !state.pending.length; note(state.items.length ? state.items.length + " archivos disponibles." : "Todavía no hay archivos adjuntos. También puedes añadir un enlace.");
        }
        async function load() {
            if (!state.topicId || state.busy || state.locked) return; busy(true); note("Consultando archivos…");
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
        return Object.freeze({validate,uploadTo,hasSelection:() => state.selected.length > 0});
    }
    window.PortalContentFiles = Object.freeze({render,clear});
})();
