(function () {
    "use strict";
    // La API conserva su contrato 0–100. Nunca migrar notas dividiéndolas en SQL.
    const valid = value => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
    const format = value => valid(value) ? (Math.round((value / 10 + Number.EPSILON) * 10) / 10).toFixed(1) : "";
    function toWire(value, previous) {
        const text = String(value ?? "").trim();
        if (!/^(?:\d|10)(?:\.\d)?$/.test(text) || Number(text) > 10) throw new Error("Escribe una calificación de 0 a 10 con un decimal.");
        // Una edición de comentarios no redondea una nota histórica sin avisar.
        if (valid(previous) && Number(text) === Number(format(previous))) return previous;
        return Math.round(Number(text) * 10);
    }
    window.PortalGradeScale = Object.freeze({ format, toWire, valid, minimum: 7 });
}());
