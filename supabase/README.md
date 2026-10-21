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
