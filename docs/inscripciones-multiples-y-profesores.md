# Inscripción múltiple, profesores agrupados y navegación

Actualización sobre `0d5ccc0` (`agregar alumnos`), posterior a Clases por curso.

## Instalar

1. Ejecutar una vez completo en Supabase → SQL Editor:
   `supabase/migrations/20261101010000_batch_enrollment.sql`.
2. Copiar los archivos del paquete sobre el repositorio conservando las carpetas,
   publicar los cambios en GitHub y recargar el portal con Ctrl+F5.

El SQL añade dos funciones con acceso exclusivo a Control Escolar activo. No
importa alumnos o clases y no modifica registros al instalarse. Requiere las
migraciones anteriores de administración (`portal_admin_write`) y el organizador
de clases ya instalado. No repetir esas migraciones ni las importaciones.

No se ejecutó el SQL en producción desde esta sesión: la verificación se hizo en
PostgreSQL desechable y con API simulada en el navegador. Si ya se instaló una
migración, no volver a ejecutarla; si el editor conserva una transacción abortada,
salir con `rollback;` antes de otra consulta.

## Inscribir varios seminaristas

En **Clases → periodo académico → curso → Inscribir alumnos**:

- La materia, el curso y el periodo aparecen arriba y permanecen fijos.
- Se muestran todos los alumnos activos; buscar por nombre o correo filtra la lista.
- Marcar casillas permite seleccionar uno o varios. Cambiar la búsqueda conserva
  las selecciones anteriores, aunque queden fuera del filtro visible.
- **Seleccionar resultados** marca los alumnos disponibles que coinciden con la
  búsqueda. Con la búsqueda vacía, selecciona todos los disponibles.
- **Quitar selección** desmarca las selecciones nuevas.
- Los **Ya inscritos** aparecen marcados y deshabilitados; no se vuelven a inscribir.
- Las bajas previas muestran **Se reactivará su inscripción**. Si se seleccionan,
  se recupera la inscripción existente conservando su identificador e historial.
- **Inscribir N alumnos** guarda el lote y muestra cantidades de nuevos,
  reactivados y ya inscritos. Se admiten hasta 500 seleccionados por operación.

La actualización posterior añade [filtros por etapa y semestre](filtros-etapas-legibilidad.md)
usando el registro personal del periodo de la clase. Control Escolar sigue
pudiendo elegir a cualquier alumno activo mediante Ver todas las etapas. No
promueve ni inscribe automáticamente a toda una etapa. El formulario general de **Inscripciones**
conserva el alta individual anterior; las casillas están en las tarjetas de Clases.

Si se pierde una respuesta de guardado, no se reenvía el lote automáticamente.
**Actualizar lista** vuelve a consultar el estado real, retira de la selección a
quienes ya están inscritos y permite revisar el resto. No se ejecutan bajas para
compensar errores de red.

## Funciones SQL y permisos

- `portal_enrollment_candidates(p_class uuid)`: exige Control Escolar activo y
  clase activa. Devuelve `class_id` e `items` con `id`, `full_name`, `email` y
  `status` (`available`, `inactive`, `enrolled`) de alumnos activos exclusivamente.
- `portal_enroll_students(p_class uuid,p_students uuid[])`: exige Control Escolar
  activo, clase activa y alumnos activos con rol `student`. Valida el lote completo
  antes de escribir y elimina UUID duplicados del argumento. Devuelve `saved`,
  `class_id`, `selected`, `enrolled`, `reactivated` y `already_enrolled`.

La escritura usa una sola transacción y el mismo bloqueo de administración
`72643219`. Reutiliza `portal_admin_write('enroll',...)` para las altas/reactivaciones,
manteniendo su auditoría y validaciones. Una inscripción activa se omite sin error;
una baja se reactiva conservando sus notas y relaciones. Si falla una operación,
se revierten todo el lote y sus eventos de auditoría. Dos controles que inscriban
simultáneamente el mismo lote no duplican registros.

Ambas funciones tienen `security definer`, `search_path=''`, revocación de acceso
a `public`/`anon` y permiso `execute` para `authenticated`; cada llamada comprueba
el rol real en la base. No se amplían permisos sobre tablas ni políticas RLS.
El límite de lectura del cliente es 10 000 candidatos; la escritura acepta de 1 a
500 entradas, sin nulos y en una sola dimensión.

## Profesores

La sección **Profesores** consulta todas las páginas de asignaciones que coinciden
con la búsqueda y las agrupa por `person_id`, no por nombre. Cada profesor aparece
una vez con el número de clases. Dos personas distintas con el mismo nombre
permanecen separadas.

Al desplegar un profesor, sus materias aparecen agrupadas por periodo. Cada
asignación conserva **Dar de baja / Reactivar** y **Entrar al curso**. **Asignar
otra clase** abre el formulario con ese profesor seleccionado. El botón general
**Asignar profesor** y la selección de personal de Control Escolar como docente
siguen disponibles.

Los grupos no se parten entre páginas. Si falla una página, no se presenta un
grupo incompleto como si fuera definitivo; se muestra el error con Actualizar.
Cuando se busca una materia o periodo, se muestran las asignaciones coincidentes,
indicándolo en el contador. Esta agrupación es visual y no fusiona personas ni
modifica sus roles.

## Barra superior

En escritorio, el menú conserva una sola fila e incluye **Mi perfil**. Aprovecha
hasta 1440 px; cuando no cabe, se desplaza horizontalmente sin crear una segunda
fila. Al navegar, el enlace activo se mantiene dentro del área visible. En celular
se conserva el menú lateral desplegable.

## Archivos y comprobaciones

`portal/enrollment-batch.js` y `.css` implementan el diálogo de selección.
`class-directory.js` abre ese diálogo y muestra el resumen del resultado.
`management.js` agrupa profesores y permite preseleccionarlos al asignar otra
clase. `workspace.css/js`, `panel.html` y `panel.js` integran la navegación y la
limpieza de estado al salir, cerrar sesión o cambiar de rol.

```bash
python3 -B supabase/tests/run_batch_enrollment_local.py
python3 -B tests/portal_batch_and_professors.py
python3 -B tests/portal_class_directory.py
python3 -B tests/portal_workspace.py
python3 -B tests/portal_course_organizer.py
python3 -B tests/portal_staff_deletion.py
python3 -B tests/portal_course_groups.py
```

PostgreSQL 17 se ejecuta en un contenedor desechable sin red. Las pruebas de
navegador usan Chromium, el SDK real de Supabase con SRI y API simulada. Se prueban
38 alumnos ficticios, escritura atómica, reactivación con notas intactas,
duplicados, concurrencia, permisos y lotes inválidos; en interfaz, selección y
filtros, móvil, errores y respuestas tardías, 217 asignaciones de tres páginas,
identidades con nombres iguales y navegación entre 850 y 1920 px. Ninguna prueba
escribe en el Supabase de producción.
