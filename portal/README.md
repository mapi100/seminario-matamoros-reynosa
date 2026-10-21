# Portal Escolar: autenticación

El portal usa HTML, CSS y JavaScript sin compilación. Conserva el servidor estático
del repositorio y configura `supabase-config.js` con la URL del proyecto y su
**publishable key** (`sb_publishable_...`). Ambos datos son públicos. Las claves
secretas, `service_role` y las contraseñas nunca pertenecen a estos archivos.

El SDK de Supabase se carga desde jsDelivr con versión fija y verificación SRI.
Después se cargan `supabase-config.js`, `auth.js` y el controlador de la página.
El panel carga también `subjects.js` antes de su controlador.
Si faltan la configuración o el SDK, el formulario permanece deshabilitado.

## Acceso y panel inicial

`auth.js` comparte la creación del cliente y la verificación de acceso entre
`portal.js` (login) y `panel.js` (panel). Se comprueba la sesión, se verifica la
identidad con `getUser()` y se consulta el perfil propio por su ID mediante RLS.

El login redirige a `panel.html` después de una verificación correcta. El panel
vuelve a verificar el acceso, incluso cuando se abre directamente, se restaura
desde la caché de navegación o se regresa a la pestaña. El nombre y el rol se
mantienen ocultos mientras se verifica la sesión y se limpian al abandonar la
página. Un error de conexión muestra una opción para reintentar.

Una sola página presenta el inicio correspondiente a `student`, `professor` o
`control_escolar`. El rol procede de `profiles`, no de la URL ni de los metadatos
editables del usuario. Los alumnos pueden consultar sus materias; todos los
roles pueden consultar el perfil y cerrar sesión. El título del panel no otorga
permisos administrativos.

El HTML estático es público. Las comprobaciones de JavaScript controlan la
navegación y la presentación; la protección de los datos sigue dependiendo de
Supabase Auth y PostgreSQL/RLS. Las funciones académicas futuras necesitarán
autorización en sus propias tablas y operaciones.

## Mis materias

`subjects.js` consulta `enrollments` con las relaciones `subjects` y
`academic_periods`. Las tres tablas aplican RLS: solo un alumno activo puede leer
sus propias inscripciones y los catálogos relacionados. Los profesores y Control
Escolar todavía no tienen una vista académica ni permisos sobre estas tablas.

Cada tarjeta muestra código, nombre de la materia, periodo y fechas. Se consultan
20 inscripciones por página y una fila adicional para decidir si aparece **Ver
más**; la fila adicional se presenta al solicitar la página siguiente. El orden
por fecha de inscripción e ID evita empates indeterminados. Todas las consultas
son de lectura y los nombres se presentan como texto.

La sección distingue carga, lista vacía y error. **Reintentar** vuelve a comprobar
la identidad y el perfil antes de consultar de nuevo. Un error al cargar más
conserva las tarjetas ya mostradas; reintentar comienza desde la primera página.
Al cerrar sesión, ocultar la pestaña o abandonar el panel, se borran las tarjetas,
se cancela la solicitud pendiente y se descartan respuestas anteriores.

Primero aplica la nueva migración y carga los datos DEMO desde administración
según [las instrucciones SQL](../supabase/README.md). Guardar el frontend en GitHub
no crea tablas ni inscripciones. Si la consulta falla, se muestra un error; una
respuesta correcta sin inscripciones muestra la lista vacía.

## Calificaciones publicadas

Cada tarjeta de materia muestra su calificación publicada en escala de **0 a
100**, con hasta dos decimales. Un cero es una nota válida. Si la nota no existe
o sigue en borrador, ambos casos muestran **Sin calificación publicada**. Esta
etapa no calcula promedios, aprobación, reprobación ni calificaciones finales.

`subjects.js` consulta `enrollment_grades` por separado, únicamente para los IDs
de las inscripciones mostradas en la página actual. RLS exige nota publicada,
inscripción propia y perfil activo con rol `student`. El navegador no tiene
permisos para registrar, editar ni publicar notas, tampoco con un perfil de
Control Escolar. Por ahora esas operaciones se realizan desde SQL Editor.

Si falla la consulta de notas, las materias permanecen visibles y cada tarjeta
afectada muestra **No fue posible consultar la calificación**. **Reintentar**
comprueba de nuevo el acceso y recarga desde la primera página. Las notas se
limpian y sus solicitudes se cancelan junto con las materias al salir u ocultar
la pestaña. Las respuestas fuera de rango o con IDs inesperados se rechazan.

La migración y los datos de ejemplo se aplican manualmente siguiendo
[Instalar calificaciones](../docs/calificaciones.md). Publicar en GitHub no
modifica las notas en Supabase. Un administrador de SQL Editor puede ver los
borradores; la comprobación desde la sesión de alumno o con el smoke RLS es la
que verifica su ocultación.

## Requisitos del proyecto Supabase

- Registro público y acceso anónimo desactivados; acceso por email habilitado.
- Site URL y Redirect URLs configurados para la dirección real del portal.
- `public.profiles` con `id`, `full_name`, `role`, `active` y `created_at`.
- `id` referencia `auth.users(id)` y los roles permitidos son `student`,
  `professor` y `control_escolar`.
- RLS activado: `authenticated` solo tiene SELECT de su propia fila activa.
- Sin permisos INSERT, UPDATE ni DELETE para el navegador, ni acceso de `anon`.
- Un usuario creado desde administración, con un perfil asignado por administración.

Los roles se consultan en `profiles`; los metadatos editables del usuario no
deciden permisos. El navegador muestra el resultado, pero PostgreSQL/RLS debe
autorizar todos los datos. Las tablas futuras también deberán comprobar la
actividad y los permisos del usuario.

## Comprobación manual con la cuenta de prueba

1. Abre `portal/index.html` mediante el servidor HTTP o GitHub Pages.
2. Inicia sesión. Debe abrirse `panel.html` con el título del rol, nombre,
   estado Activo y Cerrar sesión.
3. Recarga: la identidad se vuelve a verificar con Auth y se consulta el perfil.
4. Cierra sesión: debe volver a `index.html` con el formulario y una confirmación.
   Recarga o abre `panel.html` directamente: debes permanecer fuera del panel.
5. Una contraseña incorrecta debe mostrar un error sin revelar detalles de la cuenta.
6. Desactiva temporalmente **solo la cuenta de prueba** poniendo `active = false`
   desde administración. Al intentar entrar, no debe aparecer el perfil y se
   debe cerrar la sesión. Restaura `active = true` al terminar.
7. Con las tablas nuevas y los datos DEMO, el alumno debe ver Filosofía e Historia
   en **Mis materias**. Recarga y vuelve a la pestaña: se vuelven a consultar.
8. Cierra sesión: las materias desaparecen junto con el perfil. Una segunda cuenta
   de alumno debe ver únicamente las inscripciones que administración le asigne.
9. Tras aplicar la migración y el seed de notas, Filosofía debe mostrar
   **Calificación publicada: 85.5 / 100** e Historia **Sin calificación publicada**.
   El valor del borrador de Historia no debe aparecer en la sesión de alumno.

El SQL Editor normalmente utiliza un rol privilegiado: ver filas allí no prueba
RLS. Comprueba el aislamiento entre usuarios con sesiones autenticadas diferentes
o pruebas SQL que cambien expresamente al rol `authenticated`.

`active = false` restringe la autorización; no impide por sí mismo que Auth emita
un token. Ante un perfil ausente o no autorizado, este frontend solicita el cierre
de la sesión local. El SDK puede eliminar esa sesión del navegador aunque falle
la revocación remota. Durante el cierre se oculta el perfil; si un error impide
cerrar la sesión local, se ofrece reintentar. El cierre afecta a este dispositivo.

Esta etapa permite consultar las materias inscritas; las altas se realizan desde
administración en SQL Editor. La recuperación de contraseña por correo todavía
no está implementada; el botón
indica contactar a Control Escolar. La detección de sesiones en enlaces está
desactivada hasta implementar ese flujo.

## Pruebas locales de navegador

`tests/portal_subjects.py` comprueba las materias, el estado vacío, los errores y
reintentos, paginación, roles, móvil y respuestas tardías tras cerrar sesión u
ocultar la pestaña. Usa el SDK real con API simulada: no se conecta al proyecto
Supabase ni verifica sus políticas reales.

Con Python 3 y Playwright en un entorno virtual, desde la raíz del repositorio:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
python3 tests/portal_subjects.py
python3 tests/portal_grades.py
```

Si Chromium ya está instalado, se puede omitir la instalación del navegador.
`CHROMIUM_PATH` permite indicar su ruta. El test descarga el SDK por HTTPS y
verifica su SHA384 contra el SRI de `panel.html`, utiliza un servidor temporal
y lo detiene al terminar. `PORTAL_TEST_ARTIFACTS` permite conservar capturas.
Estas herramientas son para desarrollo; el sitio publicado sigue siendo estático.

`tests/portal_grades.py` comparte el servidor y los fixtures del test de materias.
Comprueba valores publicados, cero y cien, ausencia de publicación, errores,
reintentos, paginación y respuestas tardías. La API simulada comprueba el frontend;
las pruebas de PostgreSQL y la integración real se documentan en `supabase/README.md`.
