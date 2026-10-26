# Portadas automáticas de los cursos

Cada subida a `main` ejecuta el flujo **Publicar página y actualizar portadas**.
El flujo revisa los archivos de `images/`, genera el catálogo y publica el sitio
completo en GitHub Pages. Las fotografías nuevas pasan a estar disponibles para
las clases sin editar una lista de nombres.

## Activación inicial, una sola vez

1. Copia el paquete en la raíz del repositorio, conservando todas las carpetas,
   **incluida `.github`**. No coloques `.github` dentro de `portal`.
2. En GitHub → repositorio → **Settings → Pages → Build and deployment**, cambia
   **Source** de *Deploy from a branch* a **GitHub Actions**. Esta selección es
   necesaria para ejecutar la preparación automática del catálogo.
3. Publica los archivos con un commit a `main`:

   ```powershell
   git add .
   git commit -m "Automatizar portadas y publicacion del seminario"
   git push origin main
   ```

4. En la pestaña **Actions**, espera a que **Publicar página y actualizar
   portadas** termine correctamente. Después recarga el portal con Ctrl+F5.
   Si cambiaste Source después de subir el commit, abre ese flujo y pulsa
   **Run workflow → main → Run workflow** para iniciarlo de nuevo.

El sitio conserva `seminariomr.org`, su `CNAME`, los favicons y todos los archivos
del portal, incluidas las ponderaciones. No requiere SQL ni cambios de DNS.
La publicación utiliza las acciones oficiales de GitHub Pages y no hace commits
automáticos de vuelta al repositorio.

## Agregar fotos de ahora en adelante

Sube los archivos a **`images/`**, o a una subcarpeta dentro de ella, y confirma
los cambios en `main`. Espera a que termine el flujo de Actions y recarga el
portal. También sirve agregarlas desde la página de GitHub con **Add file →
Upload files**, confirmando el commit en `main`.

Formatos: **JPG, JPEG, PNG, WebP, AVIF y GIF**. Se admiten nombres con espacios,
acentos y mayúsculas; sus rutas se codifican automáticamente. Al quitar o
renombrar fotos, el siguiente despliegue también actualiza el catálogo.

Se omiten los nombres que empiezan con `escudo`, `logo`, `favicon` o
`apple-touch-icon`, las carpetas de logos/iconos, archivos ocultos, imágenes
dañadas, vacías o demasiado pequeñas. Así los símbolos de la cabecera no se
convierten en portadas. El PNG `jesus_y_maria_2.png` actual se omite porque es
completamente transparente. Los originales no se modifican.

## Reparto y presentación

La portada se elige mediante un sorteo reproducible usando el código de materia
y el periodo. Una clase tiene la misma imagen en sus tarjetas, encabezado y
unidades, y para alumno, profesor y Control Escolar. No se vuelve a sortear en
cada recarga.

Cuando entra una foto nueva, algunas clases pueden adoptarla; las demás conservan
su selección. La imagen nueva queda disponible, aunque no necesariamente será
elegida si existen más fotografías que clases. Se permiten portadas repetidas.

Las tarjetas, encabezados y unidades conservan las dimensiones y el diseño
adaptable que tenían los colores. Las fotos se ajustan con `cover`, con recorte
en lugar de deformación. El encabezado oscurece la foto para facilitar la lectura;
el encabezado compacto del libro del profesor conserva su presentación actual.
Si una foto no carga, permanece el color de respaldo.

## Archivos y pruebas

- `.github/workflows/publicar-pagina.yml`: preparación y despliegue automáticos.
- `scripts/generate_course_images.py`: descubre y valida las fotos.
- `scripts/build_static_site.py`: prepara el sitio y actualiza la versión del
  catálogo para evitar que se siga cargando una copia anterior desde caché.
- `portal/course-images.js`: copia inicial del catálogo para uso local. En cada
  publicación se regenera dentro del sitio desplegado; no hace falta editarla.
- `portal/course-colors.js`: reparto por clase y color de respaldo.

Los puntos focales opcionales de algunas fotos conocidas están en el generador;
no son una lista de admisión. Cualquier foto nueva válida entra automáticamente.

```sh
python -m pip install -r scripts/requirements-images.txt
python -m unittest discover -s tests -p 'test_course_images.py'
node tests/course_images.mjs
python scripts/build_static_site.py --output /tmp/seminario-sitio-nuevo
python tests/portal_content_files.py
```

La carpeta de salida debe ser nueva. El generador y el despliegue no usan
credenciales de Supabase. Las pruebas del portal usan Chromium y API simulada.
