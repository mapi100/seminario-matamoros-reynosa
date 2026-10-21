(function () {
    "use strict";

    const section = document.getElementById("controlSection");
    const link = document.getElementById("controlLink");
    const pageSize = 20;
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const dateFormat = new Intl.DateTimeFormat("es-MX", {
        day: "numeric", month: "short", year: "numeric", timeZone: "UTC"
    });
    let active = false;
    let recheckAccess;

    function validDate(value) {
        if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value < "0001-01-01") return false;
        const date = new Date(value + "T00:00:00Z");
        return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
    }

    function text(value, length) {
        return typeof value === "string" && value.trim().length > 0 &&
            [...value].length <= length && !/[\u0000-\u001f\u007f-\u009f]/.test(value);
    }

    function validRecord(record, kind) {
        if (!record || typeof record.id !== "string" || !uuid.test(record.id) ||
            typeof record.created_at !== "string" || !Number.isFinite(Date.parse(record.created_at))) return false;
        return kind === "subject"
            ? text(record.code, 40) && text(record.name, 160)
            : text(record.name, 120) && validDate(record.starts_on) && validDate(record.ends_on) && record.ends_on >= record.starts_on;
    }

    function catalog(kind) {
        return {
            kind, form: document.getElementById(kind + "Form"),
            message: document.getElementById(kind + "Message"),
            status: document.getElementById(kind + "ListStatus"),
            list: document.getElementById(kind + "List"),
            create: document.getElementById(kind + "Create"),
            refresh: document.getElementById(kind + "Refresh"),
            more: document.getElementById(kind + "More"),
            version: 0, controller: undefined, busy: false,
            loaded: false, uncertain: false, offset: 0
        };
    }

    const catalogs = [catalog("period"), catalog("subject")];

    function showMessage(state, value, type = "") {
        state.message.textContent = value;
        state.message.className = "control-message" + (type ? " " + type : "");
    }

    function sync(state) {
        state.form.setAttribute("aria-busy", String(state.busy));
        for (const field of state.form.querySelectorAll("input")) {
            field.disabled = !active || state.busy || !state.loaded || state.uncertain;
        }
        state.create.disabled = !active || state.busy || !state.loaded || state.uncertain;
        state.refresh.disabled = !active || state.busy;
        state.more.disabled = !active || state.busy;
    }

    function clear() {
        active = false;
        recheckAccess = undefined;
        section.hidden = true;
        link.hidden = true;
        for (const state of catalogs) {
            state.version += 1;
            state.controller?.abort();
            state.controller = undefined;
            state.busy = false;
            state.loaded = false;
            state.uncertain = false;
            state.offset = 0;
            state.form.reset();
            for (const field of state.form.querySelectorAll("input")) field.setCustomValidity("");
            state.list.replaceChildren();
            state.status.textContent = "";
            state.status.className = "control-list-status";
            state.more.hidden = true;
            showMessage(state, "");
            sync(state);
        }
    }

    function forbidden(error) {
        if (error?.code !== "42501" && ![401, 403].includes(error?.status)) return false;
        const verifyAccess = recheckAccess;
        clear();
        if (verifyAccess) void verifyAccess();
        return true;
    }

    function recordItem(record, kind) {
        if (!validRecord(record, kind)) throw new Error("Registro de catálogo inválido");
        const item = document.createElement("li");
        item.className = kind === "period" ? "period-item" : "catalog-subject";
        if (kind === "subject") {
            const code = document.createElement("span");
            code.className = "subject-code";
            code.textContent = record.code;
            item.append(code);
        }
        const name = document.createElement("h4");
        name.className = kind + "-name";
        name.textContent = record.name;
        item.append(name);
        if (kind === "period") {
            const dates = document.createElement("p");
            dates.className = "period-dates";
            dates.textContent = dateFormat.format(new Date(record.starts_on)) + " – " + dateFormat.format(new Date(record.ends_on));
            item.append(dates);
        }
        return item;
    }

    async function load(state, reset = true, preserveMessage = false) {
        if (!active || state.busy) return;
        const operation = ++state.version;
        state.controller = new AbortController();
        state.busy = true;
        if (reset) {
            state.offset = 0;
            state.list.replaceChildren();
            state.loaded = false;
        }
        sync(state);
        if (!preserveMessage) showMessage(state, "");
        state.status.className = "control-list-status";
        state.status.textContent = state.kind === "period" ? "Consultando periodos…" : "Consultando materias…";
        try {
            let query = window.PortalAuth.getClient()
                .from(state.kind === "period" ? "academic_periods" : "subjects")
                .select(state.kind === "period" ? "id, name, starts_on, ends_on, created_at" : "id, code, name, created_at")
                .order(state.kind === "period" ? "starts_on" : "code", { ascending: state.kind === "subject" })
                .order("id", { ascending: true });
            const response = await query.range(state.offset, state.offset + pageSize).abortSignal(state.controller.signal);
            if (!active || operation !== state.version) return;
            if (response.error) throw { ...response.error, status: response.status };
            if (!Array.isArray(response.data)) throw new Error("Respuesta de catálogo inválida");
            const items = response.data.slice(0, pageSize).map(record => recordItem(record, state.kind));
            state.list.append(...items);
            state.offset += items.length;
            state.loaded = true;
            state.uncertain = false;
            state.more.hidden = response.data.length <= pageSize;
            state.status.textContent = state.offset
                ? state.offset + (state.kind === "period"
                    ? state.offset === 1 ? " periodo mostrado." : " periodos mostrados."
                    : state.offset === 1 ? " materia mostrada." : " materias mostradas.")
                : state.kind === "period" ? "Todavía no hay periodos registrados." : "Todavía no hay materias registradas.";
        } catch (error) {
            if (!active || operation !== state.version || forbidden(error)) return;
            state.list.replaceChildren();
            state.loaded = false;
            state.offset = 0;
            state.more.hidden = true;
            state.status.className = "control-list-status error";
            state.status.textContent = "No fue posible consultar la lista. Pulsa Actualizar lista para reintentar.";
        } finally {
            if (operation === state.version) {
                state.busy = false;
                sync(state);
            }
        }
    }

    function validate(state) {
        for (const field of state.form.querySelectorAll("input")) field.setCustomValidity("");
        const name = document.getElementById(state.kind + "Name");
        if (!text(name.value, state.kind === "period" ? 120 : 160)) {
            name.setCustomValidity("Escribe un nombre válido, sin tabulaciones ni saltos de línea.");
        }
        if (state.kind === "subject") {
            const code = document.getElementById("subjectCode");
            if (!text(code.value, 40)) code.setCustomValidity("Escribe un código válido de hasta 40 caracteres.");
        } else {
            const start = document.getElementById("periodStart");
            const end = document.getElementById("periodEnd");
            if (!validDate(start.value)) start.setCustomValidity("Selecciona una fecha de inicio válida.");
            if (!validDate(end.value)) end.setCustomValidity("Selecciona una fecha de fin válida.");
            if (validDate(start.value) && validDate(end.value) && end.value < start.value) {
                end.setCustomValidity("La fecha de fin debe ser igual o posterior al inicio.");
            }
        }
        return state.form.reportValidity();
    }

    async function create(state) {
        if (!active || state.busy || !state.loaded || state.uncertain || !validate(state)) return;
        const operation = ++state.version;
        state.controller = new AbortController();
        state.busy = true;
        sync(state);
        showMessage(state, "Guardando…");
        const args = state.kind === "period" ? {
            p_name: document.getElementById("periodName").value.trim(),
            p_starts_on: document.getElementById("periodStart").value,
            p_ends_on: document.getElementById("periodEnd").value
        } : {
            p_code: document.getElementById("subjectCode").value.trim(),
            p_name: document.getElementById("subjectName").value.trim()
        };
        try {
            const response = await window.PortalAuth.getClient()
                .rpc(state.kind === "period" ? "create_academic_period" : "create_subject", args)
                .retry(false)
                .abortSignal(state.controller.signal);
            if (!active || operation !== state.version) return;
            if (response.error) throw { ...response.error, status: response.status };
            if (!Array.isArray(response.data) || response.data.length !== 1 || !validRecord(response.data[0], state.kind)) {
                throw new Error("No se pudo confirmar el registro creado");
            }
            const record = response.data[0];
            state.form.reset();
            showMessage(state, state.kind === "period"
                ? "Periodo creado: " + record.name + "."
                : "Materia creada: " + record.code + " — " + record.name + ".", "success");
            state.busy = false;
            void load(state, true, true);
        } catch (error) {
            if (!active || operation !== state.version || forbidden(error)) return;
            if (error?.code === "PT409" || error?.code === "23505") {
                showMessage(state, state.kind === "period"
                    ? "Ya existe un periodo con ese nombre. Revisa la lista o cambia el nombre."
                    : "Ya existe una materia con ese código. Revisa la lista o cambia el código.", "error");
            } else if (error?.code === "22023") {
                showMessage(state, "Revisa los datos del formulario e inténtalo nuevamente.", "error");
            } else {
                state.uncertain = true;
                showMessage(state, "No se pudo confirmar la operación. Actualiza la lista y revisa si el registro se creó antes de intentarlo de nuevo.", "error");
            }
        } finally {
            if (operation === state.version) {
                state.busy = false;
                sync(state);
            }
        }
    }

    function show(verifyAccess) {
        clear();
        active = true;
        recheckAccess = verifyAccess;
        section.hidden = false;
        link.hidden = false;
        for (const state of catalogs) void load(state);
    }

    for (const state of catalogs) {
        state.form.addEventListener("submit", function (event) {
            event.preventDefault();
            void create(state);
        });
        state.form.addEventListener("input", function () {
            for (const field of state.form.querySelectorAll("input")) field.setCustomValidity("");
        });
        state.refresh.addEventListener("click", function () { void load(state); });
        state.more.addEventListener("click", function () { void load(state, false); });
    }

    window.PortalControl = Object.freeze({ clear, show });
})();
