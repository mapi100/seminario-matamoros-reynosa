# Inscripción por etapa y mejoras de lectura

Actualización posterior al paquete de inscripción múltiple, profesores agrupados y
menú en una fila. No añade SQL ni modifica datos al instalarse.

## Uso de la inscripción

1. Abrir una clase desde **Clases → periodo académico → curso** y pulsar
   **Inscribir alumnos**.
2. El formulario propone la etapa y el semestre del curso. Por ejemplo, CI-1
   propone Introductorio / CI-1; 2F-3 propone Filosofía / semestre 3.
3. **Seleccionar resultados** marca a los disponibles de ese grupo; se puede
   afinar la selección buscando un nombre o correo y usando las casillas.
4. **Inscribir N alumnos** conserva la operación por lote y sus reglas anteriores.

Los filtros de **Etapa**, **Semestre / curso** y **Nombre o correo** se combinan.
Las opciones de etapa y semestre muestran sus cantidades de alumnos; incluyen
a los ya inscritos, que siguen identificados y deshabilitados. La lista se ordena
por etapa, semestre y nombre, con encabezados por grupo.

**Ver todas las etapas** retira los filtros y la búsqueda. Cambiar filtros no
borra la selección: el contador indica cuántos seleccionados quedan fuera del
filtro visible. **Quitar selección** permite empezar de nuevo. Solo los resultados
visibles y disponibles se marcan con **Seleccionar resultados**.

## Origen de las etapas

Se usa `student_formation_periods`, mediante la RPC existente
`portal_formation_read` con `p_resource='students'` y **el periodo de la clase**.
Control Escolar registra esos datos en **Etapas y semestres**. No se deduce la
etapa de un nombre, de las materias inscritas ni de otro periodo académico.

Los alumnos sin registro en ese periodo aparecen en **Sin etapa asignada**. Si
ningún candidato tiene etapa registrada, se propone ese grupo y se explica dónde
registrarlas, manteniendo disponibles las inscripciones. Si la etapa sí tiene
registros pero el curso elegido no tiene candidatos, se muestra una lista vacía
real con la posibilidad de cambiar filtros. No se asignan o promueven alumnos
automáticamente.

`enrollment-batch.js` consulta en paralelo los candidatos de la clase y las
trayectorias del periodo, recorriendo estas últimas por páginas de 100 hasta
completarlas (máximo 10 000 registros). Une ambas listas por UUID, conservando
solo los candidatos activos devueltos por la inscripción. Un fallo de lectura de
etapas bloquea el guardado y permite reintentar; no se interpreta como falta de
etapa registrada. Las respuestas inválidas se rechazan y salir o cambiar de
sesión descarta los resultados pendientes.

Los filtros son locales y de lectura. El lote sigue enviando exclusivamente
`p_class` y los UUID de `p_students` a `portal_enroll_students`. Se conservan las
validaciones, permisos de Control Escolar, transacción, tratamiento de duplicados
y reactivaciones de la actualización anterior.

## Tipografía

La hoja `portal/readability.css` aumenta de forma moderada los textos del portal:

- Base de texto de 16 px; menús de alumno y profesor de 17 px en escritorio y
  16 px en celular. El menú de Control Escolar mantiene una fila y desplazamiento
  horizontal cuando necesita espacio.
- Nombres de cursos de 20 px en escritorio y 18 px en celular; etiquetas,
  periodos, estados y acciones dejan de usar varios tamaños de 10–12 px.
- Textos más grandes en anuncios, tareas, formularios, contenido, calificaciones,
  listas de administración y pie del portal.

No se usa zoom ni escalado de la página. La hoja se carga con `media='screen'`,
por lo que no altera los estilos impresos o las emisiones de boletas y kardex.
El sitio público conserva sus estilos. La sesión marca `data-portal-role` para
ajustar los menús de alumno/profesor; se retira al limpiar la sesión.

## Instalar y comprobar

Combinar las carpetas del paquete con el repositorio, reemplazar sus archivos,
publicar en GitHub y recargar con Ctrl+F5. Requiere la inscripción múltiple y las
funciones de formación anteriores; no repetir migraciones o importaciones.

```bash
python3 -B tests/portal_enrollment_stages_readability.py
python3 -B tests/portal_batch_and_professors.py
python3 -B tests/portal_workspace.py
python3 -B tests/portal_class_directory.py
python3 -B tests/portal_formation.py
```

Las pruebas usan Chromium, el SDK real de Supabase y API simulada, sin escribir
en producción. Incluyen 39 candidatos, 159 trayectorias en dos páginas,
preselección de CI/F/T, periodos independientes, orden alfabético, búsqueda con
acentos, selección fuera del filtro, alumnos sin etapa, errores y navegación
durante una lectura. También revisan textos y disposición de alumno/profesor
en escritorio y celular, junto con las regresiones de inscripción y formación.
