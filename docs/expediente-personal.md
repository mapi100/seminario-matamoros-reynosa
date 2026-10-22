# Expediente personal del seminarista

Cada alumno puede completar sus datos desde **Mi perfil → Mis datos personales**.
El inicio ofrece también **Completar mis datos personales**. La captura se divide
en seis secciones con botones Anterior, Siguiente sección y Guardar mis datos.
Se puede guardar por partes; no es necesario conocer todos los datos para empezar.

## Datos disponibles

| Sección | Datos |
| --- | --- |
| Identificación | Nombre completo, CURP, nacimiento, edad calculada, país, estado y municipio de nacimiento y nacionalidad |
| Contacto | Teléfono personal, teléfono alternativo y correo de contacto adicional; el correo de acceso se muestra como referencia |
| Domicilio | Calle, números exterior e interior, colonia, código postal, municipio, estado y país |
| Familia y emergencias | Persona de contacto, relación y teléfono; nombres y teléfonos de madre y padre opcionales |
| Formación previa | Diócesis y parroquia de origen, escuela de procedencia, nivel, certificado o título y año de egreso |
| Datos escolares | Matrícula, ingreso, egreso, número de inscripciones y programas/planes vinculados; se consultan sin editarlos |

Solo el nombre es obligatorio para guardar; ya viene del perfil existente. Los
demás campos pueden quedar pendientes. La barra de avance muestra nueve datos
básicos sugeridos que ya están guardados y detalla los que faltan. No representa
una certificación de expediente completo ante la SEP. Los campos familiares y
otros datos opcionales no son requisitos para acceder a los cursos.

La edad se calcula con el nacimiento y la fecha actual de Matamoros. No se guarda
un número de edad que después quede desactualizado. La CURP se convierte a
mayúsculas y se comprueba su estructura y su fecha contra el nacimiento, cuando
ambos están presentes. Esto **no consulta ni valida la identidad ante RENAPO**.
No se infiere el siglo o el nacimiento a partir de una CURP incompleta.

## Vinculación con el portal y el kardex

El expediente pertenece al mismo identificador del usuario de Supabase Auth;
no crea otra persona ni otra cuenta. El nombre se guarda en `profiles`, y la
CURP y el nacimiento usan los campos existentes de `kardex_students`.

- Un cambio de nombre llega a las listas académicas y al kardex vivo. El alumno
  ve su nombre actualizado en el encabezado al guardar.
- Las inscripciones, clases y calificaciones siguen relacionadas con el mismo
  usuario. No se copian ni se reasignan por cambiar sus datos personales.
- Los cambios de CURP o nacimiento hechos desde Kardex también aparecen en el
  expediente personal. Los formularios anteriores detectan las revisiones para
  evitar sobrescribir los cambios de otra persona.
- Los kardex **ya emitidos** conservan la copia original. Para reflejar datos
  corregidos se revisa la vista previa y se emite un nuevo documento.
- El correo de contacto no cambia el correo de acceso, la contraseña, el rol o
  el estado de la cuenta. Tampoco crea un buzón institucional.
- Matrícula, fechas escolares, programas, inscripciones y calificaciones siguen
  bajo la administración de Control Escolar y los docentes autorizados.

## Consulta y revisión de Control Escolar

Control Escolar tiene el apartado **Expedientes** para buscar por nombre,
matrícula o CURP. También puede abrir **Personas → Expediente personal** o
**Kardex → Expediente personal** para el alumno seleccionado. Desde los datos
escolares del expediente hay un botón para volver al kardex de ese mismo alumno.

Control Escolar puede corregir los datos y pulsar **Marcar como revisado**.
Primero hay que guardar las modificaciones del formulario. Se registra quién
revisó los datos y cuándo. La revisión es interna y puede referirse a una captura
parcial; es independiente del indicador de datos pendientes y del reconocimiento
académico del programa.

Si después cambia el nombre, CURP, nacimiento u otro dato personal, el expediente
vuelve a figurar **Pendiente de revisión**. Esto incluye los cambios realizados
desde Personas y Kardex, no solo los del propio formulario. Una modificación de
matrícula o una inscripción nueva no se presenta como un cambio de datos personales.
Los alumnos inactivos siguen disponibles para consulta y corrección de Control
Escolar; su propio acceso permanece bloqueado.

## Permisos y guardado

El alumno activo solo puede leer y actualizar su propio expediente. Control
Escolar activo puede consultar y actualizar los expedientes; los profesores no
reciben acceso a CURP, domicilio, teléfonos ni contactos familiares mediante este
módulo. Tener una asignación docente no concede ese permiso. PostgreSQL comprueba
el usuario y su rol real en cada operación, sin confiar en la URL o `user_metadata`.

La tabla nueva tiene RLS y carece de permisos directos para el navegador. Las
funciones aceptan una lista cerrada de campos personales y rechazan intentos de
cambiar roles, edad, correos de acceso, matrícula, calificaciones o datos de
revisión. El historial general registra la acción y el usuario, sin copiar CURP,
domicilio ni teléfonos a los detalles de auditoría.

Los cambios de formulario sin guardar se conservan únicamente en memoria al
cambiar de pestaña mientras se vuelve a verificar la misma cuenta. Se retiran
los campos de la pantalla mientras el portal está oculto. No se guardan datos
personales ni borradores en `localStorage`. Un cambio de cuenta o de rol, la baja
del usuario y el cierre de sesión descartan el borrador. Al recargar o cerrar la
página el navegador advierte si quedan cambios sin guardar; hay que usar Guardar
mis datos para conservarlos en Supabase.

Si otra persona modificó el expediente, el formulario conserva lo escrito y
solicita actualizar antes de sobrescribir. Si se pierde la respuesta de un
guardado, no se reenvía automáticamente: **Actualizar datos** permite comprobar
lo que quedó registrado. El usuario confirma si desea descartar campos sin
guardar al salir o actualizar.

## Instalar la actualización

Esta actualización parte de la versión que ya incluye el kardex.

1. En una copia del proyecto sin un rebase pendiente, sincroniza primero con
   `git pull --rebase origin main`. Si aparece un conflicto, resuélvelo antes de
   copiar los archivos nuevos. No ejecutes otro pull durante un rebase pendiente.
2. Extrae el paquete y copia **su contenido sobre la raíz del proyecto**,
   combinando carpetas y reemplazando archivos del mismo nombre.
3. En Supabase → **SQL Editor**, ejecuta completo **una sola vez**
   `supabase/migrations/20261022030000_student_personal_record.sql`.
   Debe ir después de `20261022020000_kardex.sql`. No vuelvas a ejecutar las
   migraciones anteriores. No crea alumnos, datos ficticios ni cuentas.
4. Desde PowerShell, dentro de la raíz del proyecto:

   ```powershell
   git add README.md portal docs supabase tests
   git commit -m "Agregar expediente personal del seminarista"
   git push origin main
   ```

5. Espera a que termine GitHub Pages y recarga con **Ctrl + F5**. Prueba primero
   con una cuenta de alumno y después con Control Escolar.

Subir los archivos a GitHub no ejecuta la migración en Supabase. El módulo no
necesita otro servicio de pago ni modifica la configuración del correo.

## Pruebas locales

```bash
python3 supabase/tests/run_personal_record_local.py
PORTAL_TEST_ARTIFACTS=/tmp/expediente-pruebas python3 tests/portal_personal_record.py
```

Usan identidades ficticias: PostgreSQL desechable sin red mediante Docker y
Chromium con Playwright y una API simulada. No usan credenciales ni registros
del proyecto de producción. Comprueban permisos, validaciones, sincronización,
revisiones, edad, borradores, concurrencia y navegación en escritorio y celular.
