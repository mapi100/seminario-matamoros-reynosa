# SQL del Portal Escolar

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
periodos relacionados con sus inscripciones visibles. Un profesor, Control
Escolar, un perfil inactivo o una cuenta sin perfil no pueden leer estos datos,
aunque administración les haya asignado una inscripción por error. El rol de
perfil no sustituye el rol PostgreSQL `authenticated`.

Esta etapa no incluye grupos, profesores asignados, calificaciones ni edición
de inscripciones. Cada ampliación necesitará sus propias reglas de autorización.

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
