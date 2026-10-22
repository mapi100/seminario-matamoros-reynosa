# API del aula virtual

El aula utiliza RPC de PostgreSQL y un bucket privado de Supabase Storage.
El navegador recibe proyecciones autorizadas; no tiene acceso directo a las
tablas `learning_*`. No se cargan datos de demostración en las migraciones.

## Consultas

`portal_learning_read(p_resource text, p_course uuid = null, p_offset integer = 0, p_limit integer = 30) → jsonb`

| Recurso | Resultado |
| --- | --- |
| `dashboard` | Cursos activos autorizados, anuncios publicados, pendientes, eventos y `has_more_courses`. Control Escolar recibe además `institutional_announcements` para editar anuncios globales y sus borradores. |
| `course` | `course`, `announcements`, `modules` con sus `topics`, `assignments`, `events` y `can_manage`. Incluye únicamente las entregas y notas publicadas del alumno autenticado. El personal autorizado también consulta borradores de contenido. |
| `gradebook` | `assignments`, una página de `students` con sus `grades`, y `has_more`. Solo personal autorizado. |
| `participants` | Una página de `items` con `enrollment_id` y `name`, y `has_more`. Solo personal autorizado. |

Cada curso devuelve su ID, código, nombre, periodo, programa y nota final
publicada propia cuando corresponde. Las fechas son ISO/timestamptz y la UI
las presenta en la zona horaria del dispositivo.

Las notas por actividad separan `score` y `feedback` (borrador) de
`published_score`, `published_feedback` y `published_at` (instantánea publicada).
La revisión inicial de una nota inexistente es `0`. El alumno no recibe los
campos de borrador, ni datos de notas de otros alumnos.

## Escrituras

`portal_learning_write(p_action text, p_course uuid, p_data jsonb) → {id, saved: true, revision}`

| Acción | Campos principales de `p_data` |
| --- | --- |
| `syllabus_save` | `body` |
| `announcement_save` | `id?`, `title`, `body`, `pinned`, `published`, `revision` al editar |
| `module_save` | `id?`, `title`, `position`, `published`, `revision` al editar |
| `topic_save` | `id?`, `module_id`, `title`, `body`, `url`, `position`, `published`, `revision` al editar |
| `assignment_save` | `id?`, `title`, `instructions`, `due_at`, `allow_late`, `published`, `revision` al editar |
| `event_save` | `id?`, `title`, `body`, `starts_at`, `ends_at`, `revision` al editar |
| `grade_save` | `assignment_id`, `enrollment_id`, `score`, `feedback`, `revision` |
| `grade_publish` / `grade_unpublish` | `assignment_id`, `enrollment_id`, `revision` |
| `topic_complete` | `topic_id`, `completed` |
| `submit` | `assignment_id`, `body`, `url` |

Solo el alumno inscrito utiliza `topic_complete` y `submit`. Solo Control
Escolar crea anuncios o eventos institucionales con `p_course=null`. Las otras
acciones de gestión requieren un profesor asignado o Control Escolar.

La publicación copia el borrador en el servidor. El cliente no puede aportar
los valores `published_*`. Una reentrega conserva las notas y guarda la versión
anterior del trabajo en `learning_submission_history`. La calificación final
del sistema anterior permanece independiente.

## Archivos de las entregas

`portal_learning_files(p_action text, p_course uuid, p_assignment uuid, p_data jsonb = '{}') → jsonb`

- `list`: devuelve `items`, `can_upload` y `can_remove`. El personal indica
  `enrollment_id`; el alumno utiliza únicamente su propia inscripción.
- `attach`: recibe `object_path` y `name`. Comprueba el objeto real de Storage,
  su propietario, ruta, tamaño y MIME antes de registrar el archivo y la entrega
  en una sola transacción.
- `remove`: recibe el ID del adjunto. Conserva una entrega no vacía y autoriza
  después la limpieza del objeto retirado.

El bucket privado `portal-coursework` utiliza rutas con la forma
`curso/tarea/alumno/UUID/nombre-seguro.ext`. La descarga se hace mediante
`storage.download()` con la sesión autenticada; no se publican URLs permanentes.
Los límites son tres archivos por alumno/tarea y 5 MB por archivo. La cuota
incluye los objetos huérfanos para evitar cargas sin registro ilimitadas.

## Autorización y concurrencia

Los helpers privados `_learning_require_actor()` y
`_learning_require_course(course, manage)` vuelven a comprobar el perfil, la
clase y el vínculo activo. Comparten bloqueos con la administración para que
una baja no se adelante a una escritura ya autorizada. Las RPC tienen
`search_path` fijo y referencias de esquema completas.

Los códigos principales son `42501` (acceso), `22023` (validación) y `PT409`
(revisión obsoleta). Las revisiones optimistas protegen notas, anuncios,
unidades, temas, tareas y eventos. El libro tabular guarda por celda y muestra
los cambios confirmados si una operación posterior falla; no afirma atomicidad
de toda la tabla. Los cambios de identidad y visibilidad borran el DOM privado,
abortan lecturas y descartan respuestas antiguas.

Las consultas se acotan y el libro/listado de participantes utilizan paginación.
Los límites por curso son 50 unidades, 250 temas, 100 tareas y 200 elementos por
tipo de anuncio/evento. Los widgets muestran feeds limitados y el detalle de
cada curso proporciona el contexto académico correspondiente.

## Módulos del navegador

- `PortalLearning.show(profile, onUnauthorized)`, `clear()`, `navigate()` y
  `openByCard({code, period})` gestionan curso y widgets.
- `PortalLearningFiles.render(container, {courseId, assignmentId, canManage, enrollmentId?})`
  y `clear()` gestionan adjuntos.
- `PortalWorkspace` organiza la navegación global y delega rutas
  `#curso/UUID/seccion` al aula. Los enlaces de pendientes pueden incluir el
  ID de la tarea como segmento adicional.

Los componentes usan texto seguro y enlaces http/https validados. Solo el
personal recibe el libro grupal editable; el alumno utiliza **Mis calificaciones**.
