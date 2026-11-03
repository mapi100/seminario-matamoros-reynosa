# Boletín público y archivos personales del seminarista

Esta actualización conserva Supabase como backend. No incluye la propuesta de
servidor doméstico, AGENTS.md de infraestructura ni cambios de alojamiento/DNS.

## Instalación

1. Copiar los archivos de la actualización sobre el repositorio manteniendo carpetas.
2. Ejecutar **una sola vez** en Supabase SQL Editor:
   `supabase/migrations/20261103000000_student_personal_files.sql`.
   Requiere las tablas y funciones del expediente personal ya instaladas, además de
   Supabase Storage. No es necesario repetir las migraciones anteriores.
3. Publicar mediante el procedimiento habitual de GitHub Pages y recargar con Ctrl+F5.
4. Comprobar con cuentas propias de ensayo: alumno sube/descarga; Control Escolar abre
   ese expediente y descarga/sube; otro alumno y un profesor no pueden acceder.

La migración crea una tabla, un bucket privado, políticas específicas y funciones.
No carga documentos, no modifica expedientes existentes ni vuelve públicos los otros
buckets. No cambia la suscripción de Supabase y no se ejecutó en producción desde
esta sesión. No pegar claves service_role en el navegador ni en GitHub.

## Boletín en la página pública

El enlace **Boletín** aparece inmediatamente antes de **Portal Escolar**, con fondo
`--gold` y texto `--blue-dark`, coherentes con la paleta institucional. Abre en otra
pestaña con `noopener noreferrer` y etiqueta accesible. Se adapta al encabezado móvil.

Destino proporcionado por el administrador:

<https://heyzine.com/flip-book/7a5456d5db.html#page/1>

Es un enlace directo: no descarga ni incrusta el flipbook al abrir el sitio público.
No se copiará contenido de Heyzine al repositorio. Las verificaciones locales comprueban
URL, posición, apariencia y dimensiones; no acreditan disponibilidad del servicio externo.

## Uso de Archivos

### Alumno

En **Mi perfil → Mis datos personales → Archivos**:

1. Seleccionar el tipo de documento.
2. Elegir uno o varios PDF del equipo y pulsar **Subir PDF**. Todos los seleccionados
   en ese envío recibirán el tipo elegido.
3. Descargar desde el apartado correspondiente cuando aparezcan guardados.
4. Para corregir un archivo equivocado, pulsar **Quitar archivo** y confirmar.

### Control Escolar

En **Expedientes → buscar alumno → Abrir expediente → Archivos** dispone de las
mismas funciones. Puede subir documentos en nombre del seminarista y descargar los
que haya subido el propio alumno. El alumno puede descargar los que cargó Control.
No se confunde al propietario del expediente con el usuario que realizó la subida.

Los profesores no tienen acceso a estos archivos, aunque impartan clases al alumno.
Un alumno no puede consultar los de otro. Una cuenta inactiva pierde acceso; Control
Escolar activo conserva acceso a expedientes históricos autorizados por el sistema.

### Apartados y límites

| Apartado | Tipos |
| --- | --- |
| Sacramentos | Bautismo, primera comunión, confirmación, otro documento sacramental |
| Formación previa | Certificado de preparatoria, título universitario, otro certificado de estudios |
| Seguro médico | Constancia o póliza de seguro médico |
| Otros documentos | Otro documento personal en PDF |

Se permiten **hasta 10 PDF en total por seminarista**, no diez por apartado, y
**5 MiB por archivo** (5 × 1024 × 1024 bytes; la interfaz usa la etiqueta «5 MB»).
Los documentos son opcionales; no se inventan datos ni se exige un título universitario.

El botón **Archivos** es una sección adicional del mismo perfil. Se conservan
Identificación, Contacto, Domicilio, Familia y emergencias, Formación previa y Datos
escolares. La formación previa del formulario sigue guardando datos de texto; la
subsección con ese nombre dentro de Archivos guarda sus PDF.

La carga de archivos es independiente de **Guardar mis datos**. No modifica los nueve
datos básicos usados por el indicador de avance ni la marca de revisión de esos datos.
Un borrador del formulario no se pierde al subir PDF. No se publica ningún archivo en
la web abierta ni se incluyen archivos del alumno en GitHub/localStorage.

## Privacidad, persistencia y API

- Bucket privado nuevo: `portal-personal`, solo `application/pdf`, tamaño máximo 5 MiB.
- Tabla `public.student_record_files` con RLS y sin acceso directo para anon/authenticated.
  Guarda estudiante, tipo, nombre, tamaño, estado, autor, fecha y ruta aleatoria.
- Ruta: `<student_uuid>/<file_uuid>.pdf`. No incorpora nombres personales ni usa como
  ruta el nombre proporcionado por el navegador.
- `portal_student_files(p_action,p_student,p_data)` valida al usuario con el perfil
  activo y `_student_record_target`. Roles, límites y permisos se validan en PostgreSQL.
  Las acciones son `list`, `reserve`, `complete`, `remove` y `release`.
- `_student_file_authorized(path,action)` concede solo una comprobación booleana para
  las políticas de Storage. La inserción necesita una reserva del mismo autor y ruta;
  la lectura queda limitada al alumno del expediente y a Control Escolar autorizado.
- Las políticas restrictivas del bucket impiden que una política permisiva genérica
  preexistente abra estos documentos a otros usuarios o permita sobrescribirlos.
  Solo restringen `portal-personal`; no alteran las reglas de los buckets anteriores.
- No se permite UPDATE de objetos personales: la aplicación no sobrescribe archivos
  con upsert. Se corrigen retirándolos de forma explícita y subiendo un nuevo PDF.
- La descarga usa Storage con la sesión autenticada y RLS, luego un blob temporal para
  descargar. No se crean enlaces públicos ni URL firmadas persistentes. El blob se
  libera tras la descarga o al limpiar la sesión.
- No se incorpora un visor de PDF ni se descargan documentos al entrar al perfil. La
  consulta de la lista se inicia al abrir Archivos. Solo se descarga el PDF solicitado.
- La interfaz comprueba extensión, tamaño y cabecera PDF. El bucket y el registro
  comprueban tipo/tamaño de metadatos; esto no constituye análisis antivirus ni una
  validación completa de la estructura binaria del PDF.
- Auditoría: `student_file_uploaded` y `student_file_removed`, por ID de expediente,
  ID de archivo y tipo. No se copia el contenido, el nombre del documento ni datos
  médicos a los detalles genéricos de auditoría.

### Cargas y eliminaciones interrumpidas

Una operación entre PostgreSQL y el servicio Storage no es una única transacción.
Por ello cada documento sigue un protocolo recuperable:

1. `reserve` reserva el lugar y asigna una ruta, en estado `pending`. Las reservas
   pendientes también cuentan para el límite de diez.
2. El cliente sube a Storage con `upsert:false`; RLS exige la reserva correspondiente.
3. `complete` verifica que existe el objeto, que su autor coincide y que tamaño/MIME
   concuerdan con la reserva; lo pasa a `ready`. Es idempotente para ese mismo autor.
4. Para quitarlo, el usuario confirma y `remove` cambia el estado a `deleting`.
5. Storage elimina el objeto. `release` solo libera el registro/lugar cuando el objeto
   ya no existe. Las reservas en eliminación no admiten nuevas subidas.

Las mutaciones de la RPC se serializan con el bloqueo administrativo existente. Dos
cargas concurrentes, incluso desde alumno y Control Escolar, no pueden reservar un
undécimo lugar. No se autoriza subir a rutas arbitrarias ni dejar objetos sin reserva.

Si la conexión se corta, la interfaz no reenvía escrituras automáticamente. Pulsar
**Actualizar archivos** para comprobar el estado real. Las cargas sin confirmar muestran
**Limpiar carga incompleta**; las retiradas interrumpidas muestran **Completar eliminación**.
Si una carga se confirmó pero se perdió la respuesta, aparecerá como descargable al
actualizar, sin duplicarla. Las reservas sin confirmación pueden limpiarse y volver a
subirse; no se borran automáticamente los archivos que sí quedaron guardados.

Al salir/cambiar de cuenta se limpian listas, solicitudes y blobs temporales; una
respuesta tardía no restaura documentos de otro expediente. Cambiar de alumno o
recargar el expediente se bloquea mientras hay una operación de archivos en curso.

## Almacenamiento y copias

Los PDF consumen el almacenamiento del proyecto Supabase junto con tareas y materiales.
El límite por alumno no es una cuota adicional contratada: 40 alumnos con diez PDF
al máximo de 5 MiB ocuparían hasta 2000 MiB solo en documentos personales. El uso real
depende del tamaño de los PDF y debe vigilarse según el plan contratado.

Las copias de la base de datos conservan registros/metadatos, pero los bytes de
Storage requieren su propia copia privada. No usar un repositorio público como backup
de boletas sacramentales, certificados o seguro médico.

## Verificación local

```bash
python3 supabase/tests/run_personal_files_local.py
python3 tests/portal_personal_files.py
python3 tests/portal_personal_record.py
```

PostgreSQL usa Docker desechable sin red y datos ficticios. Verifica RLS/roles,
reservas, metadatos, cuotas/concurrencia, descargas, retiradas y auditoría; no valida el
transporte HTTP real de Supabase Storage. El navegador utiliza el SDK real con API
simulada para probar alumno/Control, cargas múltiples, descargas, errores, limpieza,
borradores, cierre de sesión, accesibilidad y los tres temas en móvil.

El encabezado público se comprobó entre 320 y 1600 píxeles, incluyendo que Boletín
preceda a Portal Escolar y no se superponga con la marca. Antes de entregar a todos,
comprobar los flujos completos con cuentas de ensayo en el proyecto Supabase real.
