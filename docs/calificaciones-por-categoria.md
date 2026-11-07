# Calificaciones por categoría, sin crear actividades

Preparado el 7 de noviembre de 2026. Probado localmente con datos ficticios; pendiente de instalar en Supabase y publicar los archivos del portal.

## Instalación

1. En Supabase → SQL Editor, ejecuta completo `supabase/migrations/20261107000000_category_grade_entry.sql`. Se puede repetir. Instalarlo no cambia notas, profesores, actividades ni boletas existentes.
2. Copia los archivos de esta actualización en las mismas rutas de tu repositorio, conservando el resto. Publica los cambios como de costumbre.
3. Recarga el portal e inicia sesión con una cuenta de profesor. No necesitas Python ni nuevas claves.

Requiere el aula virtual y las ponderaciones existentes. No es necesario reinstalar las migraciones antiguas ni asignar roles nuevos a los profesores.

## Uso del profesor

**Mis cursos → materia → Calificaciones → Configurar evaluación.**

1. Reparte el **100 %** entre Tareas, Exámenes, Proyectos y Participación. Una categoría en **0 %** no tendrá casilla para calificar ni contará en la final. No se exige crear actividades, proyectos o entregas digitales.
2. Confirma y guarda los porcentajes. Se configuran una sola vez por clase y periodo. Para modificarlos después de publicarlos, se solicita explicar el cambio.
3. En la tabla, escribe una nota de **0 a 10**, con un decimal, por alumno y categoría que cuente. La **Final calculada** se actualiza al completar las categorías requeridas.
4. Puedes **Guardar borrador** para continuar después. El alumno, la final publicada y las boletas conservan sus valores anteriores.
5. Al terminar, pulsa **Revisar y publicar finales**. Selecciona los alumnos completos. Puedes indicar una **Final ajustada** para cada uno y escribir el motivo del ajuste o de la corrección. Confirma la publicación.

Ejemplo: Tareas 30 %, Exámenes 50 %, Proyectos 0 %, Participación 20 %. Con notas de 8, 9 y 10, la final calculada es **8.9**. El profesor puede publicar **9.5** como ajuste, registrando su motivo. Se conserva tanto el cálculo original como el valor publicado y el responsable.

Una casilla vacía significa **pendiente**, no cero. Un **0** sí es una calificación. La final no se calcula con un promedio parcial ni se publica mientras falte una categoría que cuente. Los alumnos incompletos quedan sin seleccionar en la revisión; los completos pueden publicarse juntos.

El ajuste manual se introduce en la revisión final, no en las casillas de categorías. No se necesita alterar las notas de Tareas o Exámenes para conceder ese ajuste.

## Cursos que ya utilizaban actividades

Los cursos sin criterios publicados abren la captura simple, aunque ya tengan actividades o un borrador de porcentajes. Esos registros se conservan.

Los cursos que ya tienen criterios publicados por actividades conservan su método. Para pasar a captura simple, pulsa **Una nota por categoría** en el libro, revisa los porcentajes y confirma el cambio con su motivo. Las actividades y sus notas no se borran; dejan de intervenir en el cálculo de ese modo. Las finales y boletas ya emitidas no cambian al configurar.

En **Más opciones → Evaluar mediante actividades** se puede volver al configurador anterior. Es necesario revisar, guardar y publicar esa configuración para cambiar de método. Las notas por categoría se conservan, pero no intervienen en el cálculo por actividades.

## Permisos y conservación de datos

- Un profesor solo lee y modifica sus clases activas asignadas. Control Escolar mantiene su acceso por rol. No se modifica ninguna cuenta ni se crean asignaciones nuevas.
- Los borradores de categorías son privados para el personal autorizado. El alumno consulta las categorías publicadas y la final publicada, distinguiendo ambas si hubo un ajuste.
- Categorías y finales seleccionadas se publican en una sola transacción. Un error revierte todo el lote. Se reutiliza el mecanismo existente de finales, auditoría e historial para que las boletas y kardex reciban la nota final correcta.
- Cambiar los porcentajes o capturar borradores no reescribe finales publicadas ni documentos emitidos. Para reflejar una corrección se revisa y publica de nuevo; una boleta anterior conserva su copia.
- Si otra persona cambió datos durante la captura, se exige actualizar. Una respuesta incierta no se reenvía automáticamente; cierra y pulsa Actualizar libro antes de seguir.
- El contrato interno conserva la escala 0–100; la interfaz muestra 0–10. No se dividen calificaciones históricas ni se crean actividades artificiales.

## Comprobaciones

Pruebas en PostgreSQL desechable sin red y navegador con SDK real/API simulada, sin claves ni datos de producción. Se comprueban permisos, criterios sin actividades, pesos en 0 %, notas pendientes y ceros, borradores privados, cálculo ponderado, ajustes con motivo, publicación atómica, datos concurrentes, revocación, conservación de actividades y reinstalación. También se verifica el flujo previo por actividades y el de Control Escolar, además de pantallas Claro/Oscuro/OLED y móvil.

```sh
python3 supabase/tests/run_category_grades_local.py
python3 tests/portal_category_grades.py
python3 supabase/tests/run_weighted_grades_local.py
python3 tests/portal_weighted_grades.py
python3 tests/portal_learning.py
python3 supabase/tests/run_school_workflow_local.py
```
