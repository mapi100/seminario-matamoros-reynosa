# Instalar calificaciones de prueba

Esta actualización añade una nota publicada a cada tarjeta de **Mis materias**.
La escala acordada es de **0 a 100**, con hasta dos decimales. Se registra una
nota por inscripción, cargada y publicada desde administración. No se calculan
promedios ni se decide si el alumno aprobó.

## 1. Extraer la actualización

Guarda `seminario-calificaciones.zip` en tu carpeta `seminario-matamoros-reynosa`.
Desde la terminal, dentro de esa carpeta:

```bash
cp -a portal "../portal-respaldo-$(date +%Y%m%d-%H%M%S)"
unzip -o seminario-calificaciones.zip
```

El respaldo queda fuera del repositorio. La actualización conserva la
configuración pública de Supabase y las materias existentes.

## 2. Crear la tabla de notas

Abre `supabase/migrations/20261021020000_create_enrollment_grades.sql` con tu editor.
Copia el archivo completo en **Supabase → SQL Editor → New query** y pulsa **Run**.
Ejecuta esta nueva migración **una sola vez**. Las migraciones de perfiles y
materias ya se aplicaron: no las repitas.

Si ocurre un error, ejecuta `rollback;` y revisa el mensaje antes de continuar.
Subir el archivo a GitHub no ejecuta este SQL.

## 3. Cargar las notas DEMO

Copia el UID de tu alumno de prueba desde **Authentication → Users**. En otra
consulta nueva de SQL Editor, pega todo `supabase/seeds/demo_grades.sql`.
Sustituye `PEGA_AQUI_EL_UID` por ese UID, conservando las comillas, y pulsa **Run**.
Haz la sustitución solo en la consulta; conserva el marcador en GitHub.

El script requiere las dos inscripciones DEMO que ya ves en tu portal. Añade:

- Filosofía: **85.50**, publicada.
- Historia: **72.00**, sin publicar.

Ambas notas son ficticias. El script no crea usuarios ni inscripciones, no cambia
el perfil y se puede repetir sin duplicar registros. Si ya existe una nota DEMO
con otro valor o estado, aborta sin sobrescribirla.

## 4. Verificar los permisos

En otra consulta nueva, pega `supabase/tests/grades_rls.sql`, sustituye el mismo
marcador por el mismo UID y ejecuta el archivo completo. Debe mostrar:

```text
Calificaciones: RLS y permisos OK
```

La consulta es de solo lectura y termina restaurando la transacción. Comprueba
nota publicada propia, permisos y una identidad ficticia sin perfil. Las pruebas
locales entre dos alumnos se describen en [supabase/README.md](../supabase/README.md).

## 5. Publicar y probar

En la terminal, dentro del repositorio:

```bash
git add README.md portal/ supabase/ tests/ docs/
git commit -m "Mostrar calificaciones publicadas de 0 a 100"
git pull --rebase origin main
```

Si termina sin conflictos:

```bash
git push origin main
```

Tras publicarse GitHub Pages, inicia sesión. Filosofía debe mostrar
**Calificación publicada: 85.5 / 100** e Historia **Sin calificación publicada**.
Si persiste una versión anterior, recarga con **Ctrl + Shift + R**.

Recarga, vuelve a la pestaña y cierra sesión para comprobar el flujo completo.
Una segunda cuenta de alumno debe ver únicamente sus propias notas publicadas.
El navegador no puede leer el 72 del borrador ni editar notas.

Si falla la consulta de notas, las materias seguirán visibles con un mensaje de
error y **Reintentar**. No interpretes un error de conexión como ausencia de nota.
