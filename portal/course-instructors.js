(function () {
    "use strict";

    function render(instructors, compact = false) {
        const valid = Array.isArray(instructors) && instructors.length <= 100 && instructors.every(
            person => person && typeof person.name === "string" && person.name.trim() && person.name.length <= 300
        );
        const names = valid ? instructors.map(person => person.name.trim()) : null;
        const section = document.createElement(compact ? "div" : "section");
        section.className = "course-instructors" + (compact ? " compact" : " learning-card");
        section.dataset.instructorsState = names === null ? "unavailable" : names.length ? "assigned" : "empty";
        const heading = document.createElement(compact ? "span" : "h2");
        heading.className = "course-instructors-label";
        heading.textContent = compact
            ? names?.length > 1 ? "Docentes" : "Docente"
            : names?.length > 1 ? "Docentes del curso" : "Docente del curso";
        section.append(heading);
        if (names?.length) {
            const list = document.createElement("ul");
            list.className = "course-instructors-names";
            for (const name of names) {
                const item = document.createElement("li");
                item.textContent = name;
                list.append(item);
            }
            section.append(list);
        } else {
            const empty = document.createElement("p");
            empty.className = "course-instructors-empty";
            empty.textContent = names === null ? "Nombre del docente no disponible. Actualiza la información." : "Pendiente de asignación";
            section.append(empty);
        }
        return section;
    }

    window.PortalCourseInstructors = Object.freeze({ render });
})();
