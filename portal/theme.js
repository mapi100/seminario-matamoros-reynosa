(function () {
    "use strict";
    const key = "seminario.portal.theme", root = document.documentElement;
    const modes = [
        { value:"light", name:"Claro", description:"La apariencia actual del portal.", icon:"sun" },
        { value:"dark", name:"Oscuro", description:"Gris carbón y contrastes suaves.", icon:"moon" },
        { value:"oled", name:"OLED", description:"Negro puro en los fondos principales.", icon:"oled" }
    ];
    const valid = value => modes.some(mode => mode.value === value);
    let current = "light", trigger, panel, host;
    try { const saved = localStorage.getItem(key); if (valid(saved)) current = saved; } catch { /* El tema sigue funcionando si el navegador bloquea el almacenamiento. */ }
    function apply(value, persist = false) {
        current = valid(value) ? value : "light";
        root.dataset.theme = current;
        root.dataset.themeTone = current === "light" ? "light" : "dark";
        if (persist) try { localStorage.setItem(key, current); } catch { /* Preferencia solo para esta página. */ }
        sync();
    }
    function icon(kind) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
        const shapes = kind === "sun" ? [["circle",{cx:12,cy:12,r:4}], ["path",{d:"M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"}]] : kind === "moon" ? [["path",{d:"M20.5 14.1A8.6 8.6 0 0 1 9.9 3.5 8.8 8.8 0 1 0 20.5 14.1Z"}]] : [["circle",{cx:12,cy:12,r:8}], ["path",{d:"M12 4a8 8 0 0 1 0 16Z",fill:"currentColor",stroke:"none"}]];
        for (const [tag, attributes] of shapes) { const shape = document.createElementNS(svg.namespaceURI, tag); for (const [name,value] of Object.entries(attributes)) shape.setAttribute(name,String(value)); svg.append(shape); }
        return svg;
    }
    function close(focus = false) {
        if (!panel) return;
        panel.hidden = true; trigger.setAttribute("aria-expanded", "false");
        if (focus) trigger.focus({preventScroll:true});
    }
    function sync() {
        if (!trigger) return;
        const mode = modes.find(mode => mode.value === current);
        trigger.replaceChildren(icon(mode.icon));
        const name = document.createElement("span"); name.className = "portal-theme-current"; name.textContent = mode.name;
        trigger.append(name); trigger.title = "Apariencia: " + mode.name;
        trigger.setAttribute("aria-label", "Cambiar apariencia. Tema actual: " + mode.name);
        for (const input of panel.querySelectorAll("input")) input.checked = input.value === current;
    }
    function mount() {
        host = document.querySelector("[data-theme-control]"); if (!host) return;
        host.classList.add("portal-theme");
        trigger = document.createElement("button"); trigger.id = "portalThemeButton"; trigger.type = "button"; trigger.className = "portal-theme-button";
        trigger.setAttribute("aria-controls", "portalThemeOptions"); trigger.setAttribute("aria-expanded", "false");
        panel = document.createElement("div"); panel.id = "portalThemeOptions"; panel.className = "portal-theme-options"; panel.hidden = true;
        const fieldset = document.createElement("fieldset"), legend = document.createElement("legend"); legend.textContent = "Apariencia del portal"; fieldset.append(legend);
        for (const mode of modes) {
            const label = document.createElement("label"), input = document.createElement("input"), swatch = document.createElement("span"), text = document.createElement("span"), title = document.createElement("strong"), description = document.createElement("small");
            input.type = "radio"; input.name = "portal-theme"; input.value = mode.value;
            swatch.className = "portal-theme-swatch " + mode.value; swatch.setAttribute("aria-hidden", "true"); swatch.append(icon(mode.icon));
            title.textContent = mode.name; description.textContent = mode.description; text.append(title,description); label.append(input,swatch,text); fieldset.append(label);
            input.addEventListener("change", () => { if (input.checked) apply(mode.value,true); });
        }
        panel.append(fieldset); host.append(trigger,panel); sync();
        trigger.addEventListener("click", () => { const open = panel.hidden; if (open) host.style.setProperty("--theme-menu-top",Math.ceil(trigger.getBoundingClientRect().bottom + 10)+"px"); panel.hidden = !open; trigger.setAttribute("aria-expanded",String(open)); if (open) panel.querySelector("input:checked")?.focus(); });
        document.addEventListener("pointerdown", event => { if (!host.contains(event.target)) close(); });
        document.addEventListener("keydown", event => { if (event.key === "Escape" && !panel.hidden) { event.preventDefault(); event.stopImmediatePropagation(); close(true); } },true);
        document.addEventListener("focusin", event => { if (!host.contains(event.target)) close(); });
        window.addEventListener("hashchange", () => close());
        window.addEventListener("resize", () => close());
        document.addEventListener("visibilitychange", () => { if (document.hidden) close(); });
    }
    window.addEventListener("storage", event => { if (event.key === key || event.key === null) apply(valid(event.newValue) ? event.newValue : "light"); });
    apply(current);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",mount,{once:true}); else mount();
})();
