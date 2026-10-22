# Kardex de Control Escolar

El portal permite buscar a un seminarista, revisar su historial y emitir un
kardex institucional parcial o final. El documento reúne materias por periodo,
calificaciones finales publicadas, promedio, créditos, horas, tipo de evaluación,
datos del alumno y espacios para firmas. Se imprime o guarda como PDF desde el
navegador; también se descarga como CSV para abrirlo en una hoja de cálculo.

El acceso está reservado a perfiles **activos de Control Escolar**. Un profesor
asignado a una clase conserva sus funciones docentes, pero esa asignación por sí
sola no da acceso al kardex. La restricción se comprueba en PostgreSQL, incluso
si alguien intenta invocar las funciones sin pasar por la pantalla.

## Instalar esta actualización

1. Copia el contenido del paquete sobre la raíz de
   `seminario-matamoros-reynosa`, combinando las carpetas y reemplazando los
   archivos del mismo nombre. No dejes el paquete dentro de otra carpeta del
   proyecto. Conserva los demás archivos del sitio.
2. En el **SQL Editor** del proyecto Supabase del Seminario, abre y ejecuta
   **una sola vez** todo el archivo
   `supabase/migrations/20261022020000_kardex.sql`.
   Esta migración va después de
   `20261022010000_course_content_files.sql`, correspondiente a la actualización
   anterior de archivos y colores. No vuelvas a ejecutar las migraciones antiguas.
3. Publica los archivos en GitHub desde la raíz del proyecto:

   ```powershell
   git add README.md portal docs supabase tests
   git commit -m "Agregar kardex de Control Escolar"
   git push origin main
   ```

4. Espera a que termine GitHub Pages, recarga el portal con `Ctrl + F5` e inicia
   sesión con una cuenta de Control Escolar. Aparecerá **Kardex** en la barra
   superior y **Kardex e historial** en el inicio. En **Personas**, cada alumno
   tiene un acceso **Ver kardex**.

Subir los archivos a GitHub no instala el SQL en Supabase. Esta actualización
no publica notas ni cambia las calificaciones, inscripciones o roles existentes.
No requiere un servicio nuevo para generar PDF o CSV.

## Preparación inicial, desde el portal

En **Kardex → Datos del plantel**, registra el nombre institucional, sede,
domicilio, lugar de emisión y los responsables de las firmas. La CCT se llena
únicamente si corresponde y se conoce.

En **Programas y planes → Nuevo programa**, registra el programa y la versión
de su plan. Elige la mínima aprobatoria, escala del documento y forma de
calcular el promedio. La mínima aprobatoria se captura en la escala original
de 0 a 100: **70 equivale a 7** en un documento de 0 a 10. Puedes dejar el
criterio pendiente mientras consultas esa información; el sistema no lo inventa.
El número, autoridad y fecha de RVOE se registran por programa, si existen.

En **Materias y créditos**, marca las materias que integran ese plan y registra
sus créditos, horas y semestre o etapa. Se incluyen también las materias
inactivas del catálogo. Guarda los cambios de cada página antes de pasar a la
siguiente. Este plan se configura una vez y sirve para todos los alumnos que
lo cursan. Si existe una versión nueva del plan, registra otro programa/plan
para conservar la referencia del anterior.

## Emitir el kardex de un alumno

1. **Buscar:** escribe su nombre, matrícula o CURP y pulsa **Ver historial**.
   También aparecen alumnos inactivos para consultar sus antecedentes.
2. **Revisar:** completa **Datos del alumno**, especialmente la matrícula.
   En **Clasificar materias**, asigna a cada inscripción su programa y el tipo
   de evaluación: ordinaria, extraordinaria, equivalencia o revalidación.
   Los botones **Aplicar a filas sin…** agilizan las asignaciones de la página.
   No cambian las calificaciones. Las inscripciones anteriores no se clasifican
   automáticamente para evitar atribuirles un plan equivocado.
3. **Emitir:** elige historial general o un programa, revisa la vista previa,
   selecciona parcial o final y pulsa **Emitir kardex**. El documento con folio
   aparece en **Kardex emitidos**. Usa **Imprimir / Guardar PDF** y selecciona
   *Guardar como PDF* en el cuadro de impresión, o descarga el CSV.

Para un parcial hacen falta matrícula y al menos una final publicada. Puede
mostrar inscripciones pendientes y datos institucionales sin registrar.

Para un final, selecciona un programa con plan y mínima aprobatoria configurados.
El sistema verifica que todas las materias del plan estén aprobadas, tengan
créditos registrados —cero si no otorgan créditos—, no haya finales pendientes
en inscripciones activas del programa y las finales tengan tipo de evaluación.
También pide clasificar las inscripciones que aún no tienen programa. Si falta
algo, abre **Qué falta para generar un kardex final**. Los datos que no se
conozcan no se rellenan con información ficticia.

## Cómo se calculan las notas

- Se leen exclusivamente las **calificaciones finales publicadas de la
  inscripción**. El libro de tareas y sus borradores no sustituyen la final.
  Si no aparece una final, el docente debe publicarla desde la captura de
  calificaciones finales; no se captura una segunda nota en el kardex.
- Se conservan los periodos archivados y las notas publicadas de inscripciones
  dadas de baja. Una inscripción sin nota se distingue como pendiente o baja.
- Una nota pendiente no se convierte en cero. Un cero publicado sí se incluye.
- El historial general muestra todas las inscripciones y calcula un promedio
  aritmético de sus finales publicadas, en escala de 0 a 100.
- Por programa puedes contar todas las notas, la última publicada o la mejor
  de cada materia. Todas las tentativas siguen visibles; un asterisco señala las
  que no participan en el promedio elegido. "Última" se determina por las fechas
  del periodo, no por la fecha de captura de la nota.
- El promedio puede ser aritmético o ponderado por créditos. En el segundo caso,
  si faltan créditos positivos para alguna nota que debe contar, aparece
  **Sin calcular** en lugar de un resultado parcial engañoso.
- Los créditos aprobados se cuentan una vez por materia y programa, aunque se
  repita. Si faltan criterios de aprobación o créditos necesarios, el total
  aparece **Sin calcular**.

## Folios y reimpresión

Cada emisión guarda una copia fija con folio interno `KDX-año-consecutivo`. Los
folios no son folios oficiales de la SEP. Una emisión posterior puede reflejar
notas o datos corregidos; la copia anterior mantiene su contenido original.

Si se pierde la respuesta al emitir, pulsa **Comprobar / reintentar emisión**.
El sistema reutiliza la misma solicitud para evitar duplicados. También puedes
consultar **Kardex emitidos** al volver al alumno. Cada lectura, reimpresión y
exportación vuelve a comprobar el acceso de Control Escolar.

Las copias emitidas sobreviven a la eliminación completa de una clase,
materia o periodo. El historial aún no emitido refleja lo que exista en la
base de datos: un borrado completo sí retira sus inscripciones y metadatos del
historial vivo. Conviene emitir y conservar los documentos correspondientes
antes de hacer una eliminación definitiva.

## Formato ante la SEP

Aún no se conoce el nivel o reconocimiento aplicable al Seminario ni se ha
proporcionado una plantilla oficial. Por eso este formato se identifica como
**kardex institucional** y no como certificado oficial. Incluye campos para
preparar la información, pero no garantiza aceptación ante la SEP. Antes de
usarlo en un trámite oficial habrá que confirmar el reconocimiento del programa,
el formato requerido, sus campos, las firmas y las leyendas correspondientes.

## Verificación local

Las pruebas utilizan datos ficticios y servicios simulados, sin acceder al
proyecto de producción:

```bash
python3 supabase/tests/run_kardex_local.py
python3 tests/portal_kardex.py
```

La primera ejecuta todas las migraciones en un PostgreSQL desechable con Docker.
La segunda necesita Chromium, Playwright y `pdftotext`; comprueba los flujos de
pantalla, permisos, reintentos, exportación y un PDF de 120 materias en varias
páginas. Usa `PORTAL_TEST_ARTIFACTS=/tmp/kardex-pruebas` para conservar capturas
y el PDF de muestra. No es necesario ejecutar estas pruebas para instalar.
