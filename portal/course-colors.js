(function () {
    "use strict";
    const palette = ["#286a87", "#5868a0", "#326f63", "#9b6539", "#824c74", "#586c83"];
    const siteBase = new URL("../", document.currentScript.src);
    const imageBase = new URL("images/", siteBase);
    const covers = (Array.isArray(window.PortalCourseImages) ? window.PortalCourseImages : []).flatMap(entry => {
        if (!entry || typeof entry.src !== "string" || !entry.src.startsWith("images/")) return [];
        try {
            const url = new URL(entry.src, siteBase);
            if (url.origin !== siteBase.origin || !url.href.startsWith(imageBase.href) || url.search || url.hash) return [];
            const position = /^\d{1,3}% \d{1,3}%$/.test(entry.position) ? entry.position : "50% 50%";
            return [{ id: entry.src, url: url.href, position }];
        } catch { return []; }
    });
    function hash(value) {
        let result = 2166136261;
        for (const char of value) result = Math.imul(result ^ char.codePointAt(0), 16777619);
        result = Math.imul(result ^ result >>> 16, 0x85ebca6b);
        result = Math.imul(result ^ result >>> 13, 0xc2b2ae35);
        return (result ^ result >>> 16) >>> 0;
    }
    function apply(element, code, period = "") {
        if (!element) return;
        const key = JSON.stringify([String(code || "curso").trim().normalize("NFC"), String(period).trim().normalize("NFC")]);
        element.style.setProperty("--course-color", palette[hash(key) % palette.length]);
        // Sorteo reproducible por clase. Añadir una foto solo cambia las clases
        // para las que la nueva foto obtiene la mayor puntuación; no se usa el
        // índice de la lista, ni cambia en cada recarga o entre usuarios.
        let selected, best = -1;
        for (const cover of covers) {
            const score = hash(key + "\u001f" + cover.id);
            if (score > best || score === best && cover.id < selected.id) { selected = cover; best = score; }
        }
        if (!selected) {
            element.style.removeProperty("--course-image");
            element.style.removeProperty("--course-image-position");
            return;
        }
        element.style.setProperty("--course-image", 'url("' + selected.url + '")');
        element.style.setProperty("--course-image-position", selected.position);
    }
    window.PortalCourseColors = Object.freeze({ apply });
})();
