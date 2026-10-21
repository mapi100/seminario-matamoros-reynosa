# Instalar «Mis materias»

Esta actualización añade la consulta de materias inscritas del alumno. Cada
tarjeta muestra código, nombre, periodo y fechas. Las inscripciones se asignan
desde administración en Supabase; el alumno solo puede consultar las propias.

## 1. Extraer los archivos en tu computadora

Guarda `seminario-mis-materias.zip` dentro de la carpeta
`seminario-matamoros-reynosa`. En tu terminal de Ubuntu:

```bash
cd ~/Documents/documentos_personales/mapi/Website/diocesis/seminario/seminario-matamoros-reynosa
cp -a portal "../portal-respaldo-$(date +%Y%m%d-%H%M%S)"
unzip -o seminario-mis-materias.zip
```

`unzip -o` actualiza el panel anterior. El ZIP incluye únicamente los archivos
de esta actualización; conserva tu configuración pública de Supabase.

## 2. Crear las tablas en Supabase

Abre en tu editor el archivo
`supabase/migrations/20261021010000_create_academics.sql`.
Copia **todo su contenido**, entra a tu proyecto Supabase y abre
**SQL Editor → New query**. Pega el contenido y pulsa **Run**.

Ejecuta esta nueva migración **una sola vez**. No repitas la migración
`20261021000000_create_profiles.sql`: la tabla de perfiles ya existe.
Si aparece un error, ejecuta `rollback;` en SQL Editor y revisa el mensaje antes
de continuar.

## 3. Inscribir tu cuenta de prueba en dos materias ficticias

En **Authentication → Users**, copia el UID de tu alumno de prueba.

Abre `supabase/seeds/demo_enrollments.sql` en tu editor, copia todo su contenido
y pégalo en **otra consulta nueva** de SQL Editor. En esa consulta sustituye
`PEGA_AQUI_EL_UID` por el UID que copiaste, conservando las comillas. Pulsa **Run**.

El resultado debe indicar que los datos de ejemplo están listos. Se añaden
**Filosofía — ejemplo** e **Historia — ejemplo**, dentro de un periodo DEMO.
No son materias oficiales. No se crean usuarios ni se cambia tu perfil.

Conserva el marcador genérico en el archivo de GitHub. La consulta exige un
perfil activo con rol `student` y se puede repetir sin duplicar inscripciones.

## 4. Comprobar los permisos

Copia `supabase/tests/academics_rls.sql` en **otra consulta nueva** de SQL Editor.
Sustituye el mismo marcador por el mismo UID y pulsa **Run**. Debe mostrar:

```text
Materias: RLS y permisos OK
```

Esta prueba no modifica datos. Para probar el aislamiento real entre cuentas,
usa dos alumnos distintos: cada uno debe ver solo las inscripciones que se le
asignaron. Las pruebas locales reproducibles y sus límites están documentados
en [supabase/README.md](../supabase/README.md).

## 5. Publicar el portal

En la terminal, desde la raíz del repositorio:

```bash
git add README.md portal/ supabase/ tests/ docs/
git commit -m "Agregar consulta de materias inscritas con RLS"
git pull --rebase origin main
```

Si termina sin conflictos, publica:

```bash
git push origin main
```

Si aparece `CONFLICT`, resuelve el conflicto antes de continuar. El ZIP es un
medio de transferencia: no hace falta añadirlo a Git.

Cuando GitHub Pages termine de publicar, inicia sesión en el portal. Debes ver
**Mis materias** con las dos tarjetas DEMO. Si sigue apareciendo la versión
anterior, recarga con **Ctrl + Shift + R**. Recarga normalmente y prueba cerrar
sesión: al salir, las materias deben desaparecer junto con el perfil.

Subir archivos a GitHub publica el sitio; las tablas y los datos se aplican
por separado en Supabase, siguiendo los pasos anteriores.
