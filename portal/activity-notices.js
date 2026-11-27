(function () {
    "use strict";

    const $ = id => document.getElementById(id);
    const bell = $("activityNoticeBell");
    const badge = $("activityNoticeBadge");
    const panel = $("activityNoticePanel");
    const status = $("activityNoticeStatus");
    const list = $("activityNoticeList");
    const markAll = $("activityNoticeReadAll");
    const more = $("activityNoticeMore");
    const retry = $("activityNoticeRetry");
    const date = new Intl.DateTimeFormat("es-MX", {
        dateStyle: "medium", timeStyle: "short", timeZone: "America/Matamoros"
    });
    const titles = Object.freeze({
        final_corrected: "Calificación final corregida",
        personal_updated: "Datos personales actualizados"
    });
    const missing = new Set(["PGRST202", "42883", "42P01"]);
    let session, timer, reading, writing, installed;
    let viewing = false, loaded = false, needsRefresh = false, unread = 0, before = null, items = [];

    function node(tag, text) {
        const element = document.createElement(tag);
        if (text != null) element.textContent = text;
        return element;
    }

    function note(text, error = false) {
        status.textContent = text;
        status.classList.toggle("error", error);
    }

    function sync() {
        const busy = Boolean(reading || writing);
        bell.hidden = !session || installed !== true;
        badge.hidden = unread === 0;
        badge.textContent = unread > 99 ? "99+" : String(unread);
        const label = unread ? "Avisos de actividad, sin leer: " + unread : "Avisos de actividad";
        bell.setAttribute("aria-label", label);
        bell.title = label;
        panel.hidden = !viewing || installed === false;
        $("activityHistoryTitle").hidden = !viewing || installed === false;
        markAll.disabled = busy || unread === 0;
        more.hidden = before === null;
        more.disabled = busy;
        retry.hidden = !needsRefresh;
        retry.disabled = busy;
        for (const button of list.querySelectorAll("button")) button.disabled = busy;
    }

    function stopRead() {
        const request = reading;
        reading = undefined;
        request?.abort();
    }

    function clearList() {
        items = [];
        before = null;
        loaded = needsRefresh = false;
        list.replaceChildren();
        note("");
    }

    function clear() {
        session = undefined;
        window.clearInterval(timer);
        stopRead();
        writing?.abort();
        writing = undefined;
        installed = undefined;
        viewing = false;
        unread = 0;
        clearList();
        sync();
    }

    async function rpc(name, args, request) {
        const timeout = window.setTimeout(() => request.abort(), 18000);
        try {
            const result = await window.PortalAuth.getClient().rpc(name, args).retry(false).abortSignal(request.signal);
            if (result.error) throw { ...result.error, status: result.status };
            return result.data;
        } finally {
            window.clearTimeout(timeout);
        }
    }

    function accessError(error) {
        if (error?.code === "42501" || [401, 403].includes(error?.status)) {
            const verify = session?.verify;
            clear();
            if (verify) void verify();
            return true;
        }
        if (missing.has(error?.code)) {
            installed = false;
            unread = 0;
            window.clearInterval(timer);
            clearList();
            return true;
        }
        return false;
    }

    function validCount(value) {
        return Number.isSafeInteger(value) && value >= 0;
    }

    function validPage(data, cursor, listRequested) {
        if (!data || !validCount(data.unread) || !Array.isArray(data.items) || data.items.length > 20 ||
            (!listRequested && (data.items.length > 0 || data.next_before !== null))) return false;
        if (data.next_before !== null &&
            (data.items.length !== 20 || data.next_before !== data.items.at(-1)?.id)) return false;
        return data.items.every((item, i) => Number.isSafeInteger(item.id) && item.id > 0 &&
            (!cursor || item.id < cursor) && (i === 0 || item.id < data.items[i - 1].id) &&
            Object.hasOwn(titles, item.kind) && typeof item.read === "boolean" &&
            typeof item.created_at === "string" && Number.isFinite(Date.parse(item.created_at)) &&
            [item.student_name, item.subject_name, item.period_name].every(label =>
                label === null || typeof label === "string" && label.length <= 160));
    }

    function draw() {
        list.replaceChildren(...items.map(item => {
            const row = node("li");
            row.dataset.unread = String(!item.read);
            row.tabIndex = -1;
            row.id = "activity-notice-" + item.id;
            const info = node("div");
            const name = item.student_name || "Seminarista";
            const detail = item.kind === "personal_updated"
                ? name + " actualizó los datos de su expediente."
                : [name, item.subject_name, item.period_name].filter(Boolean).join(" · ");
            const time = node("time", date.format(new Date(item.created_at)));
            time.dateTime = item.created_at;
            info.append(node("strong", titles[item.kind]), node("p", detail), time);
            row.append(info);
            if (!item.read) {
                const button = node("button", "Marcar como leído");
                button.type = "button";
                button.className = "back-link";
                button.addEventListener("click", () => void mark(item.id));
                row.append(button);
            }
            return row;
        }));
        note(items.length ? "" : "Todavía no hay avisos.");
    }

    async function refresh(withList = viewing, cursor = null) {
        if (!session || installed === false || writing || document.visibilityState === "hidden") return;
        const request = new AbortController();
        stopRead();
        reading = request;
        if (withList && !loaded) note("Consultando avisos…");
        sync();

        try {
            const data = await rpc("portal_control_activity_read", { p_count_only: !withList, p_before: cursor }, request);
            if (reading !== request) return;
            if (!validPage(data, cursor, withList)) throw new Error("Avisos inválidos");
            const oldCount = unread;
            unread = data.unread;
            installed = true;
            if (withList && viewing) {
                items = cursor ? items.concat(data.items) : data.items;
                before = data.next_before;
                loaded = true;
                needsRefresh = false;
                draw();
            } else if (viewing && oldCount !== unread) {
                needsRefresh = true;
                note("Hay cambios en los avisos. Actualiza la lista cuando termines de revisarla.");
            }
        } catch (error) {
            if (reading !== request || accessError(error)) return;
            if (viewing) {
                needsRefresh = true;
                note("No se pudieron consultar los avisos. Pulsa Actualizar avisos para reintentar.", true);
            }
        } finally {
            if (reading === request) {
                reading = undefined;
                sync();
            }
        }
    }

    async function mark(id = null) {
        if (!session || !viewing || writing || unread === 0) return;
        const request = new AbortController();
        stopRead();
        writing = request;
        sync();

        try {
            const result = await rpc("portal_control_activity_mark", { p_notice_id: id, p_all: id === null }, request);
            if (writing !== request) return;
            if (result?.saved !== true || !validCount(result.unread)) throw new Error("Lectura sin confirmar");
            unread = result.unread;
            for (const item of items) {
                if (id === null || item.id === id) item.read = true;
            }
            if (viewing && loaded) {
                draw();
                if (id !== null) $("activity-notice-" + id)?.focus({ preventScroll: true });
            }
        } catch (error) {
            if (writing !== request || accessError(error)) return;
            if (viewing) {
                needsRefresh = true;
                note("No se pudo confirmar la lectura. Actualiza los avisos para comprobar su estado.", true);
            }
        } finally {
            if (writing === request) {
                writing = undefined;
                sync();
                if (viewing && !loaded && !needsRefresh) void refresh();
            }
        }
    }

    function open() {
        if (!session || viewing) return;
        viewing = true;
        sync();
        void refresh();
    }

    function leave() {
        if (!viewing) return;
        viewing = false;
        stopRead();
        clearList();
        sync();
        if (session && installed === undefined && !writing) void refresh(false);
    }

    markAll.addEventListener("click", () => void mark());
    retry.addEventListener("click", () => void refresh());
    more.addEventListener("click", () => {
        if (before !== null) void refresh(true, before);
    });
    bell.addEventListener("click", () => {
        if (viewing && !reading && !writing) void refresh();
    });

    window.PortalActivityNotices = Object.freeze({
        clear, open, leave,
        show(profile, verify) {
            clear();
            if (profile?.role !== "control_escolar") return;
            const current = { verify };
            session = current;
            queueMicrotask(() => {
                if (session === current && !reading) void refresh();
            });
            timer = window.setInterval(() => {
                if (!reading && !writing) void refresh(viewing && items.length <= 20);
            }, 60000);
        }
    });
}());
