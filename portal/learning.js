(function () {
    "use strict";

    const $ = id => document.getElementById(id);
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const tabs = { inicio: "Inicio del curso", programa: "Programa", contenido: "Contenido", tareas: "Tareas", anuncios: "Anuncios", calificaciones: "Calificaciones", "mis-notas": "Mis calificaciones", participantes: "Participantes", calendario: "Calendario" };
    const dateTime = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" });
    const shortDate = new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" });
    const number = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 2 });
    let active = false, profile, recheck, generation = 0, courseVersion = 0, dashboardVersion = 0;
    let dashboard, dashboardPromise, course, courseId, tab = "inicio", routeKey, gradebook, pageOffset = 0;
    let modal, modalToken = 0, modalBusy = false, modalUncertain = false, returnFocus;
    let calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
    const controllers = new Set();
    const openTopics = new Set();
    const pendingWrites = new Set();

    function node(tag, value, className) {
        const element = document.createElement(tag);
        if (value !== undefined && value !== null) element.textContent = String(value);
        if (className) element.className = className;
        return element;
    }
    function button(label, action, className = "learning-button") {
        const element = node("button", label, className);
        element.type = "button";
        element.addEventListener("click", action);
        return element;
    }
    function link(label, href, className) {
        const element = node("a", label, className);
        element.href = href;
        return element;
    }
    function safeURL(value) {
        if (typeof value !== "string" || !value.trim()) return null;
        try {
            const url = new URL(value);
            return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
        } catch { return null; }
    }
    function external(label, value) {
        const href = safeURL(value);
        if (!href) return null;
        const element = link(label, href, "learning-text-link");
        element.target = "_blank";
        element.rel = "noopener noreferrer";
        return element;
    }
    function date(value, compact = false) {
        if (!value || !Number.isFinite(Date.parse(value))) return "Sin fecha límite";
        return (compact ? shortDate : dateTime).format(new Date(value));
    }
    function score(value) { return typeof value === "number" && Number.isFinite(value) ? number.format(value) + " / 100" : "Sin publicar"; }
    function paragraph(value, className = "learning-prose") { return node("p", value || "", className); }
    function empty(target, message) { target.append(node("p", message, "learning-empty")); }
    function note(value, kind = "", target = $("learningStatus")) {
        if (!target) return;
        target.textContent = value;
        target.className = "learning-status" + (kind ? " " + kind : "");
    }
    function badge(value, kind = "") { return node("span", value, "learning-badge " + kind); }
    function canManage() { return Boolean(course?.can_manage && ["professor", "control_escolar"].includes(profile?.role)); }
    function coursePath(id, section = "inicio", item) { return "#curso/" + id + "/" + section + (item ? "/" + item : ""); }
    function staff() { return ["professor", "control_escolar"].includes(profile?.role); }
    function readError(error) {
        return ["PGRST202", "42883", "42P01"].includes(error?.code)
            ? "El aula virtual todavía necesita instalarse en la base de datos. Contacta al responsable del portal."
            : "No fue posible consultar el aula. Comprueba tu conexión y vuelve a intentar.";
    }
    function unauthorized(error) {
        if (error?.code !== "42501" && ![401, 403].includes(error?.status)) return false;
        const verify = recheck;
        clear();
        location.hash = "inicio";
        if (verify) void verify();
        return true;
    }
    async function request(resource, id = null, offset = 0, limit = 30) {
        const controller = new AbortController();
        controllers.add(controller);
        try {
            const response = await window.PortalAuth.getClient().rpc("portal_learning_read", { p_resource: resource, p_course: id, p_offset: offset, p_limit: limit }).abortSignal(controller.signal);
            if (response.error) throw { ...response.error, status: response.status };
            if (!response.data || typeof response.data !== "object" || Array.isArray(response.data)) throw new Error("Respuesta de aula inválida");
            return response.data;
        } finally { controllers.delete(controller); }
    }
    async function write(action, id, data) {
        const response = await window.PortalAuth.getClient().rpc("portal_learning_write", { p_action: action, p_course: id, p_data: data }).retry(false);
        if (response.error) throw { ...response.error, status: response.status };
        if (response.data?.saved !== true || !uuid.test(response.data.id)) throw new Error("El servidor no confirmó el cambio");
        return response.data;
    }
    function validCollection(value, max = 500) { return Array.isArray(value) && value.length <= max; }
    function validCourse(value) { return value && uuid.test(value.id) && [value.code, value.name, value.period_name].every(item => typeof item === "string" && item.length < 400); }
    function clear() {
        active = false; profile = undefined; recheck = undefined;
        generation++; courseVersion++; dashboardVersion++; routeKey = undefined;
        for (const controller of controllers) controller.abort();
        controllers.clear(); dashboard = undefined; dashboardPromise = undefined; course = undefined; courseId = undefined; gradebook = undefined; pageOffset = 0;
        pendingWrites.clear(); openTopics.clear();
        closeModal(true);
        window.PortalLearningFiles?.clear();
        window.PortalContentFiles?.clear();
        for (const id of ["learningAnnouncements", "learningWork", "learningCalendar", "learningRoot"]) {
            const target = $(id); if (target) target.replaceChildren();
        }
        if ($("learningRoot")) $("learningRoot").hidden = true;
        if ($("learningSidebar")) $("learningSidebar").hidden = true;
    }
    function widgetHeader(target, title, action) {
        const heading = node("div", undefined, "learning-widget-heading");
        heading.append(node("h2", title));
        if (action) heading.append(action);
        target.append(heading);
    }
    function announcementCard(item, edit, targetCourse = courseId) {
        const article = node("article", undefined, "learning-announcement");
        const heading = node("div", undefined, "learning-row-heading");
        heading.append(node("h3", item.title));
        if (item.pinned) heading.append(badge("Fijado", "pinned"));
        if (item.published === false) heading.append(badge("Borrador", "draft"));
        article.append(heading);
        const details = [item.course_name || (item.course_id === null ? "Comunidad del Seminario" : ""), item.published_at ? date(item.published_at) : ""].filter(Boolean).join(" · ");
        if (details) article.append(paragraph(details, "learning-meta"));
        article.append(paragraph(item.body));
        if (item.course_id && !edit) article.append(link("Ir al curso", coursePath(item.course_id, "anuncios"), "learning-text-link"));
        if (edit) article.append(button("Editar anuncio", () => announcementDialog(item, targetCourse), "learning-button secondary"));
        return article;
    }
    function renderAnnouncements(target, items, compact = false) {
        if (!items.length) return empty(target, "Aquí aparecerán los anuncios publicados para tu comunidad y tus cursos.");
        for (const item of items.slice(0, compact ? 5 : 100)) target.append(announcementCard(item, !compact && canManage()));
        if (compact && items.length > 5) target.append(paragraph("Abre cada curso para consultar todos sus anuncios.", "learning-meta"));
    }
    function workCard(item) {
        const row = node("li", undefined, "learning-work-item");
        const submitted = Boolean(item.submitted_at) || ["submitted", "delivered", "graded", "entregada"].includes(item.status);
        const late = !submitted && item.due_at && Date.parse(item.due_at) < Date.now();
        row.append(node("span", submitted ? "✓" : "▤", "learning-work-icon"));
        const content = node("div");
        content.append(link(item.title, coursePath(item.course_id, "tareas", item.id), "learning-work-title"));
        content.append(paragraph(item.course_name || "", "learning-meta"));
        content.append(paragraph((submitted ? "Entregada · " : late ? "Fecha vencida · " : "Entrega · ") + date(item.due_at), "learning-meta" + (late ? " overdue" : "")));
        row.append(content);
        return row;
    }
    function calendarEntries(data = dashboard) {
        if (!data) return [];
        const events = (data.events || []).map(item => ({ ...item, at: item.starts_at, section: "calendario" }));
        const tasks = (data.work || []).filter(item => item.due_at).map(item => ({ ...item, at: item.due_at, section: "tareas", assignment: item.id }));
        return [...events, ...tasks].filter(item => Number.isFinite(Date.parse(item.at)));
    }
    function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
    function renderCalendar(target, entries, month = calendarMonth) {
        const calendar = node("div", undefined, "learning-calendar");
        const heading = node("div", undefined, "learning-calendar-heading");
        const prev = button("‹", () => { calendarMonth = new Date(month.getFullYear(), month.getMonth() - 1, 1); target.replaceChildren(); renderCalendar(target, entries, calendarMonth); }, "learning-calendar-arrow");
        prev.setAttribute("aria-label", "Mes anterior");
        const next = button("›", () => { calendarMonth = new Date(month.getFullYear(), month.getMonth() + 1, 1); target.replaceChildren(); renderCalendar(target, entries, calendarMonth); }, "learning-calendar-arrow");
        next.setAttribute("aria-label", "Mes siguiente");
        heading.append(prev, node("h3", new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric" }).format(month)), next);
        calendar.append(heading);
        const grid = node("div", undefined, "learning-calendar-grid");
        for (const day of ["L", "M", "M", "J", "V", "S", "D"]) grid.append(node("span", day, "learning-calendar-weekday"));
        const first = new Date(month.getFullYear(), month.getMonth(), 1), count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
        for (let index = 0; index < (first.getDay() + 6) % 7; index++) grid.append(node("span"));
        for (let day = 1; day <= count; day++) {
            const when = new Date(month.getFullYear(), month.getMonth(), day), matches = entries.filter(item => sameDay(new Date(item.at), when));
            const cell = button(String(day), () => calendarDay(when, matches), "learning-calendar-day" + (sameDay(when, new Date()) ? " today" : "") + (matches.length ? " has-events" : ""));
            cell.setAttribute("aria-label", new Intl.DateTimeFormat("es-MX", { dateStyle: "full" }).format(when) + (matches.length ? ": " + matches.length + " actividades" : ": sin actividades"));
            grid.append(cell);
        }
        calendar.append(grid);
        target.append(calendar);
    }
    function calendarDay(when, entries) {
        const content = node("div");
        if (!entries.length) empty(content, "No hay actividades registradas para este día.");
        for (const entry of entries) {
            const item = node("article", undefined, "learning-event");
            item.append(node("h3", entry.title), paragraph(date(entry.at), "learning-meta"));
            if (entry.course_name) item.append(paragraph(entry.course_name, "learning-meta"));
            if (entry.body) item.append(paragraph(entry.body));
            if (entry.course_id) item.append(link(entry.assignment ? "Abrir tarea" : "Ir al curso", coursePath(entry.course_id, entry.section, entry.assignment), "learning-text-link"));
            content.append(item);
        }
        readOnlyDialog(new Intl.DateTimeFormat("es-MX", { dateStyle: "full" }).format(when), content);
    }
    function renderDashboard() {
        if (!active || !dashboard) return;
        const announcements = $("learningAnnouncements"), work = $("learningWork"), calendar = $("learningCalendar");
        if (announcements) {
            announcements.replaceChildren();
            widgetHeader(announcements, "Anuncios", profile.role === "control_escolar" ? button("Nuevo anuncio", () => announcementDialog({}, null), "learning-button compact") : null);
            const institutional = profile.role === "control_escolar" && validCollection(dashboard.institutional_announcements, 200) ? dashboard.institutional_announcements : [];
            if (institutional.length) {
                announcements.append(paragraph("Anuncios institucionales: publicados y borradores", "learning-meta"));
                for (const item of institutional) announcements.append(announcementCard(item, true, null));
            }
            const institutionalIds = new Set(institutional.map(item => item.id));
            const community = dashboard.announcements.filter(item => !institutionalIds.has(item.id));
            if (community.length || !institutional.length) renderAnnouncements(announcements, community, true);
        }
        if (work) {
            work.replaceChildren(); widgetHeader(work, "Trabajo pendiente");
            if (dashboard.work.length) { const list = node("ul", undefined, "learning-work-list"); list.append(...dashboard.work.slice(0, 20).map(workCard)); work.append(list); }
            else empty(work, profile.role === "student" ? "No tienes tareas pendientes. Las próximas entregas aparecerán aquí." : "Aquí aparecerán las fechas de entrega de tus cursos.");
        }
        if (calendar) {
            calendar.replaceChildren(); widgetHeader(calendar, "Calendario");
            const calendarBody = node("div"); calendar.append(calendarBody); renderCalendar(calendarBody, calendarEntries());
        }
        if ($("learningSidebar")) $("learningSidebar").hidden = false;
    }
    async function loadDashboard() {
        const operation = ++dashboardVersion, current = generation;
        try {
            const data = await request("dashboard", null, 0, 100);
            if (!active || operation !== dashboardVersion || current !== generation) return;
            if (!validCollection(data.courses, 100) || !data.courses.every(validCourse) || !validCollection(data.announcements) || !validCollection(data.work) || !validCollection(data.events)) throw new Error("Dashboard inválido");
            dashboard = data; renderDashboard();
        } catch (error) {
            if (!active || operation !== dashboardVersion || current !== generation || unauthorized(error)) return;
            for (const [id, title] of [["learningAnnouncements", "Anuncios"], ["learningWork", "Trabajo pendiente"], ["learningCalendar", "Calendario"]]) {
                const target = $(id); if (target) { target.replaceChildren(); widgetHeader(target, title); empty(target, readError(error)); }
            }
            const retry = $("learningAnnouncements"); if (retry) retry.append(button("Reintentar", () => { dashboardPromise = loadDashboard(); }, "learning-button secondary"));
            if ($("learningSidebar")) $("learningSidebar").hidden = false;
        }
    }
    function skeleton() {
        const root = $("learningRoot");
        if (!root) return null;
        root.hidden = false;
        root.replaceChildren();
        const back = link("← Todos mis cursos", "#inicio", "learning-back");
        const banner = node("header", undefined, "learning-course-banner");
        const bannerInfo = node("div");
        const code = node("p", "Aula virtual", "learning-course-code"); code.id = "learningCourseCode";
        const title = node("h1", "Cargando curso…"); title.id = "learningCourseTitle";
        const period = node("p", "", "learning-course-period"); period.id = "learningCoursePeriod";
        bannerInfo.append(code, title, period); banner.append(bannerInfo);
        const navigation = node("nav", undefined, "learning-course-nav"); navigation.id = "learningCourseNav"; navigation.setAttribute("aria-label", "Herramientas del curso");
        const status = node("p", "Consultando tu curso…", "learning-status"); status.id = "learningStatus"; status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
        const content = node("div", undefined, "learning-course-content"); content.id = "learningContent";
        const top = node("div", undefined, "learning-course-topbar"); top.append(back, button("Actualizar curso", () => navigate(true), "learning-button secondary compact"));
        root.append(top, navigation, banner, status, content);
        return root;
    }
    function courseHeading() {
        $("learningRoot").dataset.learningTab = tab;
        window.PortalCourseColors?.apply($("learningRoot"), course.course.code);
        $("learningCourseTitle").textContent = course.course.name;
        $("learningCourseCode").textContent = course.course.code;
        $("learningCoursePeriod").textContent = course.course.period_name;
        window.PortalWorkspace?.setCourseTitle?.(course.course.name, course.course.period_name);
        const nav = $("learningCourseNav"); nav.replaceChildren();
        for (const key of Object.keys(tabs)) {
            if (key === "mis-notas" && profile.role !== "student" || ["calificaciones", "participantes"].includes(key) && !canManage()) continue;
            const item = link(tabs[key], coursePath(courseId, key));
            if (key === tab) item.setAttribute("aria-current", "page");
            nav.append(item);
        }
        document.title = course.course.name + " | Portal del Seminario";
    }
    function toolbar(target, heading, actions = []) {
        const row = node("div", undefined, "learning-section-heading"); row.append(node("h2", heading));
        if (actions.length) { const controls = node("div", undefined, "learning-actions"); controls.append(...actions); row.append(controls); }
        target.append(row);
    }
    function moduleCard(module) {
        const card = link("", coursePath(courseId, "contenido"), "learning-module-card");
        const picture = node("span", undefined, "learning-module-picture"); picture.setAttribute("aria-hidden", "true");
        const info = node("div", undefined, "learning-module-info");
        info.append(node("h3", module.title));
        if (profile.role === "student") {
            const done = module.topics.filter(item => item.completed).length;
            const progress = document.createElement("progress"); progress.max = module.topics.length || 1; progress.value = done; progress.setAttribute("aria-label", "Progreso de " + module.title);
            info.append(progress, paragraph(done + " / " + module.topics.length + " temas completados", "learning-meta"));
        } else info.append(paragraph(module.topics.length + " temas" + (module.published === false ? " · Borrador" : ""), "learning-meta"));
        card.append(picture, info); return card;
    }
    function renderHome(target) {
        const grid = node("div", undefined, "learning-course-columns");
        const left = node("div", undefined, "learning-course-primary"), right = node("aside", undefined, "learning-course-secondary");
        const modules = node("section", undefined, "learning-card");
        toolbar(modules, "Contenido del curso", canManage() ? [button("Nueva unidad", () => moduleDialog())] : []);
        const cards = node("div", undefined, "learning-module-grid");
        if (course.modules.length) cards.append(...course.modules.map(moduleCard)); else empty(cards, canManage() ? "Organiza el contenido de tu curso en unidades y temas." : "Tu profesor publicará aquí las unidades y materiales del curso.");
        modules.append(cards); left.append(modules);
        const shortcuts = node("section", undefined, "learning-card"); toolbar(shortcuts, "Accesos del curso");
        const links = node("div", undefined, "learning-quick-links");
        for (const [label, section] of [["Programa del curso", "programa"], ["Tareas y entregas", "tareas"], [profile.role === "student" ? "Mis calificaciones" : "Libro de calificaciones", profile.role === "student" ? "mis-notas" : "calificaciones"], ["Calendario", "calendario"]]) links.append(link(label + " →", coursePath(courseId, section)));
        shortcuts.append(links); left.append(shortcuts);
        const announcements = node("section", undefined, "learning-card"); toolbar(announcements, "Anuncios", canManage() ? [button("Nuevo anuncio", () => announcementDialog())] : []); renderAnnouncements(announcements, course.announcements.slice(0, 4)); right.append(announcements);
        const work = node("section", undefined, "learning-card"); toolbar(work, "Próximas entregas");
        const assignments = course.assignments.filter(item => item.due_at && (!item.submission || staff())).slice().sort((a,b) => Date.parse(a.due_at)-Date.parse(b.due_at));
        if (!assignments.length) empty(work, "No hay entregas pendientes con fecha límite.");
        else { const list = node("ul", undefined, "learning-work-list"); list.append(...assignments.slice(0, 8).map(item => workCard({ ...item, course_id: courseId, course_name: course.course.name, submitted_at: item.submission?.submitted_at }))); work.append(list); }
        right.append(work); grid.append(left, right); target.append(grid);
    }
    function renderSyllabus(target) {
        toolbar(target, "Programa del curso", canManage() ? [button("Editar programa", () => syllabusDialog())] : []);
        const article = node("article", undefined, "learning-card");
        if (course.course.syllabus) article.append(paragraph(course.course.syllabus));
        else empty(article, canManage() ? "Agrega los objetivos, contenidos, criterios de evaluación y recursos de tu curso." : "El profesor todavía no ha publicado el programa del curso.");
        target.append(article);
    }
    function renderModules(target) {
        toolbar(target, "Contenido", canManage() ? [button("Nueva unidad", () => moduleDialog())] : []);
        if (!course.modules.length) return empty(target, "Este curso todavía no tiene unidades publicadas.");
        for (const module of course.modules) {
            const card = node("section", undefined, "learning-card learning-unit");
            const actions = canManage() ? [button("Editar unidad", () => moduleDialog(module), "learning-button secondary"), button("Agregar contenido", () => topicDialog({}, module))] : [];
            toolbar(card, module.title, actions);
            if (module.published === false) card.append(badge("Unidad en borrador", "draft"));
            if (!module.topics.length) empty(card, canManage() ? "Agrega un tema, una lectura o un enlace a esta unidad." : "Todavía no hay temas publicados en esta unidad.");
            for (const topic of module.topics) {
                const details = node("details", undefined, "learning-topic"); details.open = openTopics.has(topic.id);
                details.addEventListener("toggle", () => details.open ? openTopics.add(topic.id) : openTopics.delete(topic.id));
                const summary = node("summary"); summary.append(node("span", "▤", "learning-topic-icon"), node("span", topic.title));
                if (topic.completed) summary.append(badge("Completado", "done"));
                if (topic.published === false) summary.append(badge("Borrador", "draft"));
                details.append(summary);
                const body = node("div", undefined, "learning-topic-body");
                if (topic.body) body.append(paragraph(topic.body));
                const resource = external("Abrir recurso ↗", topic.url); if (resource) body.append(resource);
                if (Array.isArray(topic.files) && topic.files.length) {
                    const files = node("div"); body.append(files);
                    window.PortalContentFiles?.render(files, {courseId,topicId:topic.id,items:topic.files,edit:false});
                }
                if (canManage()) body.append(button("Editar contenido", () => topicDialog(topic, module), "learning-button secondary"));
                if (profile.role === "student") {
                    const complete = document.createElement("input"); complete.type = "checkbox"; complete.checked = Boolean(topic.completed); complete.id = "learning-complete-" + topic.id;
                    const label = node("label", "Marcar como completado", "learning-complete-label"); label.htmlFor = complete.id; label.prepend(complete);
                    complete.addEventListener("change", async () => {
                        const current = generation, view = courseVersion, value = complete.checked; complete.disabled = true;
                        try { await write("topic_complete", courseId, { topic_id: topic.id, completed: value }); if (active && current === generation && view === courseVersion) { topic.completed = value; const marker = summary.querySelector(".learning-badge.done"); if (value && !marker) summary.append(badge("Completado", "done")); else if (!value && marker) marker.remove(); note(value ? "Tema marcado como completado." : "Tema pendiente de completar.", "success"); } }
                        catch (error) { if (active && current === generation && view === courseVersion && !unauthorized(error)) { complete.checked = !value; note(writeError(error), "error"); } }
                        finally { if (active && current === generation && view === courseVersion) complete.disabled = false; }
                    }); body.append(label);
                }
                details.append(body); card.append(details);
            }
            target.append(card);
        }
    }
    function taskStatus(item) {
        if (item.published === false) return ["Borrador", "draft"];
        if (item.submission) return [item.submission.late ? "Entregada fuera de plazo" : "Entregada", "done"];
        if (item.due_at && Date.parse(item.due_at) < Date.now()) return [item.allow_late ? "Entrega pendiente · fuera de plazo" : "Entrega cerrada", "late"];
        return ["Pendiente", "pending"];
    }
    function renderTasks(target, selected) {
        if (selected) {
            const assignment = course.assignments.find(item => item.id === selected);
            if (assignment) return renderAssignment(target, assignment);
            note("La tarea solicitada no está disponible en este curso.", "error");
        }
        toolbar(target, "Tareas", canManage() ? [button("Nueva tarea", () => assignmentDialog())] : []);
        if (!course.assignments.length) return empty(target, canManage() ? "Crea la primera tarea y establece su fecha de entrega." : "Tu profesor todavía no ha publicado tareas.");
        const list = node("div", undefined, "learning-assignment-list");
        for (const assignment of course.assignments) {
            const card = node("article", undefined, "learning-card learning-assignment-card");
            card.append(node("span", "▤", "learning-assignment-icon"));
            const content = node("div"); content.append(link(assignment.title, coursePath(courseId, "tareas", assignment.id), "learning-assignment-title"), paragraph("Entrega: " + date(assignment.due_at), "learning-meta"));
            const state = taskStatus(assignment); content.append(badge(state[0], state[1]));
            if (typeof assignment.published_score === "number") content.append(paragraph("Calificación: " + score(assignment.published_score), "learning-meta"));
            const actions = node("div", undefined, "learning-actions"); actions.append(link("Abrir tarea", coursePath(courseId, "tareas", assignment.id), "learning-button secondary"));
            if (canManage()) actions.append(button("Editar tarea", () => assignmentDialog(assignment), "learning-button secondary"));
            card.append(content, actions); list.append(card);
        }
        target.append(list);
    }
    function renderAssignment(target, assignment) {
        target.append(link("← Todas las tareas", coursePath(courseId, "tareas"), "learning-back"));
        toolbar(target, assignment.title, canManage() ? [button("Editar tarea", () => assignmentDialog(assignment)), link("Evaluar entregas", coursePath(courseId, "calificaciones"), "learning-button secondary")] : []);
        const article = node("article", undefined, "learning-card");
        const status = taskStatus(assignment); article.append(badge(status[0], status[1]), paragraph("Fecha de entrega: " + date(assignment.due_at), "learning-deadline"));
        if (assignment.due_at) article.append(paragraph(assignment.allow_late ? "Se permiten entregas fuera de plazo; quedarán registradas como tardías." : "La entrega se cierra al llegar la fecha límite.", "learning-meta"));
        article.append(node("h3", "Instrucciones"));
        if (assignment.instructions) article.append(paragraph(assignment.instructions)); else empty(article, "No se han agregado instrucciones adicionales.");
        target.append(article);
        if (profile.role === "student") {
            const delivery = node("section", undefined, "learning-card"); toolbar(delivery, "Tu entrega");
            if (assignment.submission) {
                delivery.append(paragraph("Última entrega: " + date(assignment.submission.submitted_at), "learning-meta"));
                if (assignment.submission.body) delivery.append(paragraph(assignment.submission.body));
                const submittedLink = external("Abrir enlace entregado ↗", assignment.submission.url); if (submittedLink) delivery.append(submittedLink);
            } else empty(delivery, "Todavía no has enviado tu trabajo.");
            const closed = assignment.due_at && Date.parse(assignment.due_at) < Date.now() && !assignment.allow_late;
            if (!closed) delivery.append(button(assignment.submission ? "Actualizar entrega" : "Entregar tarea", () => submissionDialog(assignment)));
            else delivery.append(paragraph("El plazo de entrega ha finalizado. Contacta a tu profesor si necesitas ayuda.", "learning-meta"));
            const files = node("div", undefined, "learning-files-area"); delivery.append(files);
            window.PortalLearningFiles?.render(files, { courseId, assignmentId: assignment.id, canManage: false });
            target.append(delivery);
            if (typeof assignment.published_score === "number" || assignment.published_feedback) {
                const feedback = node("section", undefined, "learning-card"); toolbar(feedback, "Evaluación publicada"); feedback.append(paragraph(score(assignment.published_score), "learning-score-large"));
                if (assignment.published_feedback) feedback.append(paragraph(assignment.published_feedback)); target.append(feedback);
            }
        } else if (canManage()) target.append(paragraph("Abre el libro de calificaciones para revisar las entregas de cada alumno, guardar borradores y publicar resultados.", "learning-meta"));
    }
    function renderCourseAnnouncements(target) {
        toolbar(target, "Anuncios del curso", canManage() ? [button("Nuevo anuncio", () => announcementDialog())] : []);
        const wrapper = node("section", undefined, "learning-card"); renderAnnouncements(wrapper, course.announcements); target.append(wrapper);
    }
    function renderOwnGrades(target) {
        toolbar(target, "Mis calificaciones");
        const final = node("section", undefined, "learning-final-grade"); final.append(node("h3", "Calificación final publicada"), paragraph(score(course.course.final_score), "learning-score-large")); target.append(final);
        const card = node("section", undefined, "learning-card");
        card.append(paragraph("Aquí aparecen únicamente las evaluaciones que tu profesor ha publicado.", "learning-meta"));
        if (!course.assignments.length) empty(card, "Todavía no hay actividades publicadas en este curso.");
        else {
            const table = node("table", undefined, "learning-grades-table"); const head = node("thead"), headRow = node("tr");
            for (const heading of ["Actividad", "Estado de entrega", "Calificación", "Comentarios"]) headRow.append(node("th", heading)); head.append(headRow); table.append(head);
            const body = node("tbody");
            for (const assignment of course.assignments) {
                const row = node("tr"), title = node("th"); title.scope = "row"; title.append(link(assignment.title, coursePath(courseId, "tareas", assignment.id), "learning-text-link"));
                row.append(title, node("td", assignment.submission ? "Entregada" : "Sin entrega"), node("td", score(assignment.published_score)), node("td", assignment.published_feedback || "—")); body.append(row);
            }
            table.append(body); const scroll = node("div", undefined, "learning-table-scroll"); scroll.append(table); card.append(scroll);
        }
        target.append(card);
    }
    function renderCourseCalendar(target) {
        toolbar(target, "Calendario del curso", canManage() ? [button("Nuevo evento", () => eventDialog())] : []);
        const data = { events: course.events.map(item => ({ ...item, course_id: courseId, course_name: course.course.name })), work: course.assignments.map(item => ({ ...item, course_id: courseId, course_name: course.course.name })) };
        const grid = node("div", undefined, "learning-calendar-layout");
        const calendar = node("section", undefined, "learning-card"); renderCalendar(calendar, calendarEntries(data)); grid.append(calendar);
        const list = node("section", undefined, "learning-card"); toolbar(list, "Fechas y actividades");
        const entries = calendarEntries(data).sort((a,b) => Date.parse(a.at) - Date.parse(b.at));
        if (!entries.length) empty(list, "Este curso todavía no tiene fechas registradas.");
        for (const entry of entries) {
            const article = node("article", undefined, "learning-event"); article.append(node("h3", entry.title), paragraph(date(entry.at), "learning-meta"));
            if (entry.body) article.append(paragraph(entry.body));
            if (entry.assignment) article.append(link("Abrir tarea", coursePath(courseId, "tareas", entry.id), "learning-text-link"));
            else if (canManage()) article.append(button("Editar evento", () => eventDialog(entry), "learning-button secondary"));
            list.append(article);
        }
        grid.append(list); target.append(grid);
    }
    function pagination(target, offset, hasMore, action) {
        const row = node("div", undefined, "learning-pagination");
        if (offset) row.append(button("Anterior", () => action(Math.max(0, offset - 30)), "learning-button secondary"));
        row.append(paragraph("Alumnos " + (offset + 1) + "–" + (offset + (gradebook?.students?.length || 30)), "learning-meta"));
        if (hasMore) row.append(button("Siguiente", () => action(offset + 30), "learning-button secondary")); target.append(row);
    }
    async function renderParticipants(target, offset = 0) {
        toolbar(target, "Lista de alumnos");
        const operation = courseVersion, current = generation, id = courseId;
        const list = node("ul", undefined, "learning-participants"); target.append(list); note("Consultando alumnos…");
        try {
            const data = await request("participants", id, offset, 30);
            if (!active || current !== generation || operation !== courseVersion || tab !== "participantes") return;
            if (!validCollection(data.items, 30)) throw new Error("Lista inválida");
            if (!data.items.length) empty(list, "Todavía no hay alumnos activos inscritos en esta clase.");
            for (const item of data.items) list.append(node("li", item.name));
            note("");
            const nav = node("div", undefined, "learning-pagination");
            if (offset) nav.append(button("Anterior", () => { target.replaceChildren(); void renderParticipants(target, Math.max(0, offset - 30)); }, "learning-button secondary"));
            if (data.has_more) nav.append(button("Siguiente", () => { target.replaceChildren(); void renderParticipants(target, offset + 30); }, "learning-button secondary"));
            target.append(nav);
        } catch (error) { if (active && current === generation && operation === courseVersion && !unauthorized(error)) note(readError(error), "error"); }
    }
    function gradeRecord(student, assignment) { return student.grades.find(item => item.assignment_id === assignment.id) || { assignment_id: assignment.id, revision: 0, score: null, feedback: "" }; }
    async function renderGradebook(target, offset = 0) {
        const operation = courseVersion, current = generation, id = courseId;
        pageOffset = offset; toolbar(target, "Libro de calificaciones"); note("Consultando calificaciones…");
        try {
            const data = await request("gradebook", id, offset, 30);
            if (!active || current !== generation || operation !== courseVersion || tab !== "calificaciones") return;
            if (!validCollection(data.assignments, 100) || !validCollection(data.students, 30) || !data.students.every(item => uuid.test(item.enrollment_id) && validCollection(item.grades, 100))) throw new Error("Libro inválido");
            gradebook = data; note(""); drawGradebook(target, data, offset);
        } catch (error) {
            if (!active || current !== generation || operation !== courseVersion || unauthorized(error)) return;
            note(readError(error), "error"); target.append(button("Reintentar", () => { target.replaceChildren(); void renderGradebook(target, offset); }, "learning-button secondary"));
        }
    }
    function drawGradebook(target, data, offset) {
        target.append(paragraph("Guarda las notas como borrador y publícalas cuando estén listas. Las notas de actividades no reemplazan automáticamente la calificación final del curso.", "learning-meta"));
        if (!data.assignments.length) { empty(target, "Crea una tarea para agregar una columna a este libro de calificaciones."); return; }
        if (!data.students.length) { empty(target, "Control Escolar todavía no ha inscrito alumnos activos en esta clase."); return; }
        const actions = node("div", undefined, "learning-grade-actions");
        const saveAll = button("Guardar borradores", () => void saveGrid(false)); saveAll.id = "learningGradeSave";
        const publishAll = button("Publicar calificaciones", () => void saveGrid(true), "learning-button secondary"); publishAll.id = "learningGradePublish";
        const refresh = button("Actualizar libro", () => { target.replaceChildren(); void renderGradebook(target, pageOffset); }, "learning-button secondary");
        const exportButton = button("Exportar alumnos mostrados", exportGradebook, "learning-button secondary");
        actions.append(saveAll, publishAll, exportButton, refresh); target.append(actions);
        const wrapper = node("div", undefined, "learning-gradebook-scroll"); wrapper.tabIndex = 0; wrapper.setAttribute("aria-label", "Libro de calificaciones; desplázate horizontalmente para ver las tareas");
        const table = node("table", undefined, "learning-gradebook"); table.id = "learningGradebook";
        const head = node("thead"), labels = node("tr"); labels.append(node("th", "Alumno"), node("th", "Final publicada"));
        for (const assignment of data.assignments) labels.append(node("th", assignment.title)); head.append(labels); table.append(head);
        const body = node("tbody");
        for (const student of data.students) {
            const row = node("tr"), name = node("th", student.name); name.scope = "row"; row.append(name, node("td", score(student.final_score)));
            for (const assignment of data.assignments) {
                const grade = gradeRecord(student, assignment), cell = node("td", undefined, "learning-grade-cell");
                const input = document.createElement("input"); input.type = "number"; input.min = "0"; input.max = "100"; input.step = "0.01"; input.inputMode = "decimal";
                input.value = typeof grade.score === "number" ? String(grade.score) : "";
                input.dataset.enrollment = student.enrollment_id; input.dataset.assignment = assignment.id; input.dataset.original = input.value;
                input.setAttribute("aria-label", "Calificación de " + student.name + ": " + assignment.title);
                input.addEventListener("input", () => { cell.classList.toggle("is-dirty", input.value !== input.dataset.original); });
                const field = node("div", undefined, "learning-score-input"); field.append(input, node("span", "/ 100"));
                cell.append(field, paragraph(typeof grade.published_score === "number" ? "Publicada: " + score(grade.published_score) : "Sin publicar", "learning-grade-published"));
                if (grade.submitted_at) cell.append(paragraph("Entregada " + date(grade.submitted_at, true), "learning-meta"));
                cell.append(button("Revisar entrega", () => gradeDialog(student, assignment, grade), "learning-review-button"));
                cell.lastChild.setAttribute("aria-label", "Revisar entrega de " + student.name + ": " + assignment.title);
                row.append(cell);
            }
            body.append(row);
        }
        table.append(body); wrapper.append(table); target.append(wrapper);
        if (offset || data.has_more) pagination(target, offset, data.has_more, value => { target.replaceChildren(); void renderGradebook(target, value); });
    }
    function exportGradebook() {
        if (!active || !canManage() || !gradebook) return;
        const escape = value => {
            let text = value === null || value === undefined ? "" : String(value);
            if (/^[\s\u0000-\u0020\u200B-\u200D\uFEFF]*[=+\-@]/u.test(text)) text = "'" + text;
            return '"' + text.replaceAll('"', '""') + '"';
        };
        const heading = ["Alumno", "Calificación final publicada"];
        for (const assignment of gradebook.assignments) heading.push(assignment.title + " (borrador)", assignment.title + " (publicada)");
        const rows = [heading];
        for (const student of gradebook.students) {
            const row = [student.name, student.final_score];
            for (const assignment of gradebook.assignments) {
                const grade = gradeRecord(student, assignment);
                row.push(grade.score, grade.published_score);
            }
            rows.push(row);
        }
        const csv = "\uFEFF" + rows.map(row => row.map(escape).join(",")).join("\r\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        const download = document.createElement("a"); download.href = url; download.download = "calificaciones-" + course.course.code.replace(/[^a-zA-Z0-9_-]/g, "_") + "-alumnos-mostrados.csv";
        document.body.append(download); download.click(); download.remove(); setTimeout(() => URL.revokeObjectURL(url), 0);
        note("Archivo exportado con los " + gradebook.students.length + " alumnos mostrados en esta página.", "success");
    }
    async function saveGrid(publish) {
        if (!active || !canManage() || !gradebook || pendingWrites.has("grid")) return;
        const inputs = [...$("learningGradebook").querySelectorAll("input[data-assignment]")];
        const selected = inputs.filter(input => input.value !== input.dataset.original || publish && input.value !== "");
        if (!selected.length) { note("No hay calificaciones nuevas para guardar."); return; }
        for (const input of selected) {
            if (input.value === "" || !input.reportValidity()) { input.focus(); note("Escribe una calificación de 0 a 100. Los campos vacíos se conservan sin calificar.", "error"); return; }
        }
        const current = generation, operation = courseVersion, id = courseId;
        pendingWrites.add("grid");
        const controls = [...$("learningContent").querySelectorAll("button,input")]; controls.forEach(element => element.disabled = true);
        let savedCount = 0, publishedCount = 0;
        note(publish ? "Guardando y publicando calificaciones…" : "Guardando borradores…");
        try {
            for (const input of selected) {
                if (!active || current !== generation || operation !== courseVersion) return;
                const student = gradebook.students.find(item => item.enrollment_id === input.dataset.enrollment);
                const assignment = gradebook.assignments.find(item => item.id === input.dataset.assignment);
                const grade = gradeRecord(student, assignment);
                const response = await write("grade_save", id, { assignment_id: assignment.id, enrollment_id: student.enrollment_id, score: Number(input.value), feedback: grade.feedback || "", revision: grade.revision || 0 });
                savedCount++;
                const revision = Number.isInteger(response.revision) ? response.revision : (grade.revision || 0) + 1;
                if (publish) { await write("grade_publish", id, { assignment_id: assignment.id, enrollment_id: student.enrollment_id, revision }); publishedCount++; }
            }
            if (!active || current !== generation || operation !== courseVersion) return;
            const target = $("learningContent"); target.replaceChildren(); await renderGradebook(target, pageOffset);
            if (active && current === generation && operation === courseVersion) note(publish ? savedCount + " borradores guardados y " + publishedCount + " calificaciones publicadas." : savedCount + " borradores guardados.", "success");
            dashboardPromise = loadDashboard();
        } catch (error) {
            if (!active || current !== generation || operation !== courseVersion || unauthorized(error)) return;
            note(savedCount + " borradores guardados y " + publishedCount + " calificaciones publicadas. " + writeError(error) + " Actualiza el libro antes de repetir el cambio.", "error");
            controls.forEach(element => { if (element.textContent === "Actualizar libro") element.disabled = false; });
            return;
        } finally { pendingWrites.delete("grid"); }
    }
    function renderTab(selectedItem) {
        if (!active || !course || !$("learningContent")) return;
        window.PortalLearningFiles?.clear();
        window.PortalContentFiles?.clear();
        const target = $("learningContent"); target.replaceChildren(); note(""); courseHeading();
        if (tab === "inicio") renderHome(target);
        else if (tab === "programa") renderSyllabus(target);
        else if (tab === "contenido") renderModules(target);
        else if (tab === "tareas") renderTasks(target, selectedItem);
        else if (tab === "anuncios") renderCourseAnnouncements(target);
        else if (tab === "mis-notas") renderOwnGrades(target);
        else if (tab === "calendario") renderCourseCalendar(target);
        else if (tab === "participantes" && canManage()) void renderParticipants(target);
        else if (tab === "calificaciones" && canManage()) void renderGradebook(target, pageOffset);
    }
    async function loadCourse(id, selectedTab, selectedItem) {
        const operation = ++courseVersion, current = generation;
        const changedCourse = courseId !== id;
        courseId = id; course = undefined; gradebook = undefined; pageOffset = 0; if (changedCourse) openTopics.clear();
        skeleton();
        try {
            const data = await request("course", id, 0, 100);
            if (!active || current !== generation || operation !== courseVersion || courseId !== id) return;
            if (!validCourse(data.course) || data.course.id !== id || !validCollection(data.announcements, 200) || !validCollection(data.modules, 100) || !data.modules.every(item => validCollection(item.topics, 500)) || !validCollection(data.assignments, 100) || !validCollection(data.events, 200)) throw new Error("Curso inválido");
            course = data; tab = selectedTab;
            if (profile.role === "student" && ["calificaciones", "participantes"].includes(tab)) { location.hash = coursePath(id, "mis-notas"); return; }
            if (profile.role !== "student" && tab === "mis-notas") { location.hash = coursePath(id, "calificaciones"); return; }
            renderTab(selectedItem);
        } catch (error) {
            if (!active || current !== generation || operation !== courseVersion || unauthorized(error)) return;
            note(readError(error), "error");
            $("learningContent")?.append(button("Reintentar", () => void loadCourse(id, selectedTab, selectedItem), "learning-button secondary"));
        }
    }
    function navigate(force = false) {
        if (!active) return;
        const pieces = location.hash.slice(1).split("/");
        if (pieces[0] !== "curso") {
            courseVersion++; routeKey = undefined; course = undefined; courseId = undefined; gradebook = undefined; closeModal(true); window.PortalLearningFiles?.clear(); window.PortalContentFiles?.clear();
            if ($("learningRoot")) { $("learningRoot").hidden = true; $("learningRoot").replaceChildren(); }
            return;
        }
        const id = pieces[1], selectedTab = Object.hasOwn(tabs, pieces[2]) ? pieces[2] : "inicio", item = uuid.test(pieces[3] || "") ? pieces[3] : undefined;
        if (!uuid.test(id || "")) { location.hash = "inicio"; return; }
        const key = id + "/" + selectedTab + "/" + (item || "");
        if (!force && routeKey === key) return;
        closeModal(true); pendingWrites.clear(); routeKey = key;
        if ($("learningRoot")) $("learningRoot").hidden = false;
        if (!force && courseId === id && course) {
            courseVersion++; tab = selectedTab;
            if (profile.role === "student" && ["calificaciones", "participantes"].includes(tab)) { location.hash = coursePath(id, "mis-notas"); return; }
            if (profile.role !== "student" && tab === "mis-notas") { location.hash = coursePath(id, "calificaciones"); return; }
            renderTab(item);
        } else void loadCourse(id, selectedTab, item);
    }
    async function refreshCourse() {
        const pieces = location.hash.slice(1).split("/");
        if (pieces[0] === "curso" && uuid.test(pieces[1] || "")) await loadCourse(pieces[1], Object.hasOwn(tabs, pieces[2]) ? pieces[2] : "inicio", pieces[3]);
        dashboardPromise = loadDashboard();
    }
    function show(value, callback) {
        clear(); profile = value; recheck = callback; active = true;
        if ($("learningSidebar")) $("learningSidebar").hidden = false;
        for (const [id, title] of [["learningAnnouncements", "Anuncios"], ["learningWork", "Trabajo pendiente"], ["learningCalendar", "Calendario"]]) {
            const target = $(id); if (target) { target.replaceChildren(); widgetHeader(target, title); empty(target, "Consultando…"); }
        }
        dashboardPromise = loadDashboard(); navigate();
    }
    async function openByCard({ code, period }) {
        if (!active) return;
        const current = generation;
        if (dashboardPromise) await dashboardPromise;
        if (!active || current !== generation) return;
        let match = dashboard?.courses.find(item => item.code === code && item.period_name === period);
        let offset = dashboard?.courses.length || 0, hasMore = dashboard?.has_more_courses;
        try {
            for (let pages = 0; !match && hasMore && pages < 20; pages++) {
                const data = await request("dashboard", null, offset, 100);
                if (!active || current !== generation) return;
                if (!validCollection(data.courses, 100) || !data.courses.every(validCourse)) throw new Error("Cursos inválidos");
                dashboard.courses.push(...data.courses); offset += data.courses.length; hasMore = data.has_more_courses; dashboard.has_more_courses = hasMore;
                match = data.courses.find(item => item.code === code && item.period_name === period);
                if (!data.courses.length) break;
            }
            if (match) { location.hash = coursePath(match.id); return; }
            const target = $("learningAnnouncements"); if (target) { target.replaceChildren(); widgetHeader(target, "Aula virtual"); empty(target, "No fue posible abrir esta clase. Actualiza tus cursos o contacta a Control Escolar."); target.append(button("Actualizar cursos", () => { dashboardPromise = loadDashboard(); }, "learning-button secondary")); }
        } catch (error) { if (active && current === generation && !unauthorized(error)) { const target = $("learningAnnouncements"); if (target) { target.replaceChildren(); widgetHeader(target, "Aula virtual"); empty(target, readError(error)); } } }
    }
    function closeModal(force = false) {
        if (modalBusy && !force) return;
        modalToken++; modalBusy = false; modalUncertain = false;
        if (modal) { window.PortalLearningFiles?.clear(modal); window.PortalContentFiles?.clear(modal); if (modal.open) modal.close(); modal.remove(); modal = undefined; }
        if (!force && returnFocus?.isConnected) returnFocus.focus(); returnFocus = undefined;
    }
    function openDialog(title, onSubmit, submitLabel = "Guardar") {
        closeModal(true); returnFocus = document.activeElement;
        modal = node("dialog", undefined, "learning-dialog"); modal.id = "learningDialog"; modal.setAttribute("aria-labelledby", "learningDialogTitle");
        const heading = node("div", undefined, "learning-dialog-heading"); const label = node("h2", title); label.id = "learningDialogTitle";
        const close = button("×", () => closeModal(), "learning-dialog-close"); close.setAttribute("aria-label", "Cerrar formulario"); heading.append(label, close);
        const form = node("form"); form.id = "learningForm"; form.method = "post";
        const fields = node("div", undefined, "learning-fields"); fields.id = "learningFields";
        const message = node("p", "", "learning-status"); message.id = "learningDialogMessage"; message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite");
        const actions = node("div", undefined, "learning-dialog-actions");
        const submit = node("button", submitLabel, "learning-button"); submit.id = "learningSave"; submit.type = "submit";
        const cancel = button("Cancelar", () => closeModal(), "learning-button secondary"); actions.append(submit, cancel);
        form.append(fields, message, actions); modal.append(heading, form); document.body.append(modal);
        const token = modalToken;
        form.addEventListener("submit", event => { event.preventDefault(); if (!modalBusy && !modalUncertain && form.reportValidity() && token === modalToken) void onSubmit(form, token); });
        modal.addEventListener("cancel", event => { event.preventDefault(); closeModal(); });
        return { fields, form, actions, submit, message, token, open() { modal.showModal(); fields.querySelector("input:not([type=hidden]),textarea,select")?.focus(); } };
    }
    function field(target, name, label, options = {}) {
        const group = node("div", undefined, "learning-field");
        const input = document.createElement(options.textarea ? "textarea" : "input"); input.id = "learning-field-" + name; input.name = name;
        const caption = node("label", label); caption.htmlFor = input.id;
        if (!options.textarea) input.type = options.type || "text";
        input.required = Boolean(options.required); input.autocomplete = "off";
        if (options.type === "checkbox") input.checked = Boolean(options.value);
        else input.value = options.value === undefined || options.value === null ? "" : String(options.value);
        if (options.textarea) { input.rows = options.rows || 6; input.maxLength = options.max || 20000; }
        else if (!["checkbox", "number", "datetime-local"].includes(options.type)) input.maxLength = options.max || (name === "url" ? 2000 : 160);
        if (options.type === "number") { input.min = String(options.min ?? 0); input.max = String(options.max ?? 10000); input.step = String(options.step ?? 1); }
        if (options.type === "checkbox") { group.classList.add("learning-checkbox"); group.append(input, caption); } else group.append(caption, input);
        if (options.help) group.append(paragraph(options.help, "learning-meta")); target.append(group); return input;
    }
    function values(form) {
        const result = {};
        for (const input of form.querySelectorAll("input[name],textarea[name]")) result[input.name] = input.type === "checkbox" ? input.checked : input.type === "number" ? input.value === "" ? null : Number(input.value) : input.value.trim();
        return result;
    }
    function editData(row, data) { return row.id ? { ...data, id: row.id, revision: row.revision || 0 } : data; }
    function writeError(error) {
        if (error?.code === "PT409" || error?.code === "23505") return "El registro cambió o ya existe. Cierra el formulario y actualiza el curso antes de continuar.";
        if (error?.code === "22023") return typeof error.message === "string" && error.message.length <= 300 ? error.message : "Revisa los datos del formulario.";
        return "No se pudo confirmar el cambio. Actualiza el curso antes de volver a intentarlo.";
    }
    async function submitModal(action, id, data, token, after) {
        if (!active || modalBusy || modalUncertain || token !== modalToken) return;
        const current = generation; modalBusy = true; $("learningSave").disabled = true; $("learningForm").setAttribute("aria-busy", "true"); note("Guardando…", "", $("learningDialogMessage"));
        try {
            const result = await write(action, id, data);
            if (!active || current !== generation || token !== modalToken) return;
            modalBusy = false; closeModal();
            if (after) await after(result); else if (id === null) {
                dashboardPromise = loadDashboard(); await dashboardPromise;
                if (active && current === generation && $("learningAnnouncements")) $("learningAnnouncements").prepend(paragraph("Anuncio institucional guardado.", "learning-status success"));
            } else await refreshCourse();
            if (active && current === generation) note(action === "submit" ? "Tu entrega quedó guardada." : "Cambios guardados.", "success");
        } catch (error) {
            if (!active || current !== generation || token !== modalToken || unauthorized(error)) return;
            modalUncertain = !["22023", "PT409", "23505"].includes(error?.code); note(writeError(error), "error", $("learningDialogMessage"));
        } finally {
            if (token === modalToken && modal) { modalBusy = false; $("learningSave").disabled = modalUncertain; $("learningForm").setAttribute("aria-busy", "false"); }
        }
    }
    function announcementDialog(row = {}, targetCourse = courseId) {
        if (targetCourse === null ? profile?.role !== "control_escolar" : !canManage()) return;
        const dialog = openDialog(row.id ? "Editar anuncio" : targetCourse === null ? "Nuevo anuncio institucional" : "Nuevo anuncio", (form, token) => submitModal("announcement_save", targetCourse, editData(row, values(form)), token));
        field(dialog.fields, "title", "Título", { required: true, value: row.title });
        field(dialog.fields, "body", "Mensaje del anuncio", { required: true, textarea: true, value: row.body });
        field(dialog.fields, "pinned", "Fijar al inicio", { type: "checkbox", value: row.pinned });
        field(dialog.fields, "published", "Publicar anuncio", { type: "checkbox", value: row.published !== false }); dialog.open();
    }
    function syllabusDialog() {
        if (!canManage()) return;
        const dialog = openDialog("Editar programa", (form, token) => submitModal("syllabus_save", courseId, values(form), token));
        field(dialog.fields, "body", "Programa, objetivos y criterios de evaluación", { textarea: true, rows: 12, value: course.course.syllabus }); dialog.open();
    }
    function moduleDialog(row = {}) {
        if (!canManage()) return;
        const dialog = openDialog(row.id ? "Editar unidad" : "Nueva unidad", (form, token) => submitModal("module_save", courseId, editData(row, values(form)), token));
        field(dialog.fields, "title", "Nombre de la unidad", { required: true, value: row.title });
        field(dialog.fields, "position", "Orden", { type: "number", required: true, value: row.position ?? course.modules.length + 1, max: 10000 });
        field(dialog.fields, "published", "Publicar unidad", { type: "checkbox", value: row.published !== false }); dialog.open();
    }
    function topicDialog(row = {}, module) {
        if (!canManage()) return;
        const targetCourse = courseId, current = generation;
        let savedTopic;
        const dialog = openDialog(row.id ? "Editar contenido" : "Agregar contenido", async (form, token) => {
            if (!files) { note("No se pudo cargar la opción de archivos. Recarga el portal.", "error", dialog.message); return; }
            if (!files.validate()) return;
            const data = values(form);
            if (data.url && !safeURL(data.url)) { note("Introduce un enlace completo que comience con https:// o http://.", "error", dialog.message); return; }
            modalBusy = true; dialog.submit.disabled = true; form.setAttribute("aria-busy", "true");
            note(savedTopic ? "Reintentando los archivos pendientes…" : "Guardando contenido…", "", dialog.message);
            try {
                if (!savedTopic) {
                    savedTopic = await write("topic_save", targetCourse, editData(row, {...data,module_id:module.id}));
                    if (!active || current !== generation || token !== modalToken) return;
                    // Después de confirmar el tema, los reintentos solo suben archivos.
                    for (const input of form.querySelectorAll("input[name],textarea[name]")) input.disabled = true;
                }
                await files.uploadTo(savedTopic.id);
                if (!active || current !== generation || token !== modalToken) return;
                openTopics.add(savedTopic.id); modalBusy = false; closeModal(); await refreshCourse();
                if (active && current === generation) note("Contenido y archivos guardados.", "success");
            } catch (error) {
                if (!active || current !== generation || token !== modalToken || (error?.source !== "storage" && unauthorized(error))) return;
                if (savedTopic) {
                    dialog.submit.textContent = "Reintentar subida";
                    note("El tema quedó guardado. No se completó la subida de todos los archivos. Pulsa Reintentar subida para continuar sin duplicar el tema. También puedes cerrar y revisar sus archivos más tarde.", "error", dialog.message);
                } else { modalUncertain = !["22023","PT409","23505"].includes(error?.code); note(writeError(error), "error", dialog.message); }
            } finally { if (token === modalToken && modal) { modalBusy = false; dialog.submit.disabled = modalUncertain; form.setAttribute("aria-busy", "false"); } }
        });
        field(dialog.fields, "title", "Título del tema", {required:true,value:row.title});
        field(dialog.fields, "body", "Contenido o indicaciones", {textarea:true,value:row.body});
        field(dialog.fields, "url", "Enlace al recurso (opcional)", {type:"url",value:row.url});
        const area = node("div"); dialog.fields.append(area);
        const files = window.PortalContentFiles?.render(area, {courseId:targetCourse,topicId:row.id,items:row.files || [],edit:true});
        field(dialog.fields, "position", "Orden", {type:"number",required:true,value:row.position ?? module.topics.length + 1,max:10000});
        field(dialog.fields, "published", "Publicar contenido", {type:"checkbox",value:row.published !== false}); dialog.open();
    }
    function localDate(value) {
        if (!value || !Number.isFinite(Date.parse(value))) return "";
        const when = new Date(value); return new Date(when.getTime() - when.getTimezoneOffset() * 60000).toISOString().slice(0,16);
    }
    function assignmentDialog(row = {}) {
        if (!canManage()) return;
        const dialog = openDialog(row.id ? "Editar tarea" : "Nueva tarea", (form, token) => {
            const data = values(form); data.due_at = data.due_at ? new Date(data.due_at).toISOString() : null; return submitModal("assignment_save", courseId, editData(row, data), token);
        });
        field(dialog.fields, "title", "Título de la tarea", { required: true, value: row.title });
        field(dialog.fields, "instructions", "Instrucciones", { textarea: true, value: row.instructions });
        field(dialog.fields, "due_at", "Fecha y hora de entrega", { type: "datetime-local", value: localDate(row.due_at), help: "Se utiliza la zona horaria de tu dispositivo." });
        field(dialog.fields, "allow_late", "Permitir entregas fuera de plazo", { type: "checkbox", value: row.allow_late !== false });
        field(dialog.fields, "published", "Publicar tarea", { type: "checkbox", value: row.published !== false }); dialog.open();
    }
    function submissionDialog(assignment) {
        if (profile?.role !== "student") return;
        const dialog = openDialog(assignment.submission ? "Actualizar entrega" : "Entregar tarea", (form, token) => {
            const data = values(form);
            if (data.url && !safeURL(data.url)) { note("Introduce un enlace completo que comience con https:// o http://.", "error", $("learningDialogMessage")); return; }
            return submitModal("submit", courseId, { ...data, assignment_id: assignment.id }, token);
        }, "Enviar entrega");
        field(dialog.fields, "body", "Tu trabajo", { textarea: true, rows: 8, value: assignment.submission?.body });
        field(dialog.fields, "url", "Enlace de tu trabajo", { type: "url", value: assignment.submission?.url });
        dialog.fields.append(paragraph("Puedes escribir tu respuesta, compartir un enlace o utilizar los adjuntos de la tarea. El profesor verá tu última entrega.", "learning-meta")); dialog.open();
    }
    function eventDialog(row = {}) {
        if (!canManage()) return;
        const dialog = openDialog(row.id ? "Editar evento" : "Nuevo evento", (form, token) => {
            const data = values(form); data.starts_at = new Date(data.starts_at).toISOString(); data.ends_at = data.ends_at ? new Date(data.ends_at).toISOString() : null;
            if (data.ends_at && Date.parse(data.ends_at) < Date.parse(data.starts_at)) { note("La fecha de fin debe ser posterior al inicio.", "error", $("learningDialogMessage")); return; }
            return submitModal("event_save", courseId, editData(row, data), token);
        });
        field(dialog.fields, "title", "Nombre del evento", { required: true, value: row.title });
        field(dialog.fields, "body", "Descripción", { textarea: true, value: row.body });
        field(dialog.fields, "starts_at", "Inicio", { type: "datetime-local", required: true, value: localDate(row.starts_at), help: "Se utiliza la zona horaria de tu dispositivo." });
        field(dialog.fields, "ends_at", "Fin", { type: "datetime-local", value: localDate(row.ends_at) }); dialog.open();
    }
    function readOnlyDialog(title, content) {
        const dialog = openDialog(title, () => {}); dialog.fields.append(content); dialog.submit.hidden = true;
        dialog.actions.lastChild.textContent = "Cerrar"; dialog.open();
    }
    function gradeDialog(student, assignment, grade) {
        if (!canManage()) return;
        let revision = grade.revision || 0;
        const saveGrade = async (form, token, publish) => {
            const data = values(form), current = generation, id = courseId;
            if (modalBusy || modalUncertain || token !== modalToken) return;
            modalBusy = true; $("learningSave").disabled = true; publishButton.disabled = true; note("Guardando evaluación…", "", $("learningDialogMessage"));
            try {
                const result = await write("grade_save", id, { assignment_id: assignment.id, enrollment_id: student.enrollment_id, score: data.score, feedback: data.feedback, revision });
                revision = Number.isInteger(result.revision) ? result.revision : revision + 1;
                if (publish) await write("grade_publish", id, { assignment_id: assignment.id, enrollment_id: student.enrollment_id, revision });
                if (!active || current !== generation || token !== modalToken) return;
                modalBusy = false; closeModal();
                const target = $("learningContent"); target.replaceChildren(); await renderGradebook(target, pageOffset); note(publish ? "Evaluación publicada. El alumno ya puede consultarla." : "Borrador guardado. El alumno sigue viendo la última evaluación publicada.", "success");
                dashboardPromise = loadDashboard();
            } catch (error) {
                if (!active || current !== generation || token !== modalToken || unauthorized(error)) return;
                modalUncertain = !["22023", "PT409", "23505"].includes(error?.code); note(writeError(error), "error", $("learningDialogMessage"));
            } finally { if (modal && token === modalToken) { modalBusy = false; $("learningSave").disabled = modalUncertain; publishButton.disabled = modalUncertain; } }
        };
        const dialog = openDialog("Evaluar: " + student.name, (form, token) => saveGrade(form, token, false), "Guardar borrador");
        dialog.fields.append(node("h3", assignment.title));
        if (grade.submitted_at) dialog.fields.append(paragraph("Entregada: " + date(grade.submitted_at), "learning-meta")); else empty(dialog.fields, "El alumno todavía no tiene una entrega registrada. Puedes registrar una calificación si corresponde.");
        if (grade.body) dialog.fields.append(paragraph(grade.body));
        const resource = external("Abrir trabajo entregado ↗", grade.url); if (resource) dialog.fields.append(resource);
        const files = node("div", undefined, "learning-files-area"); dialog.fields.append(files);
        window.PortalLearningFiles?.render(files, { courseId, assignmentId: assignment.id, canManage: true, enrollmentId: student.enrollment_id });
        field(dialog.fields, "score", "Calificación", { type: "number", required: true, min: 0, max: 100, step: 0.01, value: grade.score });
        field(dialog.fields, "feedback", "Comentarios para el alumno", { textarea: true, rows: 5, max: 4000, value: grade.feedback });
        dialog.fields.append(paragraph("Última calificación publicada: " + score(grade.published_score), "learning-meta"));
        const publishButton = button("Publicar evaluación", () => { if (dialog.form.reportValidity()) void saveGrade(dialog.form, dialog.token, true); }, "learning-button secondary"); dialog.actions.insertBefore(publishButton, dialog.actions.lastChild);
        if (typeof grade.published_score === "number") {
            const hide = button("Retirar publicación", () => void submitModal("grade_unpublish", courseId, { assignment_id: assignment.id, enrollment_id: student.enrollment_id, revision }, dialog.token, async () => { const target = $("learningContent"); target.replaceChildren(); await renderGradebook(target, pageOffset); }), "learning-button danger"); dialog.actions.insertBefore(hide, dialog.actions.lastChild);
        }
        dialog.open();
    }

    window.addEventListener("portal-academic-deleted", () => {
        if (active) { dashboardPromise = loadDashboard(); navigate(true); }
    });
    window.addEventListener("portal-learning-files-changed", event => {
        if (active && courseId && event.detail?.courseId === courseId && !modal?.open) void refreshCourse();
        else if (active) dashboardPromise = loadDashboard();
    });
    window.PortalLearning = Object.freeze({ show, clear, navigate, openByCard });
})();
