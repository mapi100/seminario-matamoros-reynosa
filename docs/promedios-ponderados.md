# Promedios y evaluación por clase

## Instalar esta actualización

1. En Supabase → SQL Editor, ejecuta completo **una vez**
   `supabase/migrations/20261023010000_weighted_gradebook.sql`, después de la
   migración de etapas formativas `20261023000000_formation_stages.sql`.
   La instalación es transaccional. Si aparece un error, ejecuta `rollback;`
   y conserva el mensaje para revisarlo antes de repetir.
2. Copia los archivos del paquete respetando sus carpetas y publica los cambios
   del repositorio en GitHub Pages. Los SQL guardados en Git no se ejecutan solos.
3. Recarga el portal con Ctrl+F5. Entra a una clase → **Calificaciones**.

No se cambian calificaciones finales, tareas ni criterios de clases existentes.
Cada profesor debe clasificar sus actividades y publicar sus propios criterios.
Los cursos sin criterios muestran las notas publicadas, pero no inventan un
promedio. El editor anterior de notas finales funciona en esos cursos; cuando
se publican ponderaciones, las finales se revisan desde el libro del curso.

## Para el profesor

1. Usa **Nueva actividad** para crear tareas, exámenes, proyectos o participación.
   Un examen presencial o la participación pueden registrarse sin entrega de
   archivos; esto no crea un motor de cuestionarios o exámenes en línea.
2. Abre **Configurar evaluación**. Distribuye el 100 % entre las cuatro categorías.
   Una categoría que no utilices puede valer 0 %. Los valores iniciales son una
   sugerencia de borrador; no se publican automáticamente.
3. Clasifica cada actividad; **Clasificar pendientes como tareas** permite
   completar varias de una vez. Usa **Práctica (no cuenta)** para lo que no participa
   en la nota. Elige reparto **Por igual** o **Pesos diferentes** por categoría.
   Con pesos diferentes, los pesos internos de esa categoría deben sumar 100 %.
   Ejemplo: Exámenes vale 50 %; parcial 40 % y final 60 % de esa categoría aportan
   20 % y 30 % de toda la clase. La tabla muestra ambas cantidades.
4. **Guardar borrador** conserva el trabajo y vuelve a abrir la revisión.
   **Revisar y publicar criterios** pide confirmación. Una modificación de
   criterios ya publicados requiere motivo; no reemplaza las finales existentes.
5. Usa **Revisar / calificar** para ver la entrega, archivos, comentarios y nota.
   Puedes guardar un borrador o publicar. **Captura rápida** permite capturar
   muchas notas en la tabla, guardar borradores y publicarlos después sin
   volver a escribirlos. Cada lote de hasta 300 cambios se guarda completo o
   se rechaza completo; nunca queda una mitad aplicada.
6. Cuando todas las evaluaciones estén publicadas, abre **Revisar y publicar
   finales**, selecciona los alumnos y confirma. Se muestran los alumnos de la
   página actual, de 30 en 30. Un ajuste manual o una corrección de una nota
   final distinta requiere motivo de al menos 10 caracteres.

Una actividad nueva queda fuera del esquema publicado hasta clasificarla y
volver a publicar los criterios. El portal advierte al profesor e impide cerrar
finales con actividades sin clasificar. Cambiar el tipo en el formulario de una
actividad no cambia silenciosamente el esquema de evaluación publicado.

## Qué ve el alumno

- Promedio actual, calculado con notas de actividades publicadas.
- Porcentaje del peso total del curso que ya fue evaluado y publicado.
- Promedio de tareas, exámenes, proyectos y participación, y peso de cada una.
- Nota, aportación, estado y comentarios de sus actividades publicadas.
- Calificación final confirmada, separada del promedio actual.

Control Escolar ve el mismo libro y cálculo que el profesor, entrando desde
**Clases → Entrar al curso → Calificaciones**, incluso si no imparte esa clase.
El profesor solo tiene acceso a sus clases asignadas. Un alumno solo consulta
sus notas, nunca la lista del grupo, borradores o comentarios privados.

## Reglas de cálculo

Cada actividad recibe un peso efectivo en toda la clase: peso de categoría por
su proporción interna. Para el promedio actual:

`suma(nota publicada × peso efectivo) / suma(pesos efectivos ya evaluados)`

Ejemplo completo: tareas 72.50 × 30 %, exámenes 80 × 50 % y proyecto 90 × 20 %
producen **79.75 / 100**. Si únicamente se han calificado esas tareas, se muestra
**72.50 / 100, evaluado 30 % del curso**.

- Una nota pendiente no es cero. Una nota publicada de 0 sí cuenta.
- El vencimiento no aplica ceros ni penalizaciones automáticamente. El profesor
  puede **Registrar cero por no entregar** y confirmar el guardado/publicación.
- Las exenciones son por alumno y actividad, requieren motivo y son visibles
  al guardar. Redistribuyen el peso dentro de la misma categoría. No eliminan
  las notas anteriores. Quitar una exención requiere guardar una evaluación.
- Si se exentan todas las actividades de una categoría con peso, el cierre se
  bloquea: el profesor debe resolver sus criterios o evaluar otra actividad.
- Las notas de categorías con 0 % y las prácticas no alteran el promedio.
- Una actividad sin publicar no aporta una nota al promedio del alumno aunque
  tenga una calificación guardada. Si tiene peso, impide cerrar finales.
- Los cambios de notas todavía en borrador bloquean la publicación final.
- Se calcula con precisión numérica en PostgreSQL y se muestran hasta dos
  decimales; no se redondea cada aportación antes de sumar.
- El promedio y los créditos generales del kardex siguen sus propias reglas
  institucionales; las ponderaciones se aplican dentro de cada clase.

## Historial y comprobaciones

Publicar una final guarda una copia del esquema, cálculo, nombres de actividades,
nota confirmada, responsable y motivo. Actualiza la tabla de finales que ya
consumen el historial y el kardex. Los kardex ya emitidos conservan su copia.
Cambiar notas o porcentajes posteriormente recalcula el promedio actual, pero
la final se conserva hasta otra publicación explícita y auditada.

Las tablas nuevas son privadas con RLS; las RPC verifican en el servidor el
perfil activo, la clase y las inscripciones. Las escrituras se serializan con
el bloqueo de administración existente. Los tokens de revisión detectan cambios
de esquema, notas, exenciones y finales antes de guardar o publicar. El navegador
no guarda expedientes ni calificaciones en almacenamiento persistente.

Pruebas locales, sin credenciales reales:

```sh
python supabase/tests/run_weighted_grades_local.py
python tests/portal_weighted_grades.py
python supabase/tests/run_learning_local.py
python tests/portal_learning.py
python supabase/tests/run_kardex_local.py
```

Los runners SQL necesitan Docker con `postgres:17-bookworm`; los del navegador
requieren Python Playwright y Chromium. Las API del navegador se simulan; los
cálculos, permisos y transacciones se comprueban aparte en PostgreSQL real.
