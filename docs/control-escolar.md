# Instalar y probar Control Escolar

Esta actualización añade **Catálogos académicos** al panel de Control Escolar.
Permite consultar y crear periodos y materias desde la página. Reutiliza las
tablas existentes y conserva el acceso de alumnos y profesores.

## 1. Extraer la actualización

Guarda `seminario-control-escolar.zip` dentro de tu carpeta del repositorio.
Desde la terminal en esa carpeta:

```bash
cp -a portal "../portal-respaldo-$(date +%Y%m%d-%H%M%S)"
unzip -o seminario-control-escolar.zip
```

## 2. Aplicar solo la nueva migración

Abre `supabase/migrations/20261021050000_control_catalogs.sql` con tu editor.
Copia su contenido completo en **Supabase → SQL Editor → New query** y pulsa
**Run**. Ejecuta esta migración una sola vez desde la cuenta administrativa de
confianza. Las cinco migraciones anteriores ya se aplicaron: no las repitas.

El archivo añade permisos de consulta de catálogos para Control Escolar,
funciones de creación, protección contra duplicados y auditoría privada. No crea
periodos ni materias por sí solo. Si ocurre un error, ejecuta `rollback;` y revisa
el mensaje antes de continuar. Si ya hubiera códigos o periodos duplicados por
mayúsculas/espacios, hay que revisarlos: la migración no borra ni fusiona datos.

## 3. Crear una cuenta de prueba de Control Escolar

En **Authentication → Users → Add user**, crea una cuenta con un correo distinto
de los usados para alumno y profesor. Confirma el correo para poder entrar;
puedes usar la confirmación automática si aparece para esta cuenta de prueba.
Elige y conserva la contraseña en privado.

Copia el UID nuevo. En otra consulta de SQL Editor, pega todo
`supabase/seeds/demo_control_profile.sql`. Sustituye `CONTROL_UID_AQUI` por ese
UID, conservando las comillas, y pulsa **Run**.

Debe indicar **Perfil de Control Escolar de prueba listo**. El script rechaza
convertir un alumno/profesor o reactivar una cuenta inactiva; no cambia los
perfiles existentes. Introduce el UID solo en SQL Editor y conserva el marcador
en el archivo de GitHub.

## 4. Comprobar los permisos

Pega `supabase/tests/control_catalogs_rls.sql` en otra consulta nueva. Sustituye
el mismo marcador por el UID de Control Escolar y ejecuta el archivo completo.
Debe mostrar:

```text
Control Escolar: RLS y permisos OK
```

Esta comprobación es de solo lectura. Las pruebas reproducibles entre roles y
sus límites se describen en [supabase/README.md](../supabase/README.md).

## 5. Publicar el portal

En la terminal, desde la raíz del repositorio:

```bash
git add README.md portal/ supabase/ tests/ docs/
git commit -m "Agregar catalogos de periodos y materias para Control Escolar"
git pull --rebase origin main
```

Si termina sin conflictos:

```bash
git push origin main
```

Cuando GitHub Pages termine de publicar, recarga el portal con
**Ctrl + Shift + R**, cierra la sesión anterior e inicia sesión como Control
Escolar. Debe aparecer **Panel de Control Escolar → Catálogos académicos**.

## 6. Crear registros de prueba desde la página

En **Periodos académicos**, escribe:

- Nombre: **DEMO 2027 — prueba de Control**.
- Inicio: **2027-01-11**.
- Fin: **2027-06-25**.

Pulsa **Crear periodo**. Debe confirmar la creación y actualizar la lista.

En **Materias**, escribe:

- Código: **DEMO-CE-101**.
- Nombre: **Materia de prueba de Control Escolar**.

Pulsa **Crear materia**. Debe confirmar la creación. Recarga para comprobar que
los dos registros permanecen. Si repites el mismo código o el nombre del periodo,
debe rechazar el duplicado sin modificar el registro existente.

Los formularios son independientes: crear una materia la añade al catálogo.
Las asignaciones a profesores y las inscripciones se añadirán en otra etapa;
los alumnos siguen viendo únicamente las materias en las que estén inscritos.
En este módulo no hay edición, eliminación ni administración de usuarios.

Si falla la conexión después de crear, el registro puede haberse guardado. Pulsa
**Actualizar lista**, revisa el resultado y después decide si hace falta volver
a crear. El portal no repite escrituras automáticamente. Si confirmó una creación
y solo falló la lectura posterior, conservará el mensaje de creación.

Las altas hechas por estas funciones quedan en auditoría. Los cambios directos
de un administrador desde SQL Editor no pasan automáticamente por ese historial.
