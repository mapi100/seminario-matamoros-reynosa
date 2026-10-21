# Portal Escolar: autenticación

El portal usa HTML, CSS y JavaScript sin compilación. Conserva el servidor estático
del repositorio y configura `supabase-config.js` con la URL del proyecto y su
**publishable key** (`sb_publishable_...`). Ambos datos son públicos. Las claves
secretas, `service_role` y las contraseñas nunca pertenecen a estos archivos.

El SDK de Supabase se carga desde jsDelivr con versión fija y verificación SRI.
Después se cargan `supabase-config.js`, `auth.js` y el controlador de la página.
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
editables del usuario. Por ahora se puede consultar el perfil y cerrar sesión;
el título del panel no otorga permisos administrativos.

El HTML estático es público. Las comprobaciones de JavaScript controlan la
navegación y la presentación; la protección de los datos sigue dependiendo de
Supabase Auth y PostgreSQL/RLS. Las funciones académicas futuras necesitarán
autorización en sus propias tablas y operaciones.

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

El SQL Editor normalmente utiliza un rol privilegiado: ver filas allí no prueba
RLS. Comprueba el aislamiento entre usuarios con sesiones autenticadas diferentes
o pruebas SQL que cambien expresamente al rol `authenticated`.

`active = false` restringe la autorización; no impide por sí mismo que Auth emita
un token. Ante un perfil ausente o no autorizado, este frontend solicita el cierre
de la sesión local. El SDK puede eliminar esa sesión del navegador aunque falle
la revocación remota. Durante el cierre se oculta el perfil; si un error impide
cerrar la sesión local, se ofrece reintentar. El cierre afecta a este dispositivo.

Esta etapa contiene el inicio por rol y el perfil, sin gestión académica. La
recuperación de contraseña por correo todavía no está implementada; el botón
indica contactar a Control Escolar. La detección de sesiones en enlaces está
desactivada hasta implementar ese flujo.
