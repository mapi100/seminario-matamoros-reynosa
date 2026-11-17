# Inicio personal de Control Escolar

Una cuenta de Control Escolar puede administrar todas las materias. Su inicio
personal muestra las tareas, los avisos de cursos y los eventos de las clases
activas en las que tiene una asignación docente activa. Conserva los avisos y
eventos institucionales, y la administración de borradores institucionales.

Esto aplica a cualquier cuenta de Control Escolar: no depende del nombre ni del
correo del padre Martín. Una cuenta sin asignaciones docentes ve el contenido
institucional y ningún trabajo de materias ajenas. Si se retira una asignación
o se desactiva su clase, ese contenido deja de aparecer al actualizar el inicio.

## Activar

1. Abre `supabase/migrations/20261117000000_control_personal_dashboard.sql` en
   GitHub y copia su contenido completo con **Copy raw file**.
2. Pégalo en una consulta nueva del SQL Editor del proyecto habitual del
   Seminario, con el rol `postgres`, y pulsa **Run**.
3. Recarga el portal y abre **Inicio** con la cuenta de Control Escolar.

No hace falta descargar un ZIP, ejecutar Python ni modificar el código de la
página. Integrar el archivo en GitHub conserva el historial, pero no instala
automáticamente las funciones en Supabase: el paso del SQL Editor es necesario.
La migración se puede repetir y no cambia asignaciones, cuentas, actividades,
entregas, calificaciones ni documentos emitidos.

## Comportamiento y compatibilidad

El filtrado ocurre en PostgreSQL antes de limitar los avisos y tareas a 50 y
los eventos a 100. Un gran número de actividades de otros profesores no desplaza
las de la persona que consulta el inicio. Se consideran todas sus asignaciones,
independientemente de la página del directorio de cursos.

El directorio de **Mis cursos** sigue mostrando todas las materias a Control
Escolar, que conserva el acceso a su contenido, participantes y calificaciones.
Las tarjetas de **Mis cursos como profesor** siguen mostrando sus titularidades.
Las cuentas de profesores y alumnos mantienen el comportamiento anterior,
incluido retirar del trabajo pendiente las tareas que el alumno ya entregó.

Se conserva la firma de `portal_learning_read` y los campos de evaluación por
categorías que agrega el envoltorio de ponderaciones. El nuevo helper no permite
ejecución directa a roles públicos y comprueba el perfil activo del solicitante.

## Comprobar en desarrollo

```sh
python3 supabase/tests/run_control_personal_dashboard_local.py
```

Usa PostgreSQL desechable sin red ni datos reales. Comprueba docencia propia,
institucionales, saturación de actividades ajenas, bajas, clases inactivas,
paginación, permisos, compatibilidad de alumnos/profesores y reinstalación sin
modificar datos.
