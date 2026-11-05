# Boletas e inscripciones vigentes

La boleta de un periodo incluye únicamente sus inscripciones activas. Antes,
la vista previa tomaba todas las filas del kardex del periodo, incluidas las
materias retiradas. Una inscripción agregada por error y después dada de baja
podía seguir apareciendo y bloquear la emisión por falta de calificación.

El kardex conserva las inscripciones retiradas y sus calificaciones históricas.
Las boletas ya emitidas conservan su copia original: una corrección de matrícula,
nombre, inscripción o calificación exige revisar y emitir una nueva boleta cuando
corresponda; esta actualización no reescribe documentos históricos.

Aplicar en SQL Editor la migración repetible
`supabase/migrations/20261105000000_report_card_current_enrollments.sql`.
Funciona con la extensión anterior de boletas instalada o sin ella, siempre que
el kardex y las etapas ya existan. No hace falta volver a ejecutar la migración
antigua de boletas. La nueva migración no cambia notas ni reglas de los programas.
Publicar también `portal/report-cards.js` para actualizar el borrador que se usa
cuando las funciones de boletas aún no están disponibles.

Las actualizaciones nominales de matrículas, cursos e inscripciones son paquetes
privados separados. No deben subirse al repositorio ni contenerse en este documento.
Una revisión de datos no prueba que se hayan aplicado: se requiere la lectura
posterior a la transacción. Estar inscrito correctamente tampoco garantiza que
la boleta esté lista; aún se necesitan las calificaciones finales publicadas,
la matrícula, el semestre y los nombres de los firmantes.

Validación local, sin acceso a producción:

```bash
python3 supabase/tests/run_current_reports_local.py
python3 supabase/tests/run_current_reports_local.py --sin-extension-anterior
python3 tests/portal_report_current_enrollments.py
```
