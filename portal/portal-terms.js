(function () {
    "use strict";

    // Las migraciones instaladas todavía pueden devolver textos de la interfaz
    // anterior. Ajustar solo los mensajes que se van a mostrar.
    function seminarian(value) {
        return String(value ?? "").replace(/\balumn[oa]s?\b/gi, word => {
            const label = word.toLowerCase().endsWith("s") ? "seminaristas" : "seminarista";
            if (word === word.toUpperCase()) return label.toUpperCase();
            return word[0] === word[0].toUpperCase() ? label[0].toUpperCase() + label.slice(1) : label;
        });
    }

    window.PortalTerms = Object.freeze({ seminarian });
}());
