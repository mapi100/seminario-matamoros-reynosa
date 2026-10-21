# seminariomr.org: Porkbun, Cloudflare y GitHub Pages

| Servicio | Función |
| --- | --- |
| Porkbun | Registro y renovación del dominio |
| Cloudflare, plan Free | Servidores DNS del dominio |
| GitHub Pages | Publicación del sitio y certificado HTTPS |
| Supabase | Acceso al portal y datos escolares |

El dominio ya se compró en Porkbun. Usaremos Cloudflare para administrar los
DNS junto a los otros dominios de la cuenta. El sitio seguirá en GitHub Pages;
no hace falta transferir el registro, contratar hosting o crear un Worker.

**Completa la conexión DNS y la verificación antes de publicar el paquete.**
El archivo `CNAME` cambia el dominio de GitHub Pages. Estos archivos no
modifican los paneles de Porkbun, Cloudflare o Supabase.

## 1. Conectar el dominio a Cloudflare

1. En Cloudflare, abre **Domains → Add a domain / Onboard a domain**.
   Las etiquetas de los menús pueden cambiar.
2. Escribe `seminariomr.org`, continúa y selecciona el plan **Free**.
3. Permite el escaneo de DNS. Conserva los TXT de verificación y registros de
   correo existentes. El aparcamiento del dominio se reemplazará en el paso 3.
4. Continúa hasta ver los **dos nameservers asignados para seminariomr.org**.
   Copia ambos nombres completos. No uses los de otro dominio ni ejemplos.
5. En Porkbun: **Domain Management → seminariomr.org → Details →
   DNS & Nameservers → Nameservers**, pulsa el lápiz de **Nameservers**.
   Este paso no es el editor de **DNS Records**.
6. Sustituye la lista actual de servidores de Porkbun por los dos que
   Cloudflare asignó a este dominio y guarda.
7. Vuelve a Cloudflare y solicita la comprobación. Espera a que el dominio
   aparezca **Active**. La propagación puede tardar desde minutos hasta
   24 horas o más según las cachés DNS.

Después de activar Cloudflare, todos los A, CNAME y TXT de este dominio se
administran en **Cloudflare → seminariomr.org → DNS → Records**. El antiguo
editor DNS de Porkbun ya no tendrá efecto público. Porkbun conserva el registro
y la renovación del dominio; los otros dominios conservan su configuración.

## 2. Verificar la propiedad en GitHub

Antes de apuntar el dominio a GitHub Pages:

1. Abre la configuración de tu **cuenta GitHub** (no la del repositorio):
   **Settings → Pages → Add a domain**.
2. Escribe `seminariomr.org`. GitHub mostrará un nombre TXT y un valor únicos.
3. En **Cloudflare → seminariomr.org → DNS → Records → Add record**.
4. Añade **Type TXT**, **Name** con el nombre que te dio GitHub, normalmente
   `_github-pages-challenge-mapi100`, **Content** con el valor exacto generado
   y **TTL Auto**. Si GitHub muestra el nombre completo terminado en
   `.seminariomr.org`, en Name puedes escribir solo la parte anterior al dominio.
5. Regresa a GitHub y pulsa **Verify** cuando el registro se haya propagado.
   Conserva el TXT después de la verificación.

Si ya añadiste ese TXT en Porkbun, comprueba que se haya importado a Cloudflare
con el mismo nombre y valor, o añádelo manualmente allí. No copies los códigos
de verificación de tus otros dominios.

## 3. Preparar los registros DNS en Cloudflare

En **Cloudflare → seminariomr.org → DNS → Records**, configura:

| Tipo | Name | Content / Target | Proxy status | TTL |
| --- | --- | --- | --- | --- |
| A | `@` | `185.199.108.153` | **DNS only** (nube gris) | Auto |
| A | `@` | `185.199.109.153` | **DNS only** (nube gris) | Auto |
| A | `@` | `185.199.110.153` | **DNS only** (nube gris) | Auto |
| A | `@` | `185.199.111.153` | **DNS only** (nube gris) | Auto |
| CNAME | `www` | `mapi100.github.io` | **DNS only** (nube gris) | Auto |

`@` representa `seminariomr.org`; `www` representa `www.seminariomr.org`.
El destino CNAME no lleva `https://`, barra final ni el nombre del repositorio.
Desactiva la nube naranja en estos cinco registros: la configuración usa
Cloudflare como DNS y sirve el sitio directamente desde GitHub Pages.

Reemplaza únicamente los registros de aparcamiento que entren en conflicto
con el dominio raíz o con `www` (A, AAAA o CNAME de esos nombres).
Si se importó un CNAME comodín `*` de aparcamiento, también se puede quitar
del dominio nuevo.
Conserva los TXT de verificación y los registros de correo MX/TXT si existen.
Con estos cinco registros basta; IPv6 es opcional. Mantén los registros del
sitio en **DNS only** durante esta configuración. GitHub Pages emite el
certificado HTTPS; no necesitas ajustar el modo SSL de Cloudflare para DNS only.

La propagación puede tardar desde minutos hasta 24 horas. No cambies los DNS
de `marcopenaibarra.com` ni de `guadalupematamoros.org`.

## 4. Actualizar Supabase antes del cambio

En tu proyecto **Seminario MR → Authentication → URL Configuration**:

1. Añade estas entradas a **Redirect URLs** y guarda:

   ```text
   https://seminariomr.org/portal/
   https://seminariomr.org/portal/index.html
   https://seminariomr.org/portal/panel.html
   ```

2. Mientras haces el cambio puedes conservar temporalmente las URL exactas de
   GitHub Pages que ya funcionaban.
3. Cuando HTTPS esté disponible y puedas abrir el portal en el nuevo dominio,
   cambia **Site URL** por:

   ```text
   https://seminariomr.org/portal/
   ```

Este acceso usa correo y contraseña y redirige dentro del propio sitio.
Las URL de Supabase también dejan preparado el destino de futuros correos de
autenticación. El código, la Project URL y la clave pública de Supabase no
cambian. Tendrás que iniciar sesión otra vez en el dominio nuevo: el navegador
guarda la sesión por origen.

## 5. Publicar los archivos y conectar GitHub Pages

Después de activar Cloudflare, verificar el dominio y preparar los DNS:

1. Extrae el contenido de `seminario-dominio-cloudflare.zip` en la raíz de
   **seminario-matamoros-reynosa**, junto a `index.html`, conservando las rutas.
   El paquete contiene `CNAME`, `robots.txt`, `sitemap.xml`, esta guía y las
   versiones actualizadas de `index.html`, `portal/index.html` y `README.md`.
   No cambia el SQL ni los módulos de materias y calificaciones.
2. En la terminal, desde esa carpeta, revisa y publica:

   ```bash
   git status
   git diff -- index.html portal/index.html README.md
   cat CNAME
   git add CNAME robots.txt sitemap.xml index.html portal/index.html README.md docs/dominio-seminariomr.md
   git commit -m "Configurar seminariomr.org y metadatos del sitio"
   git pull --rebase origin main
   git push origin main
   ```

   `cat CNAME` debe mostrar solamente `seminariomr.org`. Si el pull avisa de un
   conflicto, resuélvelo antes de seguir; no uses `push --force`. Si descargaste
   el ZIP dentro del proyecto, no necesitas subirlo al repositorio.
3. Abre **mapi100/seminario-matamoros-reynosa → Settings → Pages**.
   Mantén la fuente de publicación actual. En **Custom domain**, comprueba que
   esté `seminariomr.org`; escríbelo y guarda si hace falta.
4. Espera a que GitHub confirme los DNS y emita el certificado. Activa
   **Enforce HTTPS** cuando esté disponible.
5. Comprueba estas direcciones:

   - `https://seminariomr.org/` → sitio principal.
   - `https://www.seminariomr.org/` → redirige al dominio sin `www`.
   - `http://seminariomr.org/` → redirige a HTTPS.
   - `https://seminariomr.org/robots.txt` → reglas de rastreo y sitemap.
   - `https://seminariomr.org/sitemap.xml` → solo la portada pública.
   - `https://seminariomr.org/portal/` → acceso al portal; prueba entrar y salir.

Si HTTPS aún no está disponible, espera al certificado antes de probar el
inicio de sesión. No cambies contraseñas o claves para resolver un problema DNS.

## 6. Registrar el sitio en Google Search Console

Esto requiere tu cuenta de Google y un código nuevo para este dominio:

1. Abre [Google Search Console](https://search.google.com/search-console/).
2. **Añadir propiedad → Dominio**: escribe `seminariomr.org`, sin `https://` ni
   rutas. Copia el TXT `google-site-verification=...` generado para esta propiedad.
3. En **Cloudflare → seminariomr.org → DNS → Records**, añade otro registro
   **TXT**, con **Name `@`**, **Content** con ese valor completo y **TTL Auto**.
   Conserva también el TXT de GitHub: son registros diferentes.
4. En Search Console pulsa **Verificar**. Si todavía no lo encuentra, espera
   la propagación y vuelve a verificar sin borrar los TXT.
5. En **Sitemaps** envía `https://seminariomr.org/sitemap.xml`.
6. En **Inspección de URLs**, inspecciona `https://seminariomr.org/`; comprueba
   la URL publicada y usa **Solicitar indexación** si está disponible.

Enviar el sitemap o pedir indexación no garantiza aparecer inmediatamente.
El estado se comprueba después en Search Console. No se solicitan las URL del
portal ni cada fragmento `#seccion`: las secciones forman una sola página.

## Qué aporta cada archivo

- `CNAME`: declara el dominio del sitio de GitHub Pages.
- `robots.txt`: permite el rastreo y anuncia dónde está el sitemap.
- `sitemap.xml`: enumera la única página pública actual, con su URL HTTPS.
- `index.html`: título y descripción, URL canónica, favicon, Open Graph y
  Twitter Cards para compartir, y datos estructurados del Seminario. La imagen
  social es la fotografía existente `images/seminario_completo.jpg`.
- `portal/index.html` y `portal/panel.html`: indican `noindex, nofollow`.
  El panel ya tenía esa indicación; se añade al acceso.

El portal no aparece en el sitemap. No lo bloqueamos en `robots.txt` porque
Google necesita leer el `noindex` de sus páginas. Esto controla indexación;
los datos escolares siguen protegidos por Supabase Auth y RLS.

Se revisaron los repositorios `mapi100/personal-website` y
`mapi100/parroquia-guadalupe-matamoros`: usan CNAME, robots y sitemap. Esos
archivos no demuestran su estado de indexación en Google y sus códigos de
verificación no se pueden reutilizar aquí.

## Referencias oficiales

- [Porkbun: ayuda](https://kb.porkbun.com/)
- [Cloudflare: conectar un dominio](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/)
- [Cloudflare: estado de proxy](https://developers.cloudflare.com/dns/proxy-status/)
- [GitHub Pages: administrar el dominio](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)
- [GitHub Pages: verificar la propiedad](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages)
- [GitHub Pages: HTTPS](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https)
- [Google: verificar la propiedad](https://support.google.com/webmasters/answer/9008080?hl=es)
- [Google: administrar sitemaps](https://support.google.com/webmasters/answer/7451001?hl=es)

Estos enlaces son referencias oficiales. Su contenido actual no pudo
consultarse desde este entorno por una restricción de red; confirma los
nombres de menús en los paneles del proveedor.
