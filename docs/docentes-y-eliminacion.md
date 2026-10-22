# Control Escolar docente y eliminación definitiva

Esta actualización permite asignar a un sacerdote de Control Escolar como
profesor sin quitarle la administración. También añade el borrado definitivo de
clases, materias y periodos. Instalarla no borra ningún registro existente.

## Instalación

1. Copia el contenido del paquete en la raíz del proyecto, combinando carpetas y
   reemplazando archivos. Conserva el escudo nuevo y el aula virtual ya publicados.
2. En Supabase → SQL Editor ejecuta **una sola vez**
   `supabase/migrations/20261022000000_staff_teaching_deletion.sql` completo.
   Requiere que las migraciones anteriores, incluidas 800 y 900, estén aplicadas.
3. Publica los archivos en GitHub y recarga el portal con Ctrl + F5.

```powershell
git add portal docs supabase/migrations tests supabase/tests
git commit -m "Permitir Control Escolar docente y eliminar clases y periodos"
git push origin main
```

La migración instala las funciones, políticas y la bandeja de limpieza; no
cambia el rol de ninguna persona, asigna profesores ni ejecuta eliminaciones.
No requiere Edge Functions, claves privadas en el navegador ni servicios nuevos.

## Padre Martín: una cuenta para ambas funciones

En **Personas**, comprueba que su perfil esté activo y tenga rol **Control
Escolar**, que es el rol administrativo del portal. En **Clases → Asignar
profesor**, selecciona su nombre: la lista ahora incluye profesores y personal
activo de Control Escolar. La opción muestra el rol junto al nombre.

Mantiene Personas, Clases, Inscripciones, Materias y periodos y Actividad. En
**Mis cursos** ve las clases que le asignaron. Desde la clase puede publicar
anuncios, organizar contenidos, crear tareas, revisar entregas y calificar.
Control Escolar conserva además la administración de todos los cursos activos.
No necesita otra cuenta ni otra contraseña.

Si otra persona necesita pasar de Profesor a Control Escolar, se puede cambiar
ese rol en Personas conservando sus asignaciones docentes. Una cuenta con
historial de alumno no puede convertirse en personal desde este formulario.
Nadie puede quitarse a sí mismo su acceso administrativo.

## Qué elimina cada botón

| Opción | Alcance |
| --- | --- |
| Clases → Eliminar clase | La clase elegida en ese periodo y su información académica; conserva la materia del catálogo y el periodo. |
| Materias y periodos → Eliminar materia | La materia del catálogo y todas sus clases, en todos los periodos. |
| Materias y periodos → Eliminar periodo | El periodo y todas sus clases, independientemente de la materia. |

Se eliminan inscripciones, asignaciones docentes, programa, contenidos y avances,
anuncios del curso, tareas, entregas e historial de entregas, notas publicadas,
borradores, historial de notas finales, eventos del curso y adjuntos. Incluye
registros inactivos. Los anuncios y eventos generales del campus se conservan.
Las cuentas de alumnos y sacerdotes, otros cursos y los registros de auditoría
administrativa se conservan. Se registra quién eliminó el registro y el alcance.

Antes del borrado se muestra el nombre completo y un resumen de cantidades. Se
requiere escribir **ELIMINAR** exactamente. Si cambia el alcance o las cantidades
mientras se confirma, el servidor rechaza la solicitud y pide volver a revisarla.
El permiso se comprueba en la base de datos; alumnos y profesores no pueden
borrar cursos ni catálogos, incluso invocando directamente las funciones.

**Desactivar clase** sigue disponible para conservar el expediente y bloquear
su uso. La eliminación definitiva no se puede deshacer desde el portal.

## Archivos y fallas de conexión

La información académica se borra en una transacción. Los adjuntos físicos se
eliminan después mediante la API oficial de Supabase Storage; nunca se borran
solo sus metadatos con SQL. Se mantiene una bandeja privada con las rutas hasta
comprobar que los objetos desaparecieron. También se incluyen archivos subidos
al curso que todavía no estaban registrados en una entrega.

Si falla Storage, el portal informa que hay una limpieza pendiente y permite
**Reintentar limpieza de archivos**. El avance sobrevive al cierre del navegador;
otra cuenta activa de Control Escolar puede completarlo. Se procesa un máximo
de 1.000 archivos por intento, en lotes de 100. Si quedan más, se continúa con el
mismo botón. Los alumnos y profesores pierden acceso a los archivos del curso
en cuanto se elimina la información académica, aunque la limpieza física tarde.

## Verificación local

- `python3 supabase/tests/run_staff_deletion_local.py`: Docker con PostgreSQL 17
  desechable sin red. Prueba permisos, asignación docente, notas, eliminación de
  dependencias, conflictos concurrentes y RLS de Storage. Auth y Storage usan
  fixtures: esta prueba no valida el servicio HTTP de Storage real.
- `python3 tests/portal_staff_deletion.py`: navegador con SDK real y API simulada.
  Comprueba selección de Control Escolar, confirmación, errores, limpieza
  reanudable y presentación móvil. Requiere Playwright y Chromium.
- Regresiones: `tests/portal_workspace.py` y `tests/portal_control_catalogs.py`.

Estas comprobaciones no acceden a datos reales ni envían correos.
