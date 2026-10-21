# Instalar y probar el panel de profesor

El profesor puede consultar las materias que tiene asignadas por periodo y
abrir sus listas de alumnos activos. Esta etapa muestra nombres; todavía no
permite capturar notas, modificar inscripciones ni publicar tareas.

## 1. Extraer la actualización

Guarda `seminario-profesores.zip` dentro de `seminario-matamoros-reynosa`.
Desde la terminal en esa carpeta:

```bash
cp -a portal "../portal-respaldo-$(date +%Y%m%d-%H%M%S)"
unzip -o seminario-profesores.zip
```

Se conserva tu configuración pública de Supabase. El respaldo queda fuera del
repositorio y los scripts de datos usan marcadores genéricos.

## 2. Aplicar la nueva migración

Abre `supabase/migrations/20261021030000_create_teaching_assignments.sql` con tu
editor. Copia el archivo completo en **Supabase → SQL Editor → New query** y pulsa
**Run**. Ejecuta esta migración una sola vez. Las de perfiles, materias y notas
ya están aplicadas: no las repitas.

Esta migración crea las asignaciones y la función de lectura del listado de
alumnos. La función verifica los permisos en PostgreSQL; no contiene claves
privadas ni permite escribir datos. Si ocurre un error, ejecuta `rollback;` y
revisa el mensaje antes de continuar.

## 3. Crear una cuenta distinta para probar al profesor

En **Authentication → Users → Add user**, crea una cuenta de prueba con un correo
distinto del de alumno. Confirma su correo para que pueda iniciar sesión; si la
pantalla ofrece confirmación automática, puedes usarla para esta cuenta de prueba.
Elige la contraseña en Supabase y consérvala privada.

Copia el UID de la nueva cuenta. En otra consulta nueva de SQL Editor, pega
todo `supabase/seeds/demo_professor_profile.sql`. Sustituye `PROFESSOR_UID_AQUI`
por ese UID, conservando las comillas, y pulsa **Run**.

Se crea un perfil llamado **Profesor de prueba**, activo y con rol `professor`.
El script rechaza una cuenta que ya sea alumno o esté inactiva: no convierte ni
reactiva perfiles existentes. No cambies el rol de tu alumno actual.

## 4. Asignarle las materias DEMO

Copia también el UID de tu alumno de prueba desde **Authentication → Users**.
En otra consulta nueva, pega `supabase/seeds/demo_teaching.sql` y sustituye:

- `STUDENT_UID_AQUI`: UID del alumno que ya ve Filosofía e Historia.
- `PROFESSOR_UID_AQUI`: UID del profesor nuevo.

Pulsa **Run**. Debe indicar que se asignaron dos materias DEMO. No se crean
inscripciones ni se modifican notas. Repetir el script no duplica asignaciones.
Sustituye los UID solo en SQL Editor; conserva los marcadores en GitHub.

## 5. Comprobar los permisos

Pega `supabase/tests/professor_rls.sql` en otra consulta nueva. Sustituye
`PROFESSOR_UID_AQUI` por el UID del profesor y ejecuta todo. Debe mostrar:

```text
Profesor: RLS y permisos OK
```

Es una comprobación de solo lectura. Las pruebas locales entre dos profesores
y varios alumnos están documentadas en [supabase/README.md](../supabase/README.md).
Para comprobar la integración real, usa también cuentas distintas en el portal.

## 6. Publicar y probar las dos cuentas

Desde la raíz del repositorio, en la terminal:

```bash
git add README.md portal/ supabase/ tests/ docs/
git commit -m "Agregar materias y listas de alumnos para profesores"
git pull --rebase origin main
```

Si termina sin conflictos:

```bash
git push origin main
```

Cuando Pages publique, cierra la sesión de alumno e inicia sesión con la cuenta
de profesor. Debes ver **Panel de profesor**, **Mis materias asignadas**, las dos
materias DEMO y el botón **Ver alumnos**. Al abrir cada una debe aparecer tu
**Usuario de prueba**, si sigue activo y con rol de alumno.

Prueba cambiar de materia, cerrar la lista, recargar y cerrar sesión. Al salir,
los nombres deben desaparecer. Vuelve a entrar como alumno: sus materias y notas
deben seguir funcionando y la lista de profesor debe permanecer oculta.
Si se mantiene una versión anterior, recarga con **Ctrl + Shift + R**.

Por ahora una lista se define por **materia y periodo**. Dos profesores asignados
a esa misma combinación comparten el listado. Los grupos separados y la captura
de notas se añadirán en etapas posteriores con sus propias reglas de acceso.
