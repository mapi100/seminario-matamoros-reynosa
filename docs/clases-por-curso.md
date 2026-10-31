# Clases por curso formativo y carga inicial 2026–2027

Esta entrega parte de `e43c3c4`. Añade la clasificación de cada clase por curso:
CI-1/CI-2, 1F-1 a 3F-6 y 1T-1 a 4T-8. CI identifica Introductorio, F Filosofía y
T Teología; el último número es el semestre y el primer número en F/T es el año.
No son claves únicas de materia: varias asignaturas pertenecen al mismo curso.

Las tarjetas, la cabecera del aula y el listado de Clases muestran el curso junto
a la materia y al periodo. Los códigos internos se conservan para las relaciones,
la selección de clase y las portadas. Al crear materias se puede dejar la referencia
interna vacía: se genera automáticamente. En el catálogo queda dentro de un detalle
de referencia; no se pide como dato obligatorio de operación escolar.

## Instalar el portal

1. Ejecutar una vez en Supabase → SQL Editor, con el rol administrador:
   `supabase/migrations/20261031000000_course_formation_groups.sql`.
   Requiere el campus/aula y catálogos existentes. No necesita ejecutar de nuevo
   las migraciones anteriores ni las funciones temporales del alta de alumnos.
2. Copiar los archivos del paquete del portal respetando sus rutas. Revisar los
   cambios y publicar en el repositorio/Pages con el procedimiento habitual.
3. Recargar con Ctrl+F5. Control Escolar dispone de **Clases → Curso / semestre**.
   Puede asignar o cambiar el curso; la operación no cambia las etapas de alumnos,
   sus notas, programas de kardex, profesores asignados o inscripciones.

No se ejecutó esta migración en producción desde la sesión de desarrollo.

## Carga privada del Excel

El paquete separado de carga contiene `02_cargar_clases_2026_2027.sql`,
`clases-revisadas.csv` y un manifiesto del origen. **No se copia al repositorio:**
contiene nombres docentes del Excel. El SQL se abre como texto y se ejecuta en
SQL Editor después de instalar la migración anterior. No usa una clave privada
ni modifica Authentication.

Se prepararon **134 clases**:

| Curso | Ago–Dic 2026 | Ene–May 2027 |
| --- | ---: | ---: |
| Introductorio | CI-1: 8 | CI-2: 8 |
| Filosofía, primero | 1F-1: 9 | 1F-2: 8 |
| Filosofía, segundo | 2F-3: 9 | 2F-4: 9 |
| Filosofía, tercero | 3F-5: 10 | 3F-6: 7 |
| Teología, primero | 1T-1: 9 | 1T-2: 9 |
| Teología, segundo | 2T-3: 9 | 2T-4: 10 |
| Teología, tercero / cíclico III | 3T-5: 9 | Sin listado en el archivo |
| Teología, cuarto | 4T-7: 10 | 4T-8: 10 |
| Total | 73 | 61 |

Fuente principal: hoja del plan global, ambos semestres (64 + 61 registros).
Se añaden las nueve materias de `(ciclico III)` para 3T-5. Se excluyen la hoja
histórica 2025–2026, `Hoja3` sin curso identificable y los bloques de estudio o
biblioteca del horario diario. No se inventan materias de 3T-6.

Hay diferencias entre nombres/docentes del horario diario y del plan; para esta
carga se eligió el plan global como fuente principal, y la hoja cíclica para el
curso adicional. El CSV permite revisar cada fila y su procedencia antes de ejecutar.
No se usa el horario diario para sobrescribir esas asignaturas o profesores.

### Fechas de periodos

Se autorizó usar **1 de enero–31 de mayo de 2027**. Para agosto–diciembre de 2026,
se reutiliza el periodo existente. Si no existe, el script propone **1 de agosto–31
de diciembre de 2026** como límites del periodo. Son referencias del calendario
académico, no una afirmación de días lectivos, festivos o fechas de exámenes.

Se buscan periodos con el nombre previsto o con inicio y final dentro de los
meses correspondientes. Si hay un único candidato se conserva, con sus fechas.
No se cambian periodos existentes por estas fechas de referencia. Si hay varios
candidatos, se aborta la transacción para resolver la ambigüedad.

### Conservación y repetición

- Reutiliza las materias por nombre normalizado (espacios, mayúsculas y acentos).
  Si hay varios candidatos con el mismo nombre, aborta; no los fusiona.
- Las variantes sustanciales de nombre no se adivinan ni se renombran. Una materia
  antigua llamada «Formación Humana» no se interpreta silenciosamente como «I».
  Revisar variantes si el catálogo contiene capturas anteriores aproximadas.
- Reutiliza la clase de la misma materia/periodo y conserva su estado, contenidos,
  notas e inscripciones. No reactiva bajas o clases inactivas.
- Inserta la clasificación de curso solo cuando no existe; conserva los cambios
  manuales de la metadata. Una clasificación incompatible provoca rollback.
- La carga completa es transaccional. Repetirla sin conflictos no duplica materias,
  clases o periodos. El resumen final identifica clases creadas y conservadas.
- Conserva docente previsto y el número de horas clase/bloques semanales del Excel
  como referencia para Control Escolar. No convierte esa cifra a créditos ni
  implementa el horario semanal de días/horas.
- **No crea cuentas docentes, asignaciones o inscripciones automáticas.** Asignar
  los profesores desde Clases; los nombres del Excel no bastan para identificar
  inequívocamente sus cuentas Auth. Asignar alumnos cuando se conozca su curso.

## Permisos y límites técnicos

`course_formation_groups` es una tabla privada con RLS y FK al curso, borrada en
cascada solo cuando se elimina esa clase. Las RPC:

- `portal_course_groups_read`: perfil activo; alumno/docente solo clases permitidas,
  Control Escolar también clases archivadas. Los nombres docentes previstos se
  devuelven solo a Control Escolar.
- `portal_course_classes_read`: listado administrativo paginado, búsqueda por
  curso/materia/periodo y conteo de docentes incluyendo Control Escolar docente.
- `portal_course_group_save`: Control Escolar activo; valida cursos y revisión,
  serializa con el bloqueo académico y registra el cambio en Actividad.

Las relaciones y código original de materia no se reemplazan con CI-1. El modelo
sigue siendo una clase por materia/periodo: no añade grupos paralelos. La etapa del
alumno y los programas/planes de kardex conservan sus propios registros.

La clasificación se guarda en Supabase, no en un arreglo fijo por clase. El módulo
JS vuelve a consultarla al verificar la sesión y limpia su caché al salir. Los
cambios tardíos de otra sesión no se aplican a la actual. Un resultado incierto de
guardado requiere cerrar/actualizar antes de reintentar; no se reenvía automáticamente.

## Verificación

Sin datos reales ni conexión a producción:

```bash
python3 supabase/tests/run_course_groups_local.py --import-sql /ruta/privada/02_cargar_clases_2026_2027.sql
python3 tests/portal_course_groups.py
python3 tests/portal_subjects.py
python3 tests/portal_workspace.py
```

SQL: PostgreSQL 17 en Docker sin red. Navegador: Playwright/Chromium, SDK fijado y
API simulada. La prueba de importación requiere el SQL privado entregado aparte;
no versiona el Excel ni su contenido docente. Se verificaron 134 clases, repetición,
notas previas, permisos, búsqueda, edición concurrente y presentación móvil.
