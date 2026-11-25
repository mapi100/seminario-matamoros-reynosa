(function () {
    "use strict";
    const months = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"];
    const augustDecember2026 = "e81223f1-e12d-4b0a-95fc-6e27f7df4b05";

    function format(period) {
        // Mostrar el periodo oficial, incluso en copias emitidas que guardaron
        // una fecha de cierre en noviembre. Es un ajuste del encabezado.
        if (period.id === augustDecember2026 || /^ago\s*[-–—]\s*dic\s+2026$/i.test(period.name?.trim())) {
            return "AGOSTO A DICIEMBRE 2026";
        }

        const [startYear, startMonth] = period.starts_on?.split("-") ?? [];
        const [endYear, endMonth] = period.ends_on?.split("-") ?? [];
        const first = months[Number(startMonth) - 1];
        const last = months[Number(endMonth) - 1];
        if (!first || !last) return period.name;
        return first + (startYear === endYear ? " A " : " " + startYear + " A ") + last + " " + endYear;
    }

    window.PortalReportPeriod = Object.freeze({ format });
}());
