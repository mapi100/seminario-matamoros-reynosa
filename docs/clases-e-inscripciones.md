# Clases por curso e inscripción desde cada clase

Actualización de interfaz sobre `dc2d029` (`bloques`). Exclusiva de Control Escolar.

## Uso

1. Abrir **Clases** y elegir el **periodo académico**, por ejemplo AGO-DIC 2026.
2. Pulsar un bloque: CI-1, CI-2, 1F-1…3F-6 o 1T-1…4T-8. Los bloques se agrupan
   en Introductorio, Filosofía y Teología y muestran sus cantidades de clases activas.
3. En la tarjeta de una materia, pulsar **Inscribir alumno** o **Asignar profesor**.
4. Buscar y seleccionar a la persona, y **Guardar**. La clase ya está elegida y
   aparece en un resumen: no es necesario volver a buscarla.

Al asignar profesores también aparece el personal de Control Escolar activo.
Asignarlo como docente conserva su rol administrativo. Los alumnos disponibles
son las personas activas con rol `student`. Las mismas validaciones del servidor
siguen controlando los roles, la clase activa y los registros duplicados.

**Ver todas las clases** permite consultar todo el periodo. La búsqueda filtra por
nombre o curso dentro del bloque seleccionado; si todavía no se seleccionó un
bloque, busca en todo el periodo. **Incluir clases inactivas** permite consultarlas;
sus botones de inscripción y asignación permanecen deshabilitados hasta reactivarlas.

**Más opciones** conserva el cambio de curso, la desactivación/reactivación y la
eliminación con su confirmación e impacto existentes. **Entrar al curso** abre el
aula. **Abrir clase** mantiene el formulario anterior y propone el periodo elegido;
una clase nueva aparece en Sin curso asignado hasta clasificarla. **Organizar
materias** lleva al tablero de arrastre de Materias y periodos.

El periodo académico y el curso formativo son selecciones diferentes: CI-1 no es
un periodo de calendario. Cambiar los filtros no mueve materias, no inscribe
grupos completos y no promueve seminaristas al siguiente semestre.

## Corrección de la carga

Antes, la ruta `#clases` usaba `PortalManagement` y `portal_course_classes_read`,
con validación y paginación propias. Materias y periodos usaba
`portal_course_board_read` y sí mostraba los registros en las capturas del usuario.
El mensaje genérico de Clases no mostraba la respuesta SQL que había fallado.
No se obtuvo acceso a los registros de producción para determinar ese error exacto.

Ahora `#clases` usa `PortalClassDirectory` y comparte la lectura validada del
organizador (`PortalCourseOrganizer.readSnapshot` → `portal_course_board_read`).
Ya no depende de `portal_course_classes_read` para mostrar las clases. La lectura
obtiene todas las clases del periodo, incluidas las posteriores a las primeras
30/50; no necesita el cálculo de cantidades de alumnos/profesores de la consulta
anterior. Las tarjetas no inventan esas cantidades.

Una consulta fallida muestra un error y permite **Actualizar**; no se interpreta
como ausencia de clases. Las solicitudes se cancelan al salir y las respuestas
tardías se descartan. Cerrar sesión o perder el rol limpia la información. Los
nombres recibidos se representan con `textContent`, sin interpretar HTML.

Las inscripciones y asignaciones usan el existente `portal_admin_write`, con
`p_action = enroll` o `assign` y solo `class_id`/`person_id`. El identificador de
clase queda fijo en el formulario. Ante una respuesta de escritura incierta, no
se reenvía automáticamente ni se muestra un éxito sin confirmar. El historial de
altas y bajas sigue disponible en Inscripciones y Profesores.

## Instalar

Esta actualización **no incorpora SQL nuevo**. Requiere la actualización del
organizador ya instalada (`20261101000000_course_organizer.sql`), que en las
capturas ya muestra las clases. Si Materias y periodos funciona, no volver a
ejecutar esa migración ni importar de nuevo alumnos o clases.

Copiar los archivos del paquete conservando las carpetas, publicar los cambios en
GitHub y recargar el portal con Ctrl+F5. No se cambiaron cuentas, claves, datos de
producción, permisos SQL, calificaciones, contenidos, boletas o kardex.

Archivos principales:

- `portal/class-directory.js` y `.css`: bloques, tarjetas, búsqueda y acciones.
- `portal/course-organizer.js`: exporta la lectura validada compartida.
- `portal/management.js`: formularios de alumno/profesor con clase fija y apertura
  de clase con periodo preseleccionado.
- `portal/panel.html`, `panel.js` y `workspace.js`: navegación, estilos, control
  de acceso y limpieza de estado.

## Verificación

Pruebas de navegador con Chromium, SDK real de Supabase fijado con SRI y API
simulada. Todas las identidades y materias utilizadas son ficticias; no se
realizan peticiones ni escrituras en Supabase de producción.

```bash
python3 -B tests/portal_class_directory.py
python3 -B tests/portal_workspace.py
python3 -B tests/portal_course_organizer.py
python3 -B tests/portal_course_groups.py
python3 -B tests/portal_staff_deletion.py
```

La cobertura específica incluye 134 clases aun cuando falla la consulta anterior,
inscripción en una clase posterior a las primeras 50, asignación de Control
Escolar como docente sin cambiar su rol, periodos separados, bloques con teclado,
móvil, búsqueda, inactivas/reactivación, error/reintento de lectura, escritura
incierta sin reenvío, salida durante lectura, denegación de acceso y aislamiento
de alumnos/profesores. Las regresiones revisan el organizador, el resto de la
administración y las confirmaciones de eliminación existentes.
