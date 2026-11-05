# Boletas en una sola hoja

La impresión de boletas utiliza una hoja tamaño Carta, con los márgenes dentro
del documento. Así se conserva el espacio de las firmas y el pie oficial en
la misma página, sin reservar espacio para encabezados automáticos del navegador.
La hoja de boletas tiene su propia configuración: no hereda los márgenes del kardex.

El encabezado, los datos del alumno y la tabla se miden al imprimir. Si el
contenido real es más alto, se ajusta su escala sin eliminar materias ni texto.
Las firmas y el pie permanecen fuera de ese ajuste y al final de la hoja.
Los cursos actuales, de siete a diez materias, se imprimen a su tamaño normal.

El pie mantiene el folio, la fecha de emisión, la escala y la mínima aprobatoria.
La fecha/hora, el título y la URL que añadía el navegador se suprimen mediante
los márgenes de impresión de la página. La configuración temporal se restaura
al cerrar o cancelar la impresión para no afectar al kardex ni al resto del portal.

La misma presentación se usa al reimprimir boletas anteriores. Se recupera y
revalida la copia emitida antes de imprimir: no cambia su folio, datos, notas
ni fecha, y no es necesario volver a emitirla. Tampoco hay cambios SQL.

Publicar juntos `portal/panel.html`, `portal/report-cards.css` y
`portal/report-cards.js`. El HTML actualiza las versiones de ambos archivos
para evitar usar una hoja de estilos nueva con un script guardado en caché.
Después de publicar, recargar el portal y usar «Ver / imprimir boleta» y luego
«Imprimir / Guardar PDF». La vista previa debe indicar una página en tamaño Carta.

## Validación

```bash
python3 tests/portal_report_print.py
```

Requiere Playwright, Chromium y las herramientas de Poppler (`pdfinfo` y
`pdftotext`). Usa datos ficticios, API simulada y archivos locales; no se conecta
a Supabase. Genera PDFs reales con los encabezados del navegador habilitados
para comprobar que no aparecen. Comprueba todos los cursos del horario actual,
casos de diez y veinte materias con nombres de 160 caracteres, vista móvil,
modo OLED, revalidación de permisos y restauración de la pantalla al terminar.

Los documentos de prueba se escriben en `/tmp/seminario-report-print-checks`.
Para elegir otra carpeta:

```bash
python3 tests/portal_report_print.py --output /tmp/boletas
```
