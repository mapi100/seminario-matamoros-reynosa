# Control Escolar: cursos, finales y boletas por grupo

Actualización del 5 de noviembre de 2026. Preparada y probada localmente; requiere instalar el SQL y publicar los archivos del portal. No se ejecutó contra Supabase de producción.

## Instalación

1. En **Supabase → SQL Editor**, ejecuta completo `supabase/migrations/20261105010000_control_school_workflow.sql`. Instálalo en el proyecto habitual del Seminario. Es transaccional y se puede repetir; instalarlo no publica notas, emite boletas ni cambia profesores.
2. Copia los archivos de esta actualización en las mismas rutas de tu repositorio, conservando el resto. Publica los cambios en GitHub como de costumbre. Se incluyen nuevos recursos en `portal/vendor/jspdf/`; también deben subirse.
3. Vuelve a entrar al portal con una cuenta activa de Control Escolar y recarga la página. No necesitas ejecutar Python, crear cuentas, introducir claves nuevas ni asignarte materia por materia.

Requiere las actualizaciones existentes de aula virtual, ponderaciones, organización por curso y boletas. Incluye la actualización de boletas vigentes `20261105000000_report_card_current_enrollments.sql` instalada antes de esta entrega. Si aparece un mensaje sobre dependencias faltantes, conserva el error para revisar el esquema; no vuelvas a ejecutar todas las migraciones antiguas.

## Entrar a cualquier materia

**Mis cursos → periodo académico → bloque (CI-1, 1F-1, etc.) → Entrar al curso.**

El rol activo de Control Escolar permite administrar todas las clases activas, incluidas las que se creen después. Los bloques tienen el mismo funcionamiento que en Clases. Puedes buscar una materia dentro del bloque, cambiar de periodo o ver todas las clases.

La autorización procede del perfil en la base de datos. No se crean asignaciones docentes para cada persona de Control Escolar: los profesores reales siguen siendo los titulares. Los alumnos y profesores conservan sus vistas y permisos habituales. Las clases inactivas se pueden consultar en el listado, pero deben reactivarse para administrarlas.

## Capturar finales por el profesor

1. En una materia de **Mis cursos**, pulsa **Capturar finales**.
2. Escribe las notas de los seminaristas en **Final a publicar**, en escala **0 a 10**, con un decimal. Se muestra la final que ya estaba publicada para comparar. Dejar el campo vacío conserva la nota actual.
3. Revisa el motivo de la captura; si corriges una nota, explica la razón.
4. Pulsa **Revisar y publicar finales**. Comprueba la lista de cambios, marca la confirmación y publica.

Se guardan todas las notas confirmadas en una sola operación. La final publicada queda disponible para el alumno, su historial y la boleta. Las tareas y ponderaciones se conservan; no es necesario reconstruir las actividades cuando el docente entrega su nota final fuera del portal. La auditoría identifica al usuario de Control Escolar que publicó o corrigió cada nota.

La escala interna continúa siendo 0–100; el portal convierte 9.4 a 94, igual que las otras pantallas. Las notas históricas no se dividen ni se redondean si no se modifican.

Si otra persona cambia las notas o la lista de alumnos antes de confirmar, se exige actualizar y revisar de nuevo. Si se pierde la respuesta al guardar, **Cerrar y actualizar** comprueba el estado; no se reenvía a ciegas.

## Descargar todas las boletas de un curso

**Mis cursos o Clases → periodo → bloque → Boletas del curso (ZIP).** También está en el bloque de **Etapas y semestres**. En **Boletas y kardex**, el enlace **Boletas por curso (ZIP)** lleva a esa sección.

1. Comprueba el periodo, el bloque y los nombres.
2. La revisión distingue **listas para emitir**, **emitidas y actualizadas** y **pendientes**.
3. Si hay emisiones nuevas, revisa notas, matrículas y firmantes y marca la confirmación.
4. Pulsa **Emitir listas y descargar ZIP** o **Descargar ZIP**.

El ZIP incluye un PDF de **una página tamaño carta por seminarista**, con su nombre, matrícula y folio en el nombre del archivo. Conserva escudo, materias, calificaciones, firmas y el pie con folio, fecha, escala y mínima aprobatoria. No incluye los encabezados de fecha/URL añadidos por el navegador al imprimir. `LEEME_DEL_LOTE.txt` indica qué contiene y detalla las pendientes.

El grupo se obtiene de la etapa/semestre registrada para ese periodo y sus inscripciones activas. No se deduce por edad ni por el nombre del correo. Una inscripción en materias de otro bloque se marca pendiente para revisar antes de emitir. Tampoco se inventan notas ni se incluyen boletas incompletas. Un alumno con una final reprobatoria publicada sí puede tener una boleta completa. El historial permite consultar alumnos dados de baja que conservaron inscripciones activas en ese periodo.

La descarga reutiliza las boletas ya emitidas cuyo contenido coincide con el actual. Si cambió una calificación, matrícula o firmante, la revisión solicita emitir una copia nueva para el alumno afectado; las boletas anteriores permanecen intactas. Los reintentos de la misma descarga conservan el lote y sus folios. Después de un conflicto, usa **Actualizar revisión** para revisar la versión nueva.

Los PDF se preparan en el navegador, sin guardarse en Supabase Storage ni enviar expedientes a otro servicio. Solo se cargan los recursos de generación cuando se descarga un ZIP por primera vez. La base conserva las emisiones y los identificadores del lote. La generación comprueba el permiso de Control Escolar de nuevo antes de entregar el ZIP.

## Notas técnicas y validación

- Nuevo SQL: dos RPC de lectura/publicación final y dos RPC de revisión/emisión por grupo; ayudantes y tabla de lotes privados con RLS, sin acceso directo desde el navegador.
- Bloqueo académico compartido con las operaciones existentes, revisión optimista y publicación/emisión transaccional. Las solicitudes de lote llevan un UUID para evitar duplicados después de una respuesta perdida.
- Generación local mediante jsPDF 4.2.1 (MIT), con fuentes Liberation Sans (SIL OFL) y escudo locales. Recursos cargados al exportar: unos 810 KiB sin compresión HTTP, compartidos por todas las boletas. Funciona con el mecanismo de archivos locales existente sin solicitar fuentes mediante `fetch(file://)`.
- Límites por operación: 500 finales o 200 boletas por grupo, ZIP de hasta 64 MB. No se limitan las listas de cursos a las primeras 20/30/50 materias.
- Pruebas sin datos personales reales ni conexión a producción: PostgreSQL desechable, navegador con SDK real y API simulada, ZIP abierto con comprobación CRC y PDFs inspeccionados con Poppler. Se verifican permisos, notas inválidas, concurrencia, auditoría, conservación de emisiones, reintentos, revocación de acceso, cursos futuros, móvil y OLED.

Comandos de verificación:

```sh
python3 supabase/tests/run_school_workflow_local.py
python3 tests/portal_school_workflow.py
python3 tests/portal_report_zip.py
python3 tests/portal_class_directory.py
python3 tests/portal_report_print.py
python3 tests/portal_learning.py
```

Se requieren Docker/PostgreSQL 17 para la primera prueba; Python con Playwright, Chromium y Poppler para las pruebas de navegador/PDF. Las pruebas no requieren claves de Supabase.
