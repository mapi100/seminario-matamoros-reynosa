# Boletas semestrales y escala institucional

Actualización local del 27 de octubre de 2026. No se ha desplegado ni ejecutado SQL contra producción. Los archivos SQL recuperados describen el esquema local reconstruido; no acreditan lo que está instalado en Supabase.

## Uso

1. Fusiona la carpeta `portal/` del ZIP con la carpeta del mismo nombre de tu repositorio local y reemplaza los archivos coincidentes. Conserva el resto del repositorio, incluidas las imágenes, los archivos de acceso local y la configuración pública de Supabase. No necesitas Python para abrirlo.
2. Abre el sitio como antes e inicia sesión con una cuenta activa de **Control Escolar**. En **Boletas y kardex**, busca al alumno y pulsa **Ver historial**.
3. En **Boleta semestral**, selecciona el periodo. Las materias y las notas finales publicadas se reúnen automáticamente. La etapa y el número de semestre proceden del registro de formación del alumno para ese periodo; no se deducen de su edad ni de su curso actual.
4. Revisa ciclo, Rector y Prefecto de Estudios. Los firmantes se pueden configurar una vez en **Datos del plantel** después de instalar la actualización de la base. El responsable de Control Escolar y el Prefecto son campos diferentes. El ciclo se propone a partir de agosto; se puede corregir antes de emitir. “Grupo” identifica la etapa (CI, Filosofía o Teología), sin crear grupos paralelos.
5. Comprueba materias y notas, marca la revisión y pulsa **Emitir boleta revisada**. Las materias pendientes aparecen como **PENDIENTE** y bloquean la emisión: nunca se convierten en cero. También se requieren matrícula, etapa, semestre y ambos firmantes. Una nota reprobatoria publicada sí se incluye en la boleta.
6. En **Boletas emitidas**, abre el documento y pulsa **Imprimir / Guardar PDF**. El formato es carta vertical, con escudo, encabezado, ciclo, periodo, datos del alumno, dos columnas y firmas. En el diálogo del navegador, elige tamaño carta, escala 100 %, sin encabezados/pies del navegador. Las boletas extensas pueden ocupar más de una página.

La emisión se produce tras la revisión de Control Escolar. No hay una tarea programada que emita al llegar una fecha, cierre semestres o promueva alumnos. El borrador cambia con las notas actuales; una emisión conserva su copia con folio interno y fecha. El archivo guardado es una instantánea de datos en PostgreSQL; el PDF se genera al imprimir esa copia.

## Escala y compatibilidad

- Captura y consulta de notas: **0.0–10.0**, un decimal, mínima aprobatoria **7.0**. Se incluyen tareas, libro de calificaciones, ajustes de finales, materias del alumno y listas de Control Escolar.
- Los porcentajes de ponderación y avance permanecen en 0–100 %. No son calificaciones.
- El contrato de las tablas y RPC existentes conserva 0–100: una captura de 8.5 envía 85, y un 85 guardado se muestra como 8.5. No se dividen las notas de la base ni se altera su significado.
- Las notas históricas se presentan redondeadas a un decimal. Editar solo comentarios conserva su valor original; una nueva captura acepta un decimal. Si el redondeo de una nota histórica inferior a 7.0 mostraría 7.0, la boleta solicita revisar esa final antes de emitir, para no aparentar una aprobación.
- La migración nueva establece la configuración de los planes en mínima 70 interna y escala documental 10. Incrementa la revisión de los planes que cambian. No altera notas, inscripciones ni documentos ya emitidos. Los nuevos kardex llevan escala 10 y un decimal; las copias históricas conservan su escala y formato anteriores.
- Mientras no se instale el SQL nuevo, la boleta permite vista previa y explica que la emisión está pendiente de habilitarse. Los kardex existentes siguen la escala informada por el servidor hasta que se actualice su configuración.

## Base de datos: pendiente de verificar e instalar

Archivo preparado: `supabase/migrations/20261027000000_semester_report_cards.sql`.

**No basta con copiar el archivo al repositorio. No está ejecutado en Supabase.** Antes de aplicarlo, el administrador debe comparar el esquema real de producción con las dependencias: kardex, historial de formación y funciones de autorización. No ejecutar las migraciones anteriores para intentar completar dependencias sin verificar su estado y preparar un respaldo.

La migración es transaccional y de una sola aplicación. Añade el campo institucional del Prefecto, una tabla privada de emisiones, una secuencia de folios y las RPC `portal_report_card_read` y `portal_report_card_issue`. Envuelve las funciones existentes de kardex para la escala institucional. Requiere las 16 migraciones anteriores del esquema reconstruido o un esquema equivalente verificado; si falta una dependencia, la transacción falla. No contiene claves ni datos reales de alumnos.

Las RPC comprueban el perfil activo de Control Escolar. La tabla y los ayudantes privados no dan acceso directo a usuarios autenticados ni anónimos. Al emitir se vuelve a calcular la boleta bajo la barrera de escrituras académicas: si las notas o el expediente cambiaron desde la vista previa, se exige otra revisión. Un identificador de solicitud permite reintentar una respuesta perdida sin duplicar el documento. Cada emisión deliberada nueva sí obtiene un folio nuevo. Las copias sobreviven al retiro de materias o de la etapa del periodo; la referencia al alumno impide borrarlo dejando documentos huérfanos.

## Verificación local

Se prueban PostgreSQL desechable sin red y un navegador con API simulada, usando exclusivamente personas ficticias. Se comprueban permisos, ausencia de notas, cero, reprobación, redondeo, cambios concurrentes, folios, reintentos, firmantes, conservación de copias, impresión, móvil y limpieza al salir. También se verifica la captura de notas, ponderaciones y el acceso local/PDF existentes.

La política del Chromium del entorno impide navegar a `file://`. La rama de compatibilidad local se verifica mediante respuestas de prueba y un origen opaco; la apertura real de archivos en tu navegador conserva el mecanismo de acceso local que ya comprobaste. No se usaron credenciales ni registros de producción.

## Kardex por etapa

Se conserva el historial y la emisión de kardex existentes, con vinculación de programas a CI, Filosofía y Teología. El diseño definitivo del documento de cierre de etapa queda pendiente de la plantilla que enviarás. No se inventaron campos ni requisitos de esa plantilla.
