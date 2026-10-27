(function () {
    "use strict";

    const editor = document.getElementById("gradeEditor");
    const title = document.getElementById("gradeEditorTitle");
    const published = document.getElementById("gradePublished");
    const draftState = document.getElementById("gradeDraftState");
    const form = document.getElementById("gradeForm");
    const input = document.getElementById("gradeScore");
    const save = document.getElementById("gradeSave");
    const publish = document.getElementById("gradePublish");
    const reload = document.getElementById("gradeReload");
    const message = document.getElementById("gradeMessage");
    let version = 0;
    let controller;
    let selection;
    let snapshot;
    let busy = false;
    let needsReload = true;

    function inputScore() {
        try { return window.PortalGradeScale.toWire(input.value, snapshot?.draft_score ?? snapshot?.published_score); } catch { return null; }
    }

    function canPublish() {
        return Boolean(snapshot && !busy && !needsReload && snapshot.revision > 0 &&
            snapshot.has_unpublished_changes && snapshot.draft_score !== null &&
            inputScore() === snapshot.draft_score);
    }

    function syncControls() {
        form.setAttribute("aria-busy", String(busy));
        input.disabled = busy || needsReload || !snapshot;
        save.disabled = busy || needsReload || !snapshot;
        publish.disabled = !canPublish();
        reload.disabled = busy;
    }

    function showMessage(text, type = "") {
        message.textContent = text;
        message.className = "grade-message" + (type ? " " + type : "");
    }

    function clear() {
        version += 1;
        controller?.abort();
        controller = undefined;
        selection = undefined;
        snapshot = undefined;
        busy = false;
        needsReload = true;
        editor.hidden = true;
        title.textContent = "";
        published.textContent = "";
        draftState.textContent = "";
        input.value = "";
        input.setCustomValidity("");
        reload.hidden = true;
        showMessage("");
        syncControls();
    }

    function parseState(data) {
        if (!Array.isArray(data) || data.length !== 1) throw new Error("Respuesta de calificación inválida");
        const state = data[0];
        const validScore = value => value === null || (typeof value === "number" &&
            Number.isFinite(value) && value >= 0 && value <= 100);
        if (
            !state || state.enrollment_id !== selection.enrollmentId ||
            !validScore(state.published_score) || !validScore(state.draft_score) ||
            !Number.isInteger(state.revision) || state.revision < 0 || state.revision > 2147483647 ||
            typeof state.has_unpublished_changes !== "boolean" ||
            (state.revision > 0 && state.draft_score === null) ||
            (state.has_unpublished_changes && (state.revision === 0 || state.draft_score === null))
        ) throw new Error("Estado de calificación inválido");
        return state;
    }

    function render(state) {
        snapshot = state;
        needsReload = false;
        published.textContent = state.published_score === null
            ? "Sin calificación publicada"
            : "Publicada: " + window.PortalGradeScale.format(state.published_score) + " / 10";
        draftState.textContent = state.revision === 0
            ? "Guarda un borrador antes de publicar."
            : state.has_unpublished_changes
                ? "Borrador guardado: " + window.PortalGradeScale.format(state.draft_score) + " / 10. Pendiente de publicación."
                : "Borrador publicado: " + window.PortalGradeScale.format(state.draft_score) + " / 10.";
        const value = state.draft_score ?? state.published_score;
        input.value = value === null ? "" : window.PortalGradeScale.format(value);
        input.setCustomValidity("");
        reload.hidden = true;
    }

    function unavailable(text, error) {
        // Un fallo de red tras una escritura no demuestra si se guardó o no.
        // Obligar a leer el estado evita reenviar la misma operación a ciegas.
        snapshot = undefined;
        needsReload = true;
        input.value = "";
        published.textContent = "";
        draftState.textContent = "";
        reload.hidden = false;
        showMessage(text, "error");
        if (error?.code === "42501" || error?.status === 403) {
            const recheck = selection?.recheckAccess;
            clear();
            if (recheck) void recheck();
        }
    }

    async function load() {
        if (!selection || busy || editor.hidden) return;
        const operation = ++version;
        controller = new AbortController();
        busy = true;
        needsReload = true;
        syncControls();
        showMessage("Consultando calificación…");
        try {
            const { data, error } = await window.PortalAuth.getClient()
                .rpc("get_teaching_grade", {
                    p_assignment_id: selection.assignmentId,
                    p_enrollment_id: selection.enrollmentId
                })
                .abortSignal(controller.signal);
            if (operation !== version || editor.hidden) return;
            if (error) throw error;
            render(parseState(data));
            showMessage("");
        } catch (error) {
            if (operation !== version || editor.hidden) return;
            unavailable("No fue posible consultar la calificación. Vuelve a consultar para intentarlo de nuevo.", error);
        } finally {
            if (operation === version) {
                busy = false;
                syncControls();
            }
        }
    }

    async function write(action) {
        if (!selection || !snapshot || busy || needsReload || editor.hidden) return;
        if (action === "save" && (!form.reportValidity() || inputScore() === null)) return;
        if (action === "publish" && !canPublish()) return;
        const previousRevision = snapshot.revision;
        const operation = ++version;
        const args = {
            p_assignment_id: selection.assignmentId,
            p_enrollment_id: selection.enrollmentId,
            p_expected_revision: previousRevision
        };
        if (action === "save") args.p_score = inputScore();
        controller = new AbortController();
        busy = true;
        needsReload = true;
        syncControls();
        showMessage(action === "save" ? "Guardando borrador…" : "Publicando calificación…");
        try {
            const { data, error } = await window.PortalAuth.getClient()
                .rpc(action === "save" ? "save_teaching_grade" : "publish_teaching_grade", args)
                .retry(false)
                .abortSignal(controller.signal);
            if (operation !== version || editor.hidden) return;
            if (error) throw error;
            const state = parseState(data);
            if (state.revision !== previousRevision + 1) throw new Error("Revisión inesperada");
            render(state);
            showMessage(action === "save"
                ? "Borrador guardado. La calificación publicada del alumno conserva su valor."
                : "Calificación publicada. El alumno podrá consultarla al actualizar su portal.", "success");
        } catch (error) {
            if (operation !== version || editor.hidden) return;
            unavailable(error?.code === "PT409" || error?.status === 409
                ? "La calificación cambió en otra sesión. Vuelve a consultar antes de continuar."
                : "No se pudo confirmar la operación. Vuelve a consultar la calificación antes de continuar.", error);
        } finally {
            if (operation === version) {
                busy = false;
                syncControls();
            }
        }
    }

    function open(context) {
        clear();
        selection = context;
        title.textContent = "Calificar a " + context.studentName + " — " + context.courseName;
        editor.hidden = false;
        void load();
        editor.scrollIntoView({ block: "nearest" });
    }

    input.addEventListener("input", function () {
        input.setCustomValidity(input.value && inputScore() === null
            ? "Escribe una nota de 0 a 10 con un decimal." : "");
        syncControls();
    });
    form.addEventListener("submit", function (event) {
        event.preventDefault();
        void write("save");
    });
    publish.addEventListener("click", function () { void write("publish"); });
    reload.addEventListener("click", function () { void load(); });
    document.getElementById("gradeCancel").addEventListener("click", clear);

    window.PortalGradeEditor = Object.freeze({ clear, open });
})();
