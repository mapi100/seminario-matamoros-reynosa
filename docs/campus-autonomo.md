# Campus del Seminario: administración y experiencia del portal

El portal tiene una organización inspirada en plataformas educativas como
Brightspace, con identidad propia del Seminario: navegación lateral, inicio por
rol, tarjetas de materias, búsqueda, filtros por periodo y formularios accesibles
para escritorio y celular.

## Qué puede hacer cada persona

- **Control Escolar:** invitar personas cuando el envío esté habilitado, editar
  nombres y acceso, administrar materias y periodos, abrir clases, asignar
  profesores, inscribir alumnos, consultar notas publicadas, tramitar bajas y revisar la actividad.
- **Profesor:** consultar sus clases y alumnos, guardar borradores y publicar
  calificaciones de 0 a 100. Una asignación inactiva deja de autorizar consultas
  y cambios.
- **Alumno:** consultar sus materias y calificaciones publicadas. Los borradores
  permanecen privados.

Los responsables crean las clases desde el portal. Esta versión organiza **una
clase por materia y periodo**. Varios profesores pueden estar asignados a esa
clase; grupos paralelos de una misma materia y periodo requieren ampliar el
modelo antes de usarse. Una persona con historial académico conserva su rol.
Control Escolar puede conceder acceso a otro responsable, pero no quitarse su
propio rol ni darse de baja desde el portal.

Las bajas conservan los registros y notas. Reactivar una inscripción restaura
la misma identidad y sus calificaciones. Desactivar una clase retira su acceso
a alumnos y profesores; sus registros permanecen disponibles para administración.

## 1. Integrar el paquete en Windows

1. Descarga `seminario-campus-autonomo.zip` y extráelo fuera del repositorio,
   por ejemplo en Descargas.
2. Abre la carpeta extraída. Dentro verás `portal`, `supabase`, `docs`, `tests`
   y `README.md`.
3. Copia **esos cinco elementos**, entra en `seminario-matamoros-reynosa` y
   pégalos. Combina las carpetas y reemplaza los archivos del mismo nombre.
   Se conservan las imágenes, el SQL anterior y los demás archivos del portal.
4. Comprueba que `portal/workspace.js` y `portal/management.js` estén junto a
   `portal/panel.html`; no dentro de otra carpeta llamada como el ZIP.

No necesitas crear materias o notas de ejemplo. La migración reconoce las
clases existentes a partir de las inscripciones y asignaciones actuales.

## 2. Aplicar las migraciones una sola vez

El proyecto ya utiliza las migraciones anteriores hasta
`20261021050000_control_catalogs.sql`. En Supabase → **SQL Editor**, ejecuta
primero el contenido completo de:

```text
supabase/migrations/20261021060000_portal_management.sql
```

Después, en otra consulta, ejecuta:

```text
supabase/migrations/20261021070000_portal_invitations.sql
```

Es una instalación inicial por parte del responsable técnico. Después, las
altas, asignaciones, inscripciones y bajas se hacen con formularios del portal.
Las migraciones son transaccionales y no se deben ejecutar dos veces. Si una
consulta falla, revisa el error antes de continuar con la siguiente.

La segunda migración prepara invitaciones, pero no envía correos ni crea
cuentas por sí sola. Las funciones de invitación solo se conceden a
`service_role`; los usuarios del navegador no pueden ejecutarlas directamente.

## 3. Publicar y comprobar

En PowerShell, dentro del proyecto:

```powershell
git status
git add portal/ supabase/ docs/campus-autonomo.md tests/ README.md
git commit -m "Crear campus con navegación por rol y administración escolar"
git pull --rebase origin main
git push origin main
```

Si un comando informa de un conflicto, resuélvelo antes de seguir. El ZIP puede
quedarse en Descargas; no se necesita subirlo al repositorio.

Espera el despliegue en GitHub Actions y abre:

```text
https://seminariomr.org/portal/
```

Prueba con tus cuentas existentes:

1. **Control Escolar:** Inicio → Materias y periodos. Crea o edita un catálogo.
2. **Clases:** abre una materia en un periodo. No es una inscripción automática.
3. En esa clase, pulsa **Asignar profesor** y busca una cuenta de profesor activa.
4. Pulsa **Inscribir** y busca una cuenta de alumno activa.
5. Entra como profesor: debe aparecer la clase y su lista. Guarda y publica una
   nota ficticia solo en una cuenta de prueba.
6. Entra como alumno: debe aparecer la materia y la nota publicada.
7. Da de baja y reactiva la inscripción desde Control Escolar: la nota se conserva.
8. Prueba en celular el botón de menú, la navegación y los formularios.

La actividad registra actor, acción, fecha y entidad. No se necesita borrar
filas para corregir una inscripción o una asignación.

## 4. Preparar invitaciones y recuperación de contraseña

Para utilizar Resend con los correos actuales de alumnos y sacerdotes, sigue
[la configuración de correo del portal](correo-resend.md). Incluye el remitente,
los campos SMTP y las plantillas de invitación y recuperación en español.

**Estado inicial: invitaciones desactivadas.** En Personas se indica que el
servicio está pendiente, mientras se permite administrar las cuentas existentes.
El botón se habilita con `features.invitations` en `portal/supabase-config.js`;
la Edge Function también exige autorización y una opción de activación propia.
Cambiar el navegador nunca sustituye las comprobaciones del servidor.

Antes de activar el envío:

1. Configura **SMTP personalizado en Supabase Authentication** con un proveedor
   de correo transaccional. Revisa su plan y límites antes de contratarlo.
   El servicio SMTP predeterminado de Supabase tiene restricciones y no es
   suficiente para dar por listo el envío a todos los seminaristas.
2. Configura la dirección de remitente verificada que indique ese proveedor.
   Sus credenciales van exclusivamente en Supabase. Sus registros DNS se añaden
   en Cloudflare conservando los A, CNAME y TXT actuales.
3. En **Authentication → URL Configuration → Redirect URLs**, añade:

   ```text
   https://seminariomr.org/portal/activar.html
   ```

   Conserva `https://seminariomr.org/portal/` como Site URL y las URL del portal
   que ya funcionaban. La plantilla de invitación debe enlazar la
   `ConfirmationURL` de Supabase, como la plantilla predeterminada.
4. Despliega `supabase/functions/invite-person` en tu proyecto. Con Node.js y
   la CLI de Supabase, desde el repositorio:

   ```powershell
   npx supabase login
   npx supabase functions deploy invite-person --project-ref ysiifytzvchubcdxbsxg --no-verify-jwt
   ```

   El acceso se autoriza dentro de la función: consulta Auth para validar el
   token y verifica el rol activo en PostgreSQL. `--no-verify-jwt` desactiva la
   verificación del gateway, no las verificaciones de esta función.
5. En **Edge Functions → Secrets**, configura:

   | Nombre | Valor |
   | --- | --- |
   | `PORTAL_ORIGIN` | `https://seminariomr.org` |
   | `PORTAL_INVITES_ENABLED` | `true`, solo después de probar SMTP |

   `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` son variables del servidor
   suministradas por Supabase. Nunca pongas esa clave en JavaScript público,
   GitHub, un ZIP o el chat.
6. En `portal/supabase-config.js`, cambia únicamente:

   ```javascript
   features: Object.freeze({ invitations: true })
   ```

   Publica ese cambio y envía una invitación a una cuenta de prueba que controles.
7. El invitado recibe un enlace, abre `activar.html`, crea una contraseña de
   al menos 12 caracteres y entra al portal con su rol asignado por Control
   Escolar. Los tokens se retiran de la dirección al abrir la página.
8. Prueba **¿Olvidaste tu contraseña?** escribiendo primero el correo en el
   acceso. La respuesta es genérica para no revelar si una cuenta existe.

### Si falla una invitación

No se reenvía automáticamente una operación de resultado incierto. Revisa
Personas y los registros de Auth antes de intentar una nueva invitación.
`portal_invitations` conserva la solicitud y su estado para que el responsable
pueda reconciliar un fallo de SMTP o de red sin crear cuentas duplicadas.

Una solicitud enviada vuelve a responder correctamente si se repite el mismo
identificador; una solicitud en curso o incierta exige revisión. Si se pierde
la autorización antes de registrar el perfil, la función cancela la operación
y, cuando el error confirma una transacción fallida, retira la cuenta de Auth
recién creada. Un timeout nunca provoca borrar una cuenta posiblemente válida.

## 5. Buzones nombre@seminariomr.org

Los buzones institucionales y las cuentas del portal son servicios distintos.
La invitación no crea un buzón. Por ahora se puede usar el correo existente de
cada persona para acceder al portal.

La elegibilidad del Seminario para Google Workspace for Nonprofits o Education
está pendiente de confirmar. Antes de registrar un proveedor o cambiar MX,
se debe consultar con el Seminario su reconocimiento educativo o documentación
legal y confirmar el plan que apruebe el proveedor. Después se crean buzones,
se configuran MX/SPF/DKIM/DMARC y se prueba envío y recepción.

Cloudflare Email Routing puede reenviar correo a cuentas existentes, pero no
proporciona por sí mismo buzones con envío y recepción independientes.
El SMTP transaccional usado para invitaciones tampoco sustituye esos buzones.

## Validación y límites de esta entrega

Validación realizada para esta entrega:

| Comprobación | Resultado |
| --- | --- |
| PostgreSQL: permisos, historial, invitaciones y concurrencia | 120 aprobadas |
| Navegador: escenarios anteriores y nuevo campus | 185 aprobados |
| Servicio de invitaciones: autorización y fallos de red/SMTP | 22 aprobados |

Las pruebas utilizan PostgreSQL desechable y una API simulada con el SDK real.
No crean alumnos, materias, notas ni buzones en producción:

```powershell
python supabase/tests/run_management_local.py
node tests/invite_function.mjs
python tests/portal_workspace.py
```

Las pruebas del navegador requieren Python, Playwright y Chromium. El SQL usa
Docker con `postgres:17-bookworm`; el servicio de invitaciones se prueba con
Node.js 24. Los escenarios anteriores de materias, notas, profesores, captura y
catálogos también se conservan en `tests/`.

Esta entrega cubre administración escolar, navegación y acceso. Las tarjetas
muestran las materias y notas actuales; actividades, entregas, cuestionarios y
contenidos por unidad corresponden a módulos posteriores. El sitio público,
HTTPS y sitemap continúan usando su configuración actual; las páginas del
portal, incluida la activación, llevan `noindex`.
