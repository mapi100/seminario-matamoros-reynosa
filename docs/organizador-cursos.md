# Organizador de materias y selección de clases

Actualización sobre `777e65f`. Control Escolar puede organizar las clases por
periodo, etapa y curso formativo; las funciones de alumnos y profesores se conservan.

## Instalar

1. En Supabase → SQL Editor, ejecutar una vez completo:
   `supabase/migrations/20261101000000_course_organizer.sql`.
   Requiere la migración anterior `20261031000000_course_formation_groups.sql`.
   Si hay duda, comprobar solo la presencia de la tabla antes de instalar:

   ```sql
   select to_regclass('public.course_formation_groups');
   ```

   Si devuelve el nombre, no repetir la migración anterior. Si devuelve null,
   instalar primero esa actualización anterior con sus dependencias verificadas.
2. Copiar los archivos del paquete sobre el repositorio y publicar en GitHub Pages.
3. Recargar el portal con Ctrl+F5.

**No repetir el alta de alumnos ni la carga de las 134 clases del Excel.** Esta
migración no crea cuentas, no carga clases, no reasigna alumnos ni modifica notas.
Si el SQL falla, revisar el mensaje y ejecutar `rollback;` para salir de una
transacción abortada antes de seguir. No conceder permisos abiertos para resolverlo.

## Inscribir alumnos / asignar profesores

El selector de clase permite:

1. Elegir el periodo académico; propone el periodo actual cuando existe.
2. Filtrar por Introductorio, Filosofía, Teología o Sin clasificar.
3. Elegir un curso concreto, como CI-2 o 2F-3.
4. Buscar el nombre de la materia y seleccionarla dentro de sus grupos.

Se muestran todas las clases activas del periodo, sin limitarse a las primeras 50.
Cambiar un filtro no altera las clases o los alumnos. Si falla la consulta,
**Reintentar lista** vuelve a consultar conservando la selección del alumno.
Los filtros auxiliares no se envían como campos de una inscripción.

El código anterior solo solicitaba una página y convertía cualquier error de
consulta o validación en un mensaje genérico sin reintento. No se tuvo acceso a
la consola/registro productivo para identificar la respuesta exacta que produjo
el fallo de la captura. El nuevo camino evita ese selector, usa una lectura
completa por periodo y ofrece recuperación explícita. Mientras falta la RPC nueva,
la compatibilidad consulta `portal_admin_read` por páginas de 100 hasta completarlas.

## Materias y periodos

El nuevo tablero aparece arriba de los formularios existentes:

- Seleccionar **Periodo académico** define qué clases se organizan.
- Cada bloque CI/F/T muestra cuántas materias contiene. Pulsarlo muestra sus clases.
- **Ver todas** recupera la lista del periodo.
- Arrastrar una materia a otro bloque guarda su nueva clasificación.
- **Mover** abre un selector de destino; permite la misma operación con teclado
  y en celular, sin arrastrar. En pantallas estrechas, pulsar un bloque lleva a la lista.
- **Sin curso asignado** retira la clasificación, conservando la clase y sus datos.
- **Agregar desde catálogo** muestra materias que todavía no tienen una clase en
  ese periodo. Arrastrarlas a un bloque o usar **Abrir y asignar curso** crea una
  clase nueva en el periodo seleccionado y la clasifica en una sola transacción.
- Las clases inactivas conservan su estado. Organizarlas no las reactiva.

Mover una clase **no cambia de periodo**, no copia materias al siguiente semestre,
no promueve alumnos y no modifica el plan del kardex o la etapa personal de un
seminarista. Conserva profesores, inscripciones, tareas, contenidos y calificaciones.
La materia de catálogo permanece disponible para otros periodos. Los snapshots de
boletas y kardex ya emitidos mantienen sus datos originales.

Si otra persona cambió una clasificación, el servidor rechaza una revisión antigua.
Ante conflicto o respuesta incierta, las operaciones de movimiento se bloquean
hasta **Actualizar**. No hay reenvío automático de escrituras ni borrados de
compensación. Cambiar de sección o de cuenta descarta la información de pantalla
y las respuestas tardías no la vuelven a mostrar.

## SQL y permisos

Se añaden dos RPC:

- `portal_course_board_read(p_period)`: exige Control Escolar activo; devuelve
  periodos, catálogo y clases del periodo con clasificación y revisión.
- `portal_course_board_write(p_subject,p_period,p_course,p_group,p_revision)`:
  Control Escolar activo; comprueba los vínculos y la revisión, valida el curso,
  abre una clase únicamente si se solicita desde catálogo y no existía, y audita.

La tabla `course_formation_groups` admite `group_code = null` para conservar la
metadata docente cuando una clase queda Sin clasificar. El módulo de etiquetas
admite esta representación; no se eliminan filas para retirar la clasificación.
Los permisos de lectura/escritura directa y RLS de la tabla permanecen cerrados.
Anónimos, profesores y alumnos no pueden usar estas RPC administrativas.

Las escrituras emplean el bloqueo académico `72643219`, transacción y revisión.
Una clase recién creada por otra operación provoca conflicto, no duplicados ni
cambios silenciosos a esa clase. Los IDs de materia, clase y periodo se validan
juntos. La notificación a PostgREST actualiza la caché de funciones al instalar.

## Verificación local

```bash
python3 supabase/tests/run_course_organizer_local.py
python3 tests/portal_course_organizer.py
python3 tests/portal_workspace.py
python3 tests/portal_course_groups.py
```

Se verificaron 31 casos SQL en PostgreSQL desechable sin red; siete escenarios
nuevos de navegador, 18 del campus y seis de etiquetas/cursos. Incluyen 134 clases,
paginación compatible de 100+34, filtros, reintento conservando el alumno, arrastre,
interacción móvil, apertura atómica desde catálogo, cambios concurrentes, permisos,
notas conservadas y limpieza al navegar. Las personas y materias de prueba son
ficticias. No se ejecutó SQL ni se modificaron datos de producción desde esta sesión.
