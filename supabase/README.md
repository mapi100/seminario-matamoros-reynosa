# SQL del Portal Escolar

Para agregar Curso Introductorio (2 semestres), Filosofía (6) y Teología (8),
consulta [Etapas formativas](../docs/etapas-formativas.md). La migración
`20261023000000_formation_stages.sql` se aplica una vez después del expediente
personal; vincula etapa y semestre por alumno y periodo académico.

Esta carpeta conserva el esquema y las pruebas de PostgreSQL en Git, junto con
el código del portal. Guardar los archivos en GitHub no los ejecuta en Supabase.

## Esquema inicial

`migrations/20261021000000_create_profiles.sql` contiene la creación de
`public.profiles`, sus restricciones, permisos y política RLS:

- Cada perfil pertenece a un usuario de Supabase Auth.
- Los roles son `student`, `professor` y `control_escolar`.
- Un usuario autenticado solo puede consultar su propio perfil activo.
- El navegador no tiene permisos para insertar, modificar ni borrar perfiles.
- El rol anónimo no tiene permisos sobre esta tabla.

En un **proyecto nuevo**, con Auth disponible y sin una tabla `profiles`, se
puede ejecutar el archivo completo desde SQL Editor como administrador.

En el **proyecto actual**, este esquema ya se creó manualmente. Este archivo
documenta lo aplicado: se guarda en Git y no se vuelve a ejecutar allí. El
historial de migraciones de Supabase CLI todavía no está configurado. Antes de
automatizar despliegues hay que contrastar el esquema real con este archivo y
establecer su punto de partida; esta carpeta por sí sola no registra una
migración como aplicada en Supabase.

## Comprobación de RLS y permisos

1. Confirma que la cuenta de prueba tiene un perfil con `active = true`.
2. Copia su UID desde Authentication → Users.
3. Copia el contenido de `tests/profiles_rls.sql` en una consulta nueva de SQL Editor.
4. En esa consulta, sustituye `PEGA_AQUI_EL_UID` por el UID y ejecuta el bloque
   completo como administrador. El archivo versionado conserva su marcador.

El script cambia temporalmente al rol `authenticated`, verifica el perfil
propio, los permisos de tabla y columna, y la ausencia de acceso a ese perfil
desde un UID simulado distinto. Se ejecuta en una transacción de solo lectura y
termina con `rollback`, restaurando el contexto de la conexión.

El resultado esperado es `RLS y permisos: OK`. Ante un error, ejecuta `rollback;`
antes de continuar y revisa el mensaje. No cambies permisos solo para conseguir
que la prueba pase.

La ejecución documentada es manual con SQL Editor. El archivo no usa pgTAP y
todavía no está preparado para el comando `supabase test db`.

Es una comprobación inicial de `profiles`: la identidad simulada no es una
segunda cuenta real y este script no comprueba directamente el filtrado de
perfiles inactivos. La prueba manual del portal incluye desactivar y reactivar
la cuenta de prueba. Las tablas y funciones futuras necesitarán sus propias
políticas y comprobaciones.

Los archivos usan un marcador genérico: introduce los UID de tus pruebas solo
en SQL Editor. Las contraseñas y claves privadas nunca pertenecen a esta carpeta.

## Aplicar «Mis materias» en el proyecto actual

La migración de perfiles anterior **ya está aplicada: no la repitas**. Esta
actualización añade tres tablas:

- `subjects`: código y nombre de la materia.
- `academic_periods`: nombre del periodo y sus fechas.
- `enrollments`: relación alumno–materia–periodo. Una combinación no se puede
  duplicar, y las claves foráneas impiden referencias inexistentes.

En Supabase → **SQL Editor → New query**, como administrador:

1. Ejecuta completo `migrations/20261021010000_create_academics.sql` **una vez**.
   Crea las tablas, sus restricciones, índices y políticas RLS. Ante un error,
   ejecuta `rollback;` y revisa el mensaje antes de continuar.
2. Para probar, copia `seeds/demo_enrollments.sql` en otra consulta. Sustituye
   `PEGA_AQUI_EL_UID` por el UID de **tu alumno de prueba activo** desde
   Authentication → Users. Ejecuta todo el archivo.
3. Ejecuta `tests/academics_rls.sql` en una nueva consulta, sustituyendo el
   marcador por el mismo UID. Debe mostrar **`Materias: RLS y permisos OK`**.
4. En el portal, inicia sesión con esa cuenta. «Mis materias» debe mostrar
   `DEMO-FIL-101` y `DEMO-HIS-101`, dentro de «DEMO 2026 — semestre de prueba».

El seed añade **datos ficticios**, no materias oficiales. Se puede repetir para
la misma cuenta sin duplicar inscripciones; si un código DEMO o el periodo ya
existe con contenido distinto, aborta la transacción sin sobrescribirlo. No crea
usuarios ni perfiles, y rechaza UID sin perfil, inactivos o con otro rol.
Introduce el UID solo en SQL Editor; conserva el marcador en GitHub.

Guardar o subir estos archivos a GitHub **no ejecuta** el SQL en Supabase. Para
un proyecto completamente nuevo, aplica primero la migración de perfiles y
luego la académica. El historial automático de Supabase CLI sigue pendiente.

### Permisos del módulo

Las tres tablas tienen RLS activado y solo permiten SELECT a `authenticated`.
El navegador no puede insertar, actualizar ni borrar, tampoco con el rol de
perfil `control_escolar`; por ahora las altas se hacen desde administración.

Una inscripción solo es visible si pertenece al usuario autenticado y su
perfil sigue activo con rol `student`. Los catálogos solo muestran materias y
periodos relacionados con sus inscripciones visibles. La migración académica
inicial no permite leer estos datos a profesores, Control Escolar, perfiles
inactivos o cuentas sin perfil, aunque tengan una inscripción asignada por error.
La ampliación de profesor descrita más abajo añade lectura de catálogos asignados
y un listado limitado mediante función; mantiene cerrada la lectura directa de
inscripciones. El rol de perfil no sustituye el rol PostgreSQL `authenticated`.

La migración académica inicial no incluye grupos, profesores asignados ni notas.
Las ampliaciones de calificaciones y profesor se describen más abajo; cada una
añade sus propias reglas. La edición de inscripciones sigue pendiente.

### Pruebas reproducibles de SQL y aislamiento

El smoke de SQL Editor comprueba permisos, RLS habilitado, ausencia de
inscripciones ajenas, catálogos relacionados y una identidad ficticia sin perfil.
Requiere al menos una inscripción del alumno; con un único alumno real no
sustituye una prueba entre dos cuentas de Supabase Auth.

El runner `tests/run_academics_local.py` conserva fixtures de **dos alumnos**,
catálogos compartidos y exclusivos, perfil inactivo y otros roles. Usa Python 3
y Docker; desde la raíz del repositorio:

```bash
docker pull postgres:17-bookworm
python3 supabase/tests/run_academics_local.py
```

El runner crea exclusivamente su propio contenedor temporal sin red ni puertos
publicados, aplica las migraciones y destruye el contenedor al terminar. No
acepta conexiones externas ni usa credenciales del proyecto. Comprueba
consultas y joins, aislamiento entre alumnos, desactivación y cambio de rol,
permisos de anónimo, escritura denegada, restricciones, seed repetible y que el
smoke detecte fallos introducidos intencionalmente en políticas/permisos.

`auth.users` y `auth.uid()` son fixtures locales mínimos: estas pruebas validan
PostgreSQL y RLS, no el servidor real de Supabase Auth ni PostgREST. La prueba
manual del portal con cuentas diferentes sigue siendo necesaria para comprobar
la integración real. Ninguno de los archivos de prueba es pgTAP.

## Aplicar calificaciones publicadas de 0 a 100

Esta actualización añade `enrollment_grades`: una nota por inscripción, de
**0 a 100**, con hasta dos decimales. No calcula promedios ni determina si el
alumno aprobó. `published` vale `false` de forma predeterminada; los alumnos solo
pueden consultar notas publicadas de sus propias inscripciones mientras su
perfil siga activo.

En el proyecto actual, perfiles, materias, periodos e inscripciones **ya están
creados**. No repitas esas migraciones. En **SQL Editor → New query**, como
administrador:

1. Ejecuta completo `migrations/20261021020000_create_enrollment_grades.sql`
   **una sola vez**. Ante un error, ejecuta `rollback;` y revisa el mensaje.
2. Copia `seeds/demo_grades.sql` en otra consulta. Sustituye `PEGA_AQUI_EL_UID`
   por el UID de tu alumno de prueba activo y ejecuta todo el contenido.
   Requiere las dos inscripciones DEMO ya cargadas en el paso anterior.
3. Ejecuta `tests/grades_rls.sql` en otra consulta, con el mismo UID. Debe mostrar
   **`Calificaciones: RLS y permisos OK`**.
4. Publica el frontend actualizado. Filosofía debe mostrar **85.50 / 100**;
   Historia debe mostrar **Sin calificación publicada**. Historia tiene una nota
   ficticia sin publicar; esa nota y su existencia no se devuelven al alumno.

El seed usa únicamente datos ficticios: Filosofía 85.50 publicada e Historia
72.00 sin publicar. Se puede repetir sin duplicar filas. Si una nota DEMO o su
publicación ya fueron modificadas, aborta toda la transacción sin sobrescribir
los cambios. No crea cuentas, perfiles ni inscripciones. Conserva los marcadores
genéricos en GitHub e introduce el UID solo en SQL Editor.

### Permisos y conservación de notas

La tabla tiene RLS y SELECT para `authenticated`, sin permisos de escritura del
navegador para ningún rol de perfil. La política comprueba expresamente que la
nota esté publicada, la inscripción pertenezca a `auth.uid()` y el perfil sea
un alumno activo; no depende solo de ocultar botones ni de un filtro del cliente.
Los borradores y las notas ajenas tampoco se pueden consultar directamente por
su ID. Esta migración inicial no añade captura desde el portal; la ampliación
de captura del profesor se aplica con la quinta migración, descrita más abajo.
Control Escolar todavía no tiene un flujo de captura en el portal.

La clave foránea usa `ON DELETE RESTRICT`. Mientras una inscripción tenga nota,
PostgreSQL impide eliminarla y también impide borrados en cascada de su perfil o
cuenta. Es una protección contra eliminación accidental de datos académicos;
una baja académica no debe resolverse borrando su historial. La estrategia de
copias de seguridad y conservación oficial se definirá antes de usar notas reales.

La consulta de notas es independiente de la de materias. Si faltara la tabla o
fallara la consulta, el frontend conserva las materias y muestra un error de
calificaciones; no presenta un fallo como ausencia de nota. Una nota ausente y
una nota no publicada muestran el mismo texto genérico al alumno.

### Pruebas locales de calificaciones

Con Docker, Python 3 e imagen `postgres:17-bookworm`, desde la raíz:

```bash
python3 supabase/tests/run_grades_local.py
```

El runner crea y elimina su propio contenedor sin red ni puertos publicados,
aplica las tres migraciones y usa fixtures mínimos de Auth. Comprueba dos alumnos
con la misma materia y periodo, notas publicadas y borradores, ausencia de nota,
0 y 100, inactividad y otros roles, consultas directas y filtros, escritura
denegada, valores inválidos, seed repetible y conflictos, protección frente a
borrados y detección de permisos/políticas deliberadamente incorrectos. También
comprueba que ampliar una política de inscripciones o perfiles no amplíe por sí
solo el acceso a calificaciones. No usa un DSN ni credenciales del proyecto.

`grades_rls.sql` es una comprobación manual de solo lectura que requiere al menos
una nota publicada; no crea una segunda cuenta real ni sustituye la prueba de
integración con Supabase Auth y PostgREST. El runner local prueba PostgreSQL/RLS,
no esos servicios. Los archivos no usan pgTAP ni historial automático de CLI.

## Profesor: materias asignadas y listado de alumnos

Esta actualización añade `teaching_assignments`: vincula un profesor, una materia
y un periodo. Un mismo profesor no puede tener la misma combinación duplicada;
dos profesores pueden compartirla. Por ahora no se crean grupos separados: el
listado incluye a todos los alumnos activos inscritos en esa materia y periodo.
La captura se instala con la ampliación descrita más abajo. Las tareas siguen
pendientes.

En el proyecto actual las tres migraciones anteriores ya están aplicadas.
No las repitas. Desde **SQL Editor → New query**, como administrador:

1. Ejecuta completo `migrations/20261021030000_create_teaching_assignments.sql`
   **una sola vez**. Si ocurre un error, ejecuta `rollback;` y revisa el mensaje.
2. Crea una cuenta de prueba **nueva y distinta** de la cuenta del alumno en
   **Authentication → Users → Add user → Create new user**. Usa un correo que
   controles y una contraseña de prueba que mantengas privada. Para esta cuenta
   de pruebas puedes marcar la confirmación automática del correo si esa opción
   aparece en el formulario; no habilites el registro público. Copia el UID nuevo.
3. En otra consulta nueva pega `seeds/demo_professor_profile.sql`, sustituye
   `PROFESSOR_UID_AQUI` por ese UID y ejecuta todo el contenido. Crea el perfil
   **Profesor de prueba**. Si la cuenta ya pertenece a un alumno o está inactiva,
   el script la rechaza sin convertir ni reactivar el perfil.
4. Copia `seeds/demo_teaching.sql` en otra consulta nueva. Sustituye
   `STUDENT_UID_AQUI` por el UID de tu alumno actual y `PROFESSOR_UID_AQUI` por el
   UID nuevo del profesor. Asigna las dos materias DEMO existentes. No crea
   inscripciones, usuarios ni cambia roles; se puede repetir sin duplicados.
5. Ejecuta `tests/professor_rls.sql` en otra consulta, sustituyendo solamente
   `PROFESSOR_UID_AQUI` por el UID del profesor. Debe mostrar
   **`Profesor: RLS y permisos OK`**.
6. Publica el frontend actualizado, cierra la sesión del alumno y entra con la
   cuenta del profesor. Debe ver sus materias asignadas y, al abrir cada lista,
   los nombres de sus alumnos activos. Usa otra sesión para comprobar que el
   alumno conserva su acceso a materias y calificaciones propias.

Conserva los marcadores genéricos en los archivos de GitHub; sustituye los UID
solo en SQL Editor. No compartas ni guardes contraseñas en código. Subir estos
archivos a GitHub no ejecuta el SQL ni crea cuentas en Supabase.

### Permisos y función del listado

`teaching_assignments` tiene RLS y solo SELECT para `authenticated`. Una fila es
visible únicamente al profesor asignado, con perfil activo y rol `professor`.
Las políticas nuevas de `subjects` y `academic_periods` permiten leer solamente
los catálogos de sus asignaciones visibles, sin ciclos entre políticas.

No se amplían los permisos de lectura de `profiles`, `enrollments` ni
`enrollment_grades`: el profesor sigue sin poder consultar directamente perfiles
de alumnos, sus inscripciones ni sus notas. El frontend llama a
`get_teaching_roster(p_assignment_id, p_offset, p_limit)`, una función de consulta
que devuelve **solo `enrollment_id` y `student_name`**. No devuelve correo,
dirección, teléfono, contactos, UID del perfil ni calificaciones.

La función comprueba en cada llamada que la asignación pertenece al profesor y
que su perfil permanece activo con el rol correcto. Un ID ajeno, inexistente o
una cuenta no autorizada recibe el mismo error de permiso. El listado filtra
alumnos activos con rol `student`, por materia y periodo, y ordena por nombre e
ID de inscripción. Acepta desplazamientos de 0 a 100000 y límites de 1 a 100;
rechaza valores nulos o fuera de rango. El frontend solicita páginas pequeñas.

Es una función `STABLE SECURITY DEFINER`, propiedad del administrador de
confianza que aplica la migración, con `search_path` vacío y tablas nombradas
con su esquema. La autorización explícita es necesaria porque la función lee
las filas usando ese propietario. Se revoca la ejecución predeterminada de
`PUBLIC` y de `anon`; solo `authenticated` puede llamarla y sus comprobaciones
internas deciden quién está autorizado. No realiza escrituras ni contiene SQL
dinámico. Ningún perfil del navegador recibe permisos de edición.

### Pruebas locales del profesor

Con los mismos requisitos de Docker, Python 3 e imagen PostgreSQL:

```bash
python3 supabase/tests/run_professor_local.py
```

El runner crea exclusivamente su propio contenedor temporal sin red ni puertos,
aplica las cuatro migraciones y lo elimina al terminar. Incluye dos profesores,
al menos tres alumnos, materias compartidas y exclusivas, periodos diferentes,
co-docencia, perfiles inactivos y otros roles. Comprueba la privacidad de perfiles
y notas, autorizaciones de la función, paginación, permisos de ejecución,
escritura denegada, seeds repetibles y que el smoke detecte políticas o permisos
incorrectos. También vuelve a ejecutar los smokes anteriores de perfiles,
materias y notas para dos alumnos después de aplicar las políticas nuevas.

El smoke de SQL Editor es una comprobación de solo lectura para un profesor con
asignaciones. Comprueba las reglas expuestas y que la función rechace una
identidad sin perfil; no crea una segunda cuenta real ni demuestra por sí solo
el aislamiento completo del listado. El runner usa fixtures mínimos de Auth y
prueba SQL/PostgreSQL; la prueba manual con cuentas reales comprueba la
integración con Supabase Auth y PostgREST.

## Capturar y publicar calificaciones desde el profesor

Esta ampliación añade el editor de notas de **0 a 100**, con hasta dos decimales,
para alumnos activos inscritos en materias y periodos asignados al profesor.
Se aplica sobre las cuatro migraciones anteriores, que ya están instaladas en
el proyecto actual. No las repitas y no necesitas crear otras cuentas o datos DEMO.

Desde **SQL Editor → New query**, como administrador de confianza:

1. Ejecuta completo `migrations/20261021040000_enable_grade_capture.sql` una sola
   vez. Si falla, ejecuta `rollback;` y revisa el mensaje antes de continuar.
2. En otra consulta, pega `tests/grade_capture_rls.sql`. Sustituye
   `PROFESSOR_UID_AQUI` por el UID del profesor existente, conservando las comillas.
   El archivo versionado conserva su marcador. Debe mostrar
   **`Captura: RLS y permisos OK`**. Esta comprobación es de solo lectura.
3. Publica el frontend actualizado y entra como profesor. Abre **Ver alumnos**,
   pulsa **Calificar** junto al alumno, introduce una nota y elige **Guardar
   borrador**. La publicación requiere la acción separada **Publicar**.
4. Comprueba desde otra sesión de alumno: guardar un borrador mantiene la nota
   publicada anterior, si existe. Solo publicar cambia la nota que ve el alumno.

Una nota previa sin publicar, como el DEMO de Historia, se utiliza como valor
inicial del editor. Primero debe guardarse como borrador en el portal antes de
habilitar su publicación. Una nota de cero es válida. No se calculan promedios,
aprobación ni notas oficiales finales.

### Borradores, autorización y revisión de cambios

`enrollment_grade_drafts` conserva el borrador separado de `enrollment_grades`,
que sigue siendo la fuente de notas publicadas para el alumno. El navegador no
recibe permisos directos sobre borradores, auditoría ni escritura de notas.
Las políticas anteriores de perfiles, inscripciones y notas no se amplían.

El acceso se realiza mediante tres funciones con propietario administrativo de
confianza, `SECURITY DEFINER`, `search_path` vacío y tablas nombradas por esquema:

- `get_teaching_grade`: comprueba asignación, profesor activo y alumno activo;
  devuelve la nota publicada, el borrador, su revisión y si está pendiente de
  publicación. No realiza escrituras.
- `save_teaching_grade`: vuelve a autorizar, valida escala y decimales y guarda
  el borrador sin modificar la nota publicada.
- `publish_teaching_grade`: vuelve a autorizar y publica únicamente un borrador
  previamente guardado, en la revisión esperada.

Se revoca la ejecución de `PUBLIC` y `anon`, y solo `authenticated` puede llamar
a estas funciones; las comprobaciones internas deciden si ese usuario puede
operar sobre la inscripción concreta. El helper de bloqueo es privado y no se
puede ejecutar directamente desde el navegador.

Cada escritura bloquea la inscripción y mantiene bloqueos compartidos sobre la
asignación y los perfiles autorizados hasta terminar la transacción. Así dos
profesores que comparten una materia no sobrescriben silenciosamente el trabajo
del otro. El cliente debe enviar `p_expected_revision`: una revisión distinta
produce **`PT409`**, que PostgREST presenta como HTTP 409. Hay que volver a cargar
la nota antes de intentar otra modificación. Guardar y publicar incrementan la
revisión, y publicar consume el borrador pendiente.

`enrollment_grade_events` registra cada guardado o publicación completados: actor,
inscripción, identificador de asignación, acción, valores anteriores y nuevo,
revisión y fecha. Se escribe en la misma transacción; si falla la auditoría,
también se revierte el cambio de nota. El identificador de asignación es una
instantánea sin clave foránea: el historial no impide revocar la asignación.
El navegador no puede leer, insertar, modificar ni borrar este historial.

La revisión y el historial cubren operaciones realizadas por estas funciones;
las escrituras manuales de un administrador en SQL Editor no pasan por ellas.
Para las pruebas de captura usa el portal en lugar de cambiar las notas a mano.
No repitas los seeds de notas después de editarlas: rechazan los valores DEMO
modificados para evitar sobrescribirlos.

### Pruebas locales de captura

Con Docker, Python 3 e imagen `postgres:17-bookworm`, desde la raíz:

```bash
python3 supabase/tests/run_grade_capture_local.py
```

El runner usa exclusivamente su propio contenedor temporal sin red ni puertos,
aplica las cinco migraciones y lo elimina al terminar. Incluye dos profesores
que comparten materia, alumnos ajenos y de otros periodos, perfiles inactivos y
otros roles. Comprueba autorización en lectura y escritura, rango y decimales,
cero y cien, borradores invisibles al alumno, publicación, auditoría atómica,
revisiones y escrituras concurrentes, bloqueos frente a revocación y conservación
de los smokes anteriores después de la migración nueva.

`grade_capture_rls.sql` es una comprobación manual de solo lectura de configuración,
permisos y lectura autorizada; no guarda ni publica notas. Las pruebas locales
usan fixtures mínimos de Auth y PostgreSQL. La prueba manual con cuentas reales
es la que comprueba Supabase Auth y PostgREST integrados. Ninguna prueba conecta
al proyecto real ni requiere credenciales del proyecto.

## Control Escolar: crear periodos y materias

Esta ampliación permite a una cuenta activa con rol `control_escolar` consultar
todos los periodos y materias y crear registros nuevos desde el portal. No
añade edición, eliminación, gestión de cuentas, asignaciones ni inscripciones.
Los accesos de alumno y profesor conservan sus reglas anteriores.

En el proyecto actual las cinco migraciones previas ya están aplicadas.
Desde **SQL Editor → New query**, como administrador de confianza:

1. Ejecuta completo `migrations/20261021050000_control_catalogs.sql` **una vez**.
   Si ocurre un error, ejecuta `rollback;` y revisa el mensaje antes de continuar.
   No repitas las migraciones anteriores.
2. En **Authentication → Users → Add user**, crea y confirma una cuenta de prueba
   distinta de alumno y profesor. Mantén la contraseña privada. Copia el UID.
3. Pega `seeds/demo_control_profile.sql` en otra consulta nueva. Sustituye
   `CONTROL_UID_AQUI` por ese UID y ejecuta todo el archivo. Crea el perfil
   **Control Escolar de prueba**; rechaza una cuenta con otro rol o inactiva, sin
   convertir ni reactivar perfiles existentes.
4. Pega `tests/control_catalogs_rls.sql` en otra consulta nueva, sustituye el mismo
   marcador y ejecuta todo. Debe mostrar **`Control Escolar: RLS y permisos OK`**.
   Es una comprobación de solo lectura: no crea periodos ni materias.
5. Publica los archivos del portal e inicia sesión con la cuenta nueva. Comprueba
   las listas y crea un periodo y una materia de prueba desde los formularios.

Conserva los marcadores en GitHub y sustitúyelos solo en SQL Editor. Subir archivos
a GitHub no ejecuta el SQL ni crea la cuenta de Supabase Auth.

### Funciones de creación y permisos

Los RPC `create_subject(p_code, p_name)` y
`create_academic_period(p_name, p_starts_on, p_ends_on)` autorizan mediante
`auth.uid()` y el perfil activo de Control Escolar. Mantienen un bloqueo `FOR
SHARE` del perfil durante la transacción, para que un cambio de rol o actividad
no se interponga entre la autorización y el guardado. Son funciones
`VOLATILE SECURITY DEFINER`, con propietario administrativo confiable,
`search_path` vacío y objetos nombrados con su esquema. La ejecución predeterminada
de `PUBLIC` y `anon` está revocada; sus comprobaciones internas deciden qué usuario
autenticado puede crear. El helper de autorización no es ejecutable desde el
navegador.

No se conceden permisos directos INSERT, UPDATE o DELETE sobre los catálogos.
Solo se añade SELECT de catálogos al perfil activo de Control Escolar. No se
amplía el acceso a perfiles ajenos, notas, inscripciones ni asignaciones docentes.

Los códigos se recortan y convierten a mayúsculas, con longitud de 1 a 40
caracteres; los nombres de materia aceptan 1 a 160 caracteres y los de periodo
1 a 120. Se recortan espacios exteriores y se rechazan caracteres de control.
Las cadenas compuestas únicamente por espacios Unicode, como NBSP o EM SPACE,
también se rechazan para coincidir con la validación del navegador.
No se impone un formato institucional de código todavía. Las fechas son
obligatorias, finitas y de los años 0001 a 9999; la final no puede preceder a la
inicial. Estos límites mantienen el formato ISO de fecha del portal.

Los índices únicos normalizados rechazan códigos y nombres de periodo repetidos
por cambios de mayúsculas o espacios exteriores. Un duplicado devuelve un
conflicto `PT409` sin sobrescribir el registro. La migración no cambia ni borra
datos existentes; si ya hay duplicados normalizados, falla y revierte por
completo para revisarlos antes de aplicarla.

Cada creación mediante estos RPC registra actor, acción, ID y datos creados en
`catalog_events`, dentro de la misma transacción. La auditoría tiene RLS y no
permite lectura o escritura directa desde el navegador. Un fallo de auditoría
revierte también la creación. Los cambios manuales de un administrador SQL no
pasan automáticamente por este registro.

Ante un fallo de conexión después de crear, el cliente no debe reenviar la
operación automáticamente: puede haberse completado. Debe actualizar la lista y
revisarla antes de intentar otra creación. La unicidad normalizada impide
duplicar el mismo código o nombre incluso con solicitudes concurrentes.

### Pruebas locales de Control Escolar

Con Docker, Python 3 e imagen `postgres:17-bookworm`, desde la raíz:

```bash
python3 supabase/tests/run_control_catalogs_local.py
```

El runner aplica las seis migraciones en su propio contenedor temporal sin red
ni puertos publicados, y lo elimina al terminar. Incluye dos cuentas de Control
Escolar, alumnos, profesor, inactivos y cuenta sin perfil. Comprueba permisos,
normalización, validaciones, duplicados concurrentes, auditoría atómica,
bloqueo de cambios de rol, creación segura del perfil y regresiones de las pruebas
anteriores de alumno y profesor. También comprueba que duplicados históricos
aborten la migración sin eliminar datos ni dejar objetos parciales.

El smoke manual comprueba configuración, permisos y aislamiento de lectura;
no ejecuta los RPC de creación porque la transacción es de solo lectura. Las
escrituras y concurrencia se prueban en el contenedor local. Auth es un fixture
mínimo: la prueba con la cuenta real en el portal comprueba Supabase Auth y
PostgREST integrados. Ninguna de estas pruebas requiere credenciales del
proyecto ni escribe en Supabase real.
