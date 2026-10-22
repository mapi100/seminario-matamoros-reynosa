# Correos automáticos del Portal Escolar con Resend

Esta configuración utiliza el plan gratuito de Resend y los correos actuales
de unas 60 personas. Los alumnos y sacerdotes reciben sus invitaciones en
Gmail, Outlook u otra cuenta que ya utilicen, y crean una contraseña del portal.
Los buzones institucionales de Google Workspace quedan pendientes.

El portal tiene implementadas las invitaciones y la recuperación de contraseña.
El envío depende de configurar Resend, SMTP en Supabase y la función
`invite-person` en el proyecto real. Los archivos de este repositorio no
acreditan que esa configuración ya esté aplicada en producción.

## 1. Registrar el remitente en Resend

En Resend → **Domains → Add domain**, introduce:

```text
notificaciones.seminariomr.org
```

Usaremos como remitente:

```text
Portal Escolar del Seminario <portal@notificaciones.seminariomr.org>
```

La dirección identifica los mensajes automáticos; no crea una bandeja personal.
Para pedir ayuda, las personas se comunican con Control Escolar por los
medios que el Seminario ya utiliza.

Resend mostrará los registros DNS de verificación y envío. En Cloudflare →
**seminariomr.org → DNS → Records**, agrega exactamente los tipos, nombres,
valores y prioridades que muestre Resend. Los valores DKIM pertenecen a tu
cuenta y deben copiarse de esa pantalla; no utilices ejemplos como registros.
Los registros de correo no utilizan el proxy de Cloudflare.

Conserva los A del sitio, el CNAME de `www`, el TXT de verificación de Google
y los demás registros existentes. No actives recepción de correo en Resend
para este flujo ni reemplaces los MX de `seminariomr.org`. Si Resend solicita
un MX para su dominio de retorno de envíos, utiliza únicamente el nombre
completo que indique, dentro de `notificaciones.seminariomr.org`.

Vuelve a Resend y comprueba que el dominio aparezca **Verified** y permita
enviar. En la configuración del dominio, desactiva el seguimiento de clics
y aperturas para los enlaces de acceso.

## 2. Conectar SMTP en Supabase

En Resend, crea una API key con permiso **Sending access** restringido al
dominio verificado. Esa clave será la contraseña SMTP. Copia la clave
directamente en Supabase; no la pegues en el chat ni en el repositorio.

En Supabase → **Authentication → Email → SMTP Settings**, o la sección de
SMTP personalizado de Authentication, activa **Custom SMTP** y completa:

| Campo | Valor |
| --- | --- |
| Sender email | `portal@notificaciones.seminariomr.org` |
| Sender name | `Portal Escolar del Seminario` |
| Host | `smtp.resend.com` |
| Port | `465` |
| Username | `resend` |
| Password | La API key de envío de Resend |

Comprueba los parámetros SMTP en la documentación o el panel de tu cuenta de
Resend antes de guardar. El puerto 465 utiliza TLS. Si el panel ofrece otros
puertos, utiliza la combinación de puerto y cifrado indicada por Resend.
La API key permanece en el servidor de Supabase; el navegador conserva
solamente la URL y la clave pública que ya utiliza.

Las rutas y etiquetas de los paneles pueden variar. La sección de plantillas
de Resend no configura estos mensajes: Supabase genera el contenido y Resend
lo entrega mediante SMTP.

## 3. Configurar enlaces y mensajes

En Supabase → **Authentication → URL Configuration**:

- Conserva **Site URL**: `https://seminariomr.org/portal/`.
- Añade a **Redirect URLs**: `https://seminariomr.org/portal/activar.html`.
- Conserva las otras URL del portal que ya estaban autorizadas.

En **Authentication → Email Templates**, pega el contenido completo de los
archivos siguientes en las plantillas correspondientes y guarda:

| Plantilla de Supabase | Asunto | Archivo del repositorio |
| --- | --- | --- |
| Invite user | `Activa tu acceso al Portal Escolar del Seminario` | `supabase/templates/invite.html` |
| Reset password | `Restablece tu contraseña del Portal Escolar` | `supabase/templates/recovery.html` |

Conserva la variable `{{ .ConfirmationURL }}` en los botones y enlaces.
Supabase genera ese enlace para cada destinatario. No lo reemplaces por la
dirección del portal ni por un enlace recibido en una prueba anterior.
Subir los HTML a GitHub no cambia las plantillas del proyecto de Supabase.

## 4. Probar recuperación con una cuenta existente

Antes de habilitar invitaciones:

1. Abre `https://seminariomr.org/portal/` sin una sesión iniciada.
2. Escribe el correo de una cuenta de prueba existente que controles.
3. Pulsa **¿Olvidaste tu contraseña?**.
4. Revisa la bandeja y la carpeta de spam. Comprueba en Resend el estado de
   entrega; una respuesta genérica del portal no demuestra la recepción.
5. Abre el enlace más reciente, guarda una contraseña nueva e inicia sesión.

Si el envío falla, revisa primero el remitente, SMTP y los registros de
Authentication. Si el enlace es rechazado, revisa la URL de redirección y
la plantilla. No se necesita crear un usuario ni cambiar roles para esta prueba.

## 5. Habilitar invitaciones desde Control Escolar

La migración `20261021070000_portal_invitations.sql` debe estar aplicada.
Si ya se ejecutó correctamente, no la repitas. Si no lo recuerdas, puedes
comprobar la tabla con esta consulta de solo lectura en SQL Editor:

```sql
select to_regclass('public.portal_invitations') as tabla_invitaciones;
```

Un resultado nulo indica que falta la tabla. Consulta entonces la instalación
de las migraciones en [la guía del campus](campus-autonomo.md), en su orden,
sin volver a ejecutar las que ya estén instaladas.

Con Node.js disponible, ejecuta desde PowerShell en la raíz del repositorio:

```powershell
npx supabase login
npx supabase functions deploy invite-person --project-ref ysiifytzvchubcdxbsxg --no-verify-jwt
```

La función valida el token con Auth y comprueba el rol activo en PostgreSQL.
La opción `--no-verify-jwt` corresponde a la verificación del gateway; la
autorización de esta función sigue siendo obligatoria.

En Supabase → **Edge Functions → Secrets**, configura:

| Nombre | Valor |
| --- | --- |
| `PORTAL_ORIGIN` | `https://seminariomr.org` |
| `PORTAL_INVITES_ENABLED` | `true`, después de completar la prueba de recuperación |

Supabase proporciona las variables privadas `SUPABASE_URL` y
`SUPABASE_SERVICE_ROLE_KEY` al servidor. No copies claves privadas al portal.

Finalmente, cambia en `portal/supabase-config.js`:

```javascript
features: Object.freeze({ invitations: true })
```

Publica ese cambio y comprueba el despliegue de GitHub Pages. La activación
requiere tanto la opción del navegador como la del servidor.

## 6. Probar la primera invitación

1. Entra al portal como **Control Escolar → Personas → Invitar persona**.
2. Utiliza otra dirección de correo que controles y que todavía no tenga
   cuenta en el proyecto. Asigna el rol **Alumno** para la prueba.
3. Abre la invitación, crea la contraseña y entra con esa cuenta.
4. Comprueba que figure como alumno, sin permisos de profesor ni administración.
5. Control Escolar podrá inscribirla en una clase desde el portal.

Una invitación no crea una bandeja de correo ni inscribe automáticamente a la
persona en materias. Las cuentas existentes siguen accediendo con su correo
y contraseña actuales; no necesitan otra invitación.

Si una invitación informa de un resultado incierto, comprueba Personas,
Authentication y los registros de la función antes de repetirla. Una operación
en revisión no se reenvía automáticamente.

## Límites gratuitos y funcionamiento diario

La cuenta mostraba un límite de **100 envíos diarios y 3,000 mensuales** en
Resend. Comprueba los límites que muestre tu panel antes de incorporar a las
60 personas. Un envío cuenta como correo, no como usuario del portal; entrar
al portal o consultar calificaciones no envía mensajes.

Supabase también aplica límites de envío, visibles en **Authentication → Rate
Limits**. El portal admite como máximo 20 solicitudes de invitación por
administrador en 10 minutos. Programa las altas en grupos respetando todos
esos límites y las cuotas que resten después de las pruebas.

Esta integración cubre invitaciones y recuperación de contraseña. Los avisos
automáticos de tareas o calificaciones requieren un módulo posterior; guardar
una nota no envía un correo actualmente. Los buzones institucionales completos
continúan pendientes, sin impedir el uso del portal con correos existentes.

Para suspender nuevas invitaciones mientras revisas un problema, establece
`PORTAL_INVITES_ENABLED=false` en el servidor y desactiva también la opción
pública. Las cuentas existentes conservan su acceso al portal.
