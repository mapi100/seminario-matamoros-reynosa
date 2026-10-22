(function () {
    "use strict";

    const bucket = "portal-coursework";
    const maxSize = 5 * 1024 * 1024;
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const types = Object.freeze({
        pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
        txt: "text/plain", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    });
    const instances = new Set();
    const byContainer = new WeakMap();

    function node(tag, text, className) {
        const result = document.createElement(tag);
        if (text !== undefined) result.textContent = text;
        if (className) result.className = className;
        return result;
    }
    function button(text, handler, className = "learning-file-button") {
        const result = node("button", text, className);
        result.type = "button";
        result.addEventListener("click", handler);
        return result;
    }
    function dispose(state) {
        state.alive = false;
        state.version++;
        state.controller.abort();
        for (const url of state.urls) URL.revokeObjectURL(url);
        state.urls.clear();
        state.container.replaceChildren();
        instances.delete(state);
        byContainer.delete(state.container);
    }
    function clear(scope) {
        for (const state of [...instances]) {
            if (!scope || scope === state.container || scope.contains(state.container)) dispose(state);
        }
    }

    function render(container, options) {
        if (!(container instanceof HTMLElement)) return;
        if (byContainer.has(container)) dispose(byContainer.get(container));
        container.replaceChildren();
        if (!options || !uuid.test(options.courseId) || !uuid.test(options.assignmentId) ||
            (options.enrollmentId && !uuid.test(options.enrollmentId))) return;
        const state = {
            container, options: { ...options }, alive: true, version: 0, controller: new AbortController(),
            urls: new Set(), busy: false, uncertain: false, items: [], canUpload: false, canRemove: false
        };
        instances.add(state);
        byContainer.set(container, state);
        container.classList.add("learning-files");
        const heading = node("h4", "Archivos de la entrega");
        const message = node("p", "Consultando archivos…", "learning-file-message");
        message.setAttribute("role", "status");
        message.setAttribute("aria-live", "polite");
        const list = node("ul", undefined, "learning-file-list");
        const upload = node("form", undefined, "learning-file-upload");
        upload.hidden = true;
        const label = node("label", "Adjuntar archivo");
        const input = node("input");
        input.type = "file";
        input.accept = ".pdf,.jpg,.jpeg,.png,.txt,.docx";
        input.required = true;
        label.append(input);
        const help = node("p", "PDF, JPG, PNG, TXT o DOCX. Hasta 5 MB por archivo y 3 archivos por tarea.", "learning-file-help");
        const save = node("button", "Subir y entregar archivo", "learning-file-button learning-file-primary");
        save.type = "submit";
        upload.append(label, help, save);
        const refresh = button("Actualizar archivos", () => { if (!state.busy) void load(); });
        container.append(heading, message, list);
        if (!state.options.canManage) container.append(upload);
        container.append(refresh);

        function live(operation) { return state.alive && operation === state.version; }
        function note(text, error = false) {
            message.textContent = text;
            message.classList.toggle("error", error);
        }
        function setBusy(value) {
            state.busy = value;
            container.setAttribute("aria-busy", String(value));
            input.disabled = value || state.uncertain;
            save.disabled = value || state.uncertain;
            refresh.disabled = value;
            for (const control of list.querySelectorAll("button")) control.disabled = value || state.uncertain;
        }
        async function rpc(action, data = {}) {
            let request = window.PortalAuth.getClient().rpc("portal_learning_files", {
                p_action: action, p_course: state.options.courseId,
                p_assignment: state.options.assignmentId, p_data: data
            });
            if (action !== "list") request = request.retry(false);
            const result = await request.abortSignal(state.controller.signal);
            if (result.error) throw result.error;
            return result.data;
        }
        function validateRows(result) {
            if (!result || !Array.isArray(result.items) || result.items.length > 3) throw new Error("Respuesta inválida");
            const prefix = state.options.courseId + "/" + state.options.assignmentId + "/";
            for (const row of result.items) {
                if (!row || !uuid.test(row.id) || typeof row.name !== "string" || !row.name || row.name.length > 160 ||
                    !Number.isInteger(row.size) || row.size < 1 || row.size > maxSize ||
                    typeof row.object_path !== "string" || !row.object_path.startsWith(prefix) || row.object_path.length > 400)
                    throw new Error("Archivo inválido");
            }
            return result.items;
        }
        function changed() {
            window.dispatchEvent(new CustomEvent("portal-learning-files-changed", {
                detail: { courseId: state.options.courseId, assignmentId: state.options.assignmentId }
            }));
        }
        function draw() {
            list.replaceChildren();
            for (const row of state.items) {
                const li = node("li");
                const description = node("div");
                description.append(node("strong", row.name), node("span", Math.ceil(row.size / 1024) + " KB"));
                const actions = node("div", undefined, "learning-file-actions");
                actions.append(button("Descargar", () => void download(row)));
                if (!state.options.canManage && state.canRemove) actions.append(button("Retirar", () => void remove(row)));
                li.append(description, actions);
                list.append(li);
            }
            upload.hidden = state.options.canManage || !state.canUpload;
            if (!state.items.length) note(state.options.canManage && !state.options.enrollmentId
                ? "Selecciona un alumno para consultar sus archivos."
                : "Todavía no hay archivos adjuntos. También puedes entregar texto o un enlace.");
            else note(state.items.length + (state.items.length === 1 ? " archivo adjunto." : " archivos adjuntos."));
        }
        async function load() {
            const operation = ++state.version;
            setBusy(true);
            note("Consultando archivos…");
            try {
                const result = await rpc("list", state.options.enrollmentId ? { enrollment_id: state.options.enrollmentId } : {});
                if (!live(operation)) return;
                state.items = validateRows(result);
                state.canUpload = result.can_upload === true;
                state.canRemove = result.can_remove === true;
                state.uncertain = false;
                draw();
            } catch (error) {
                if (!live(operation)) return;
                list.replaceChildren(); upload.hidden = true;
                state.items = [];
                note(["42883", "PGRST202", "42P01"].includes(error.code)
                    ? "Los adjuntos todavía no están habilitados. Puedes utilizar la entrega por texto o enlace."
                    : "No fue posible consultar los archivos. Actualiza para volver a comprobar el acceso.", true);
            } finally { if (live(operation)) setBusy(false); }
        }
        async function download(row) {
            if (state.busy || state.uncertain) return;
            const operation = ++state.version;
            setBusy(true); note("Preparando descarga…");
            try {
                const { data, error } = await window.PortalAuth.getClient().storage.from(bucket).download(row.object_path);
                if (!live(operation)) return;
                if (error || !(data instanceof Blob) || data.size > maxSize) throw error || new Error("Descarga inválida");
                // Forzar descarga; nunca abrir contenido de alumnos dentro del portal.
                const url = URL.createObjectURL(new Blob([data], { type: "application/octet-stream" }));
                state.urls.add(url);
                const anchor = node("a");
                anchor.href = url; anchor.download = row.name; anchor.hidden = true;
                container.append(anchor); anchor.click(); anchor.remove();
                window.setTimeout(() => { URL.revokeObjectURL(url); state.urls.delete(url); }, 1000);
                note("Descarga preparada.");
            } catch {
                if (live(operation)) note("No se pudo descargar el archivo. Comprueba tu conexión y tu acceso al curso.", true);
            } finally { if (live(operation)) setBusy(false); }
        }
        async function remove(row) {
            if (state.busy || state.uncertain) return;
            const operation = ++state.version;
            setBusy(true); note("Retirando archivo…");
            let registered = false;
            try {
                await rpc("remove", { id: row.id });
                if (!live(operation)) return;
                registered = true;
                const cleanup = await window.PortalAuth.getClient().storage.from(bucket).remove([row.object_path]);
                if (!live(operation)) return;
                await load();
                if (state.alive && cleanup.error) {
                    note("El adjunto se retiró de la entrega, pero no se pudo liberar su espacio. Contacta al administrador del portal.", true);
                } else if (state.alive) changed();
            } catch (error) {
                if (!live(operation)) return;
                if (error.code === "22023") note(error.message || "Conserva otro archivo o texto antes de retirar este adjunto.", true);
                else {
                    state.uncertain = !registered;
                    note("No se pudo confirmar el cambio. Actualiza los archivos antes de intentarlo de nuevo.", true);
                }
            } finally { if (live(operation)) setBusy(false); }
        }
        upload.addEventListener("submit", async event => {
            event.preventDefault();
            if (state.busy || state.uncertain || !state.canUpload || state.options.canManage) return;
            const file = input.files && input.files[0];
            if (!file) return;
            const originalName = file.name.normalize("NFC").trim();
            const extension = originalName.split(".").pop().toLowerCase();
            if (!Object.hasOwn(types, extension) || !originalName || originalName.length > 160 || /[\x00-\x1f\x7f/\\]/.test(originalName) || file.size < 1 || file.size > maxSize) {
                note("Selecciona un PDF, JPG, PNG, TXT o DOCX de hasta 5 MB.", true); return;
            }
            const operation = ++state.version;
            setBusy(true); note("Subiendo archivo…");
            let path, attemptedAttach = false;
            try {
                const client = window.PortalAuth.getClient();
                const userResult = await client.auth.getUser();
                if (!live(operation)) return;
                if (userResult.error || !uuid.test(userResult.data?.user?.id)) throw new Error("Sesión no válida");
                path = [state.options.courseId, state.options.assignmentId, userResult.data.user.id,
                    crypto.randomUUID(), crypto.randomUUID() + "." + extension].join("/");
                const result = await client.storage.from(bucket).upload(path, file, { contentType: types[extension], upsert: false, cacheControl: "0" });
                if (!live(operation)) return;
                if (result.error) throw result.error;
                note("Registrando entrega…"); attemptedAttach = true;
                await rpc("attach", { object_path: path, name: originalName });
                if (!live(operation)) return;
                input.value = "";
                await load();
                if (state.alive) changed();
            } catch (error) {
                if (!live(operation)) return;
                if (attemptedAttach) {
                    // Un fallo de red puede ocurrir después del commit. No borrar ni reintentar.
                    state.uncertain = true;
                    note("No se pudo confirmar el registro. Actualiza los archivos antes de subirlo otra vez.", true);
                } else note("No se pudo subir el archivo. Comprueba su tamaño, tu conexión y la fecha límite.", true);
            } finally { if (live(operation)) setBusy(false); }
        });
        void load();
    }
    window.PortalLearningFiles = Object.freeze({ render, clear });
})();
