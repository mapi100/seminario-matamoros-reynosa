# Curso exacto, promedio semestral y calificaciones reprobatorias

Actualización del 5 de noviembre de 2026. Se aplica a la vista previa, impresión individual y PDF descargados en ZIP por Control Escolar.

- **Grupo:** indica el curso correspondiente a la etapa y semestre registrados para ese periodo: CI-1, CI-2, 1F-1, 1F-2, 2F-3, etc. Se utilizan los datos de la boleta emitida para conservar su contexto histórico.
- **Promedio semestral:** media aritmética de todas las calificaciones finales que aparecen en la boleta, con un decimal. Se incluyen las reprobatorias y los ceros. Si una nota está pendiente, la vista previa muestra el promedio como PENDIENTE. No se modifica la escala interna de la base de datos ni las ponderaciones de cada clase.
- **Reprobación:** calificaciones de 6.9 o menos con fondo rojo y número negro, solo en la celda de la nota. Una calificación de 7.0 se conserva sin rojo. El mismo criterio se aplica a la celda del promedio.
- **Una hoja:** el promedio participa en el ajuste del contenido, conservando las firmas y el pie con folio, fecha y escala en la única página tamaño carta. El PDF del ZIP conserva el color sin depender de los ajustes de impresión del navegador.

## Instalación

Copia las carpetas del ZIP sobre tu repositorio y publica los cambios como de costumbre. Conserva el resto de los archivos. **Esta actualización no requiere ejecutar SQL.** Recarga el portal después de publicar y vuelve a descargar o imprimir las boletas: los PDF que ya estaban guardados en tu computadora conservan su apariencia anterior.

Este paquete complementa la actualización anterior de acceso de Control Escolar y descarga por ZIP; requiere que aquella ya esté instalada.

## Verificación

Se prueban PDF reales con datos ficticios y API simulada, sin acceder a producción. Se comprueban los cursos de CI, Filosofía y Teología, el cálculo del promedio, notas de 5, 6.9 y 7.0, color limitado a las celdas numéricas, títulos largos y conservación de todos los datos en una sola hoja.

```sh
python3 tests/portal_report_print.py
python3 tests/portal_report_zip.py
```
