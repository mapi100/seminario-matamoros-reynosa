(function () {
    "use strict";
    const palette = ["#286a87", "#5868a0", "#326f63", "#9b6539", "#824c74", "#586c83"];
    function apply(element, key) {
        if (!element) return;
        let hash = 0;
        for (const char of String(key || "curso")) hash = (Math.imul(hash, 31) + char.codePointAt(0)) >>> 0;
        element.style.setProperty("--course-color", palette[hash % palette.length]);
    }
    window.PortalCourseColors = Object.freeze({ apply });
})();
