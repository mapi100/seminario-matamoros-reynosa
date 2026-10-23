(function () {
    "use strict";

    const nav = document.getElementById("workspaceNav");
    const toggle = document.getElementById("menuToggle");
    const courseName = document.getElementById("workspaceCourseName");
    const breadcrumb = document.getElementById("workspaceBreadcrumb");
    const mobile = matchMedia("(max-width:760px)");
    const routes = {
        inicio: "Inicio", "mis-materias": "Mis cursos", "materias-asignadas": "Mis cursos",
        personas: "Personas", clases: "Clases", inscripciones: "Inscripciones",
        profesores: "Profesores", "catalogos-academicos": "Materias y periodos",
        kardex: "Kardex", etapas: "Etapas y semestres", expedientes: "Expedientes", actividad: "Actividad", "mi-perfil": "Mi perfil", curso: "Curso"
    };
    const adminRoutes = {
        personas: "people", clases: "classes", inscripciones: "enrollments",
        profesores: "assignments", actividad: "events"
    };
    const courseRoute = /^curso\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:\/|$)/i;
    let profile;

    function syncMenu() {
        const closed = mobile.matches && !nav.classList.contains("menu-open");
        nav.inert = closed;
        nav.setAttribute("aria-hidden", String(closed || nav.hidden));
    }

    function closeMenu() {
        nav.classList.remove("menu-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Abrir menú");
        syncMenu();
    }

    function setCourseTitle(name, period) {
        if (!profile || document.body.dataset.view !== "curso") return;
        const title = typeof name === "string" ? name : "Curso";
        const term = typeof period === "string" ? period : "";
        courseName.textContent = title;
        courseName.title = term ? title + " · " + term : title;
        courseName.hidden = false;
        breadcrumb.textContent = "Mi campus / " + title;
    }

    function clear() {
        profile = undefined;
        nav.hidden = true;
        closeMenu();
        document.getElementById("controlHome").hidden = true;
        document.getElementById("welcomeTitle").textContent = "Bienvenido al Portal Escolar";
        document.getElementById("workspaceUserName").textContent = "Mi perfil";
        document.getElementById("workspaceAvatar").textContent = "SJ";
        document.getElementById("workspaceCoursesLink").href = "#inicio";
        courseName.textContent = "";
        courseName.removeAttribute("title");
        courseName.hidden = true;
        breadcrumb.textContent = "Mi campus";
        document.body.dataset.view = "inicio";
        for (const link of nav.querySelectorAll("a")) {
            link.hidden = true;
            link.removeAttribute("aria-current");
        }
        for (const kind of ["student", "teacher"]) {
            document.getElementById(kind + "Search").value = "";
            document.getElementById(kind + "Period").replaceChildren(new Option("Todos los periodos", ""));
            document.getElementById(kind + "PeriodTabs").replaceChildren();
            document.getElementById(kind + "FilterStatus").textContent = "";
        }
    }

    function navigate(focus = false) {
        if (!profile) return;
        window.PortalDeletion?.leave();
        const hash = location.hash.slice(1) || "inicio";
        let route = courseRoute.test(hash) ? "curso" : hash;
        if (route !== "curso") {
            const known = Object.hasOwn(routes, route) && route !== "curso";
            const link = nav.querySelector('[data-route="' + (known ? route : "inicio") + '"]');
            if (!known || !link || link.hidden) route = "inicio";
        }
        if (window.PortalPersonalRecord?.canNavigate(route) === false) {
            history.replaceState(null, "", "#" + document.body.dataset.view);
            return;
        }
        document.body.dataset.view = route;
        for (const panel of document.querySelectorAll("[data-screen]")) {
            panel.classList.toggle("view-hidden", !panel.dataset.screen.split(" ").includes(route));
        }
        for (const item of nav.querySelectorAll("a")) {
            if (item.dataset.route === route) item.setAttribute("aria-current", "page");
            else item.removeAttribute("aria-current");
        }
        breadcrumb.textContent = "Mi campus / " + routes[route];
        if (route !== "curso") {
            courseName.hidden = true;
            courseName.textContent = "";
            courseName.removeAttribute("title");
        }
        if (Object.hasOwn(adminRoutes, route)) window.PortalManagement?.openResource(adminRoutes[route]);
        else window.PortalManagement?.leave();
        if (route === "kardex") window.PortalKardex?.openRoute();
        else window.PortalKardex?.leave();
        if (route === "etapas") window.PortalFormation?.openRoute();
        else window.PortalFormation?.leave();
        window.PortalPersonalRecord?.navigate(route);
        window.PortalLearning?.navigate();
        closeMenu();
        if (focus) {
            document.getElementById("panelMain").focus({ preventScroll: true });
            window.scrollTo({ top: 0, behavior: "instant" });
        }
    }

    function show(value) {
        profile = value;
        nav.hidden = false;
        syncMenu();
        for (const link of nav.querySelectorAll("a")) {
            link.hidden = Boolean(link.dataset.roles && !link.dataset.roles.split(" ").includes(profile.role));
        }
        document.getElementById("welcomeTitle").textContent = "Bienvenido, " + profile.full_name;
        document.getElementById("workspaceUserName").textContent = profile.full_name;
        const initials = profile.full_name.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("");
        document.getElementById("workspaceAvatar").textContent = initials.toLocaleUpperCase("es");
        document.getElementById("controlHome").hidden = profile.role !== "control_escolar";
        document.getElementById("workspaceCoursesLink").href = {
            student: "#mis-materias", professor: "#materias-asignadas", control_escolar: "#clases"
        }[profile.role] || "#inicio";
        navigate();
    }

    window.addEventListener("portal-personal-updated", function (event) {
        if (!profile || event.detail?.id !== profile.id || typeof event.detail.full_name !== "string") return;
        profile.full_name = event.detail.full_name;
        document.getElementById("profileName").textContent = profile.full_name;
        document.getElementById("welcomeTitle").textContent = "Bienvenido, " + profile.full_name;
        document.getElementById("workspaceUserName").textContent = profile.full_name;
        document.getElementById("workspaceAvatar").textContent = profile.full_name.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("").toLocaleUpperCase("es");
    });

    toggle.addEventListener("click", function () {
        const open = nav.classList.toggle("menu-open");
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
        syncMenu();
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && nav.classList.contains("menu-open")) {
            closeMenu();
            toggle.focus();
        }
    });
    window.addEventListener("hashchange", () => navigate(true));
    mobile.addEventListener("change", syncMenu);
    document.addEventListener("pointerdown", function (event) {
        if (nav.classList.contains("menu-open") && !nav.contains(event.target) && !toggle.contains(event.target)) closeMenu();
    });
    for (const link of document.querySelectorAll("[data-widget-focus]")) {
        link.addEventListener("click", function () {
            if (!profile) return;
            closeMenu();
            window.setTimeout(function () {
                if (!profile) return;
                const widget = document.getElementById(link.dataset.widgetFocus);
                if (!widget || widget.closest(".view-hidden")) return;
                widget.focus({ preventScroll: true });
                widget.scrollIntoView({ block: "start", behavior: "instant" });
            }, 0);
        });
    }

    for (const [kind, listId, nameClass, periodClass] of [
        ["student", "subjectsList", "subject-name", "subject-period"],
        ["teacher", "teachingList", "teaching-name", "teaching-period"]
    ]) {
        const search = document.getElementById(kind + "Search");
        const period = document.getElementById(kind + "Period");
        const tabs = document.getElementById(kind + "PeriodTabs");
        const list = document.getElementById(listId);
        function rebuildTabs(periods) {
            tabs.replaceChildren();
            for (const value of ["", ...periods]) {
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = value || "Todos";
                button.dataset.period = value;
                button.setAttribute("aria-pressed", String(period.value === value));
                button.addEventListener("click", function () { period.value = value; filter(); });
                tabs.append(button);
            }
        }
        function filter() {
            const cards = [...list.children];
            const selected = period.value;
            const periods = [...new Set(cards.map(card => card.querySelector("." + periodClass)?.textContent).filter(Boolean))];
            if ([...period.options].slice(1).map(option => option.value).join("|") !== periods.join("|")) {
                period.replaceChildren(new Option("Todos los periodos", ""), ...periods.map(value => new Option(value, value)));
                period.value = periods.includes(selected) ? selected : "";
                rebuildTabs(periods);
            } else if (!tabs.children.length && cards.length) rebuildTabs(periods);
            for (const button of tabs.querySelectorAll("button")) {
                button.setAttribute("aria-pressed", String(button.dataset.period === period.value));
            }
            const needle = search.value.trim().toLocaleLowerCase("es");
            let visible = 0;
            for (const card of cards) {
                window.PortalCourseColors?.apply(card, card.querySelector(".subject-code,.teaching-code")?.textContent);
                const text = ((card.querySelector("." + nameClass)?.textContent || card.textContent) + " " +
                    (card.querySelector(".subject-code,.teaching-code")?.textContent || "")).toLocaleLowerCase("es");
                card.hidden = Boolean((needle && !text.includes(needle)) ||
                    (period.value && card.querySelector("." + periodClass)?.textContent !== period.value));
                if (!card.hidden) visible += 1;
            }
            document.getElementById(kind + "FilterStatus").textContent = (needle || period.value)
                ? visible + " coincidencias entre las materias mostradas." : "";
        }
        search.addEventListener("input", filter);
        period.addEventListener("change", filter);
        new MutationObserver(filter).observe(list, { childList: true });
    }

    window.PortalWorkspace = Object.freeze({ show, clear, navigate, setCourseTitle });
})();
