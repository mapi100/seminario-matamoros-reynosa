# Grupos dentro de Etapas y semestres

Esta mejora amplía la sección existente de Control Escolar. No añade una sección a la navegación.

## Instalación

1. Copiar los archivos de esta actualización sobre el repositorio y conservar la estructura de carpetas.
2. En Supabase SQL Editor ejecutar **una sola vez** `supabase/migrations/20261101020000_formation_group_batches.sql`. Requiere las migraciones anteriores, incluida `20261101010000_batch_enrollment.sql`.
3. Publicar los archivos del portal mediante el procedimiento habitual de GitHub Pages y recargar el navegador con Ctrl+F5.

La instalación solo añade funciones y permisos de ejecución específicos; no carga alumnos, no asigna etapas ni crea inscripciones. El SQL fue comprobado en PostgreSQL desechable; su ejecución en producción corresponde al administrador. No se usaron credenciales de producción.

## Uso por Control Escolar

1. Abrir **Etapas y semestres** y elegir el **periodo académico**.
2. Elegir el bloque **CI-1, CI-2, 1F-1…4T-8**. Cada bloque muestra su número de seminaristas activos y materias activas.
3. Pulsar **Agregar seminaristas**. Por defecto muestra los que aún no tienen curso en ese periodo, si los hay. Se puede cambiar a otro curso o a todos, buscar por nombre/matrícula, marcar varios o seleccionar todos los resultados. La selección se conserva al filtrar y muestra cuántos seleccionados quedaron fuera del filtro.
4. Pulsar **Revisar cambios**. La revisión enumera los nombres, el curso anterior y el nuevo. Confirmar asigna la etapa y el semestre derivados del bloque elegido. Un cambio de curso afecta solo al periodo seleccionado; no promueve automáticamente otros periodos ni modifica inscripciones anteriores.
5. Pulsar **Inscribir en materias** dentro del bloque. Se preseleccionan sus seminaristas y materias activas del mismo periodo. Es posible desmarcar personas o materias para hacer excepciones.
6. Revisar el resumen de inscripciones nuevas, existentes y bajas. Las existentes se omiten. Las bajas se conservan salvo que se marque expresamente **Reactivar también las inscripciones dadas de baja**. Confirmar guarda el lote completo.

Asignar el curso y hacer las inscripciones son dos acciones distintas. La asignación del curso no elimina materias que un alumno ya tuviera; esas excepciones se revisan en Clases o Inscripciones. Las notas y la trayectoria de otros periodos se conservan.

Las materias del bloque provienen de **Materias y periodos**, no del nombre o código interno de la materia. Las clases inactivas y sin clasificación no se ofrecen para inscribir grupos. Si un bloque no tiene materias, organizarlas primero allí. Si no tiene seminaristas, agregarlos primero. Continúan disponibles la consulta individual, su historial y los flujos de inscripción por clase.

## Implementación

- `portal/formation-groups.js` y `.css`: bloques, listas, filtros, selección, revisión y confirmación; integrados en `formation.js`/`panel.html` y su ciclo de navegación/sesión. Soportan claro, oscuro y OLED.
- `portal_formation_group_read(p_period uuid)`: lectura exclusiva de Control Escolar activo. Devuelve alumnos activos con rol student, su formación en ese periodo, materias activas clasificadas y estados de inscripción. No devuelve contraseñas, expediente personal ni correos de Auth.
- `_formation_group_snapshot(uuid)`: función interna sin permiso de ejecución para anon/authenticated. Genera la lectura y un token determinista del estado del periodo, con orden estable.
- `portal_formation_group_write(p_action,p_period,p_stage,p_semester,p_students,p_token,p_classes,p_reactivate)`: operaciones `assign` o `enroll`, exclusiva de Control Escolar activo. Revalida personas, periodo, etapa, semestre y clases en PostgreSQL. Los permisos se obtienen de profiles, nunca de metadatos enviados por el navegador.
- El token exige que el estado consultado siga vigente al confirmar. Otro cambio en alumnos, formación, clases o inscripciones del mismo periodo puede requerir actualizar incluso si afectó a otra parte del tablero. Un token no concede permisos ni sustituye las validaciones de pertenencia al curso.
- Las escrituras usan la misma exclusión transaccional (`pg_advisory_xact_lock(72643219)`) que las funciones administrativas existentes y bloqueos sobre las filas relevantes. Cada lote es una transacción: un fallo intermedio revierte también la auditoría previa.
- `assign` reutiliza `portal_formation_save` y su auditoría/revisiones. `enroll` reutiliza `portal_admin_write('enroll',…)`; al reactivar mantiene el identificador de la inscripción y sus notas. No se borran filas ni se altera la escala de calificaciones.
- Límites: hasta 500 seminaristas y 100 materias, máximo 5000 combinaciones por lote. UUID duplicados se deduplican en el servidor.
- No hay nueva tabla, política RLS, cambio de rol ni datos personales incorporados al repositorio.

## Si aparece un error

- **Falta instalar el SQL de grupos**: instalar la migración; la consulta individual sigue funcionando.
- **El grupo o sus materias cambiaron**: cerrar, actualizar, revisar y confirmar una nueva selección.
- **No se pudo confirmar el guardado**: no reenviar automáticamente. Cerrar y actualizar para comprobar el resultado; la respuesta puede haberse perdido después de guardar. Al repetir una revisión actualizada, las inscripciones activas se omiten y las asignaciones iguales no generan cambios.
- Si se revoca el acceso, la pantalla elimina los datos y vuelve a comprobar la sesión. Las respuestas tardías no restauran la sección tras navegar o cerrar sesión.

## Verificación local

```bash
python3 supabase/tests/run_formation_groups_local.py
python3 tests/portal_formation_groups.py
python3 tests/portal_formation.py
```

Las pruebas SQL usan Docker/PostgreSQL 17 sin red, con usuarios ficticios. Comprueban permisos, validación, 10×2 inscripciones, preservación de bajas/notas/historia, rollback completo, idempotencia y dos controles concurrentes. El navegador usa el SDK real con API simulada; comprueba selección, filtros, revisión, excepciones, conflictos, respuestas inciertas, navegación, texto seguro y móviles en los tres temas. No sustituyen una comprobación funcional después de instalar el SQL y publicar el portal.

## Corregir seminaristas o materias agregados por error

Instalar una sola vez la migración adicional `supabase/migrations/20261101030000_remove_formation_group_members.sql` y publicar los archivos actualizados. Instalarla solo crea una función: no retira automáticamente a ninguna persona ni materia.

Dentro del bloque elegido aparecen **Quitar seminaristas** y **Quitar materias**:

1. Verificar el periodo en el selector principal. Para corregir el ejemplo de diez asignados por error a CI-1 en enero–mayo, elegir **ENE-MAY 2027 → CI-1 → Quitar seminaristas**.
2. Marcar uno, varios o usar **Seleccionar resultados** para todos los mostrados. La búsqueda conserva la selección y avisa si hay seleccionados fuera del filtro.
3. Pulsar **Revisar selección**. La ventana muestra periodo, curso y todos los nombres elegidos. **Volver a la selección** borra cualquier confirmación escrita anteriormente.
4. Escribir **CONFIRMAR** y pulsar **Confirmar y quitar**. Cancelar o Escape antes de enviar no realiza cambios.

### Alcance de cada acción

- **Quitar seminaristas** elimina únicamente su registro en `student_formation_periods` para el periodo y el curso revisados. Quedan sin etapa/semestre en ese periodo y pueden volver a agregarse. No borra sus cuentas, expedientes ni asignaciones de otros periodos. Cada retirada queda registrada en `management_events` con etapa, semestre y revisión anteriores; Actividad la muestra como «Etapa y semestre retirados del periodo».
- Las inscripciones en materias siguen siendo independientes de la formación. Si los seleccionados tienen inscripciones activas, la revisión avisa que seguirán activas. Si también fueron un error, se pueden dar de baja mediante Clases o Inscripciones. No se dan de baja automáticamente ni se eliminan calificaciones.
- **Quitar materias** deja `course_formation_groups.group_code` en NULL mediante `portal_course_board_write`, conservando la fila y aumentando su revisión. No elimina la materia del catálogo ni la clase del periodo. Conserva docentes, tareas, entregas, inscripciones y notas. Puede volver a organizarse desde **Materias y periodos**, mostrando todas las clases del periodo. Otros periodos conservan sus propias clases y clasificación.
- Los documentos ya emitidos conservan sus snapshots; esta corrección no reescribe copias históricas.

### Seguridad y recuperación

`portal_formation_group_remove(p_kind,p_period,p_stage,p_semester,p_ids,p_token,p_confirmation)` exige Control Escolar activo, confirmación escrita, curso/semestre válidos y pertenencia de **todos** los seleccionados al grupo y periodo. Tipos: `students` o `classes`. Límites: 500 seminaristas o 100 materias; deduplica UUID repetidos. La función no está disponible para anon y utiliza `security definer` con `search_path=''`; no amplía políticas RLS.

Cada lote es una transacción con el mismo bloqueo administrativo y token de revisión de la lectura original. Una modificación concurrente exige actualizar. Un fallo intermedio revierte también la auditoría de las retiradas anteriores. Si la respuesta se pierde, el portal desactiva el envío y permite cerrar y actualizar para comprobar qué ocurrió; no reenvía automáticamente.

Pruebas adicionales, exclusivamente con datos ficticios:

```bash
python3 supabase/tests/run_formation_removal_local.py
python3 tests/portal_formation_removal.py
```

Cubren los dos periodos con diez alumnos cada uno, confirmación obligatoria en servidor y navegador, permisos, lotes inválidos, duplicados, conservación de relaciones académicas, auditoría, rollback, concurrencia, volver a agregar, selección/búsqueda, cancelación, revocación de acceso, respuestas tardías y temas claro/oscuro/OLED en móvil.
