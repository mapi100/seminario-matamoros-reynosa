# PDF.js 5.4.624

Distribución oficial `pdfjs-dist@5.4.624` de Mozilla, licencia Apache-2.0.
Origen: https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-5.4.624.tgz

Integridad SHA-512 del paquete npm:
`sm6TxKTtWv1Oh6n3C6J6a8odejb5uO4A4zo/2dgkHuC0iu8ZMAXOezEODkVaoVp8nX1Xzr+0WxFJJmUr45hQzg==`

Se conservan sin modificar `build/pdf.min.mjs`, `build/pdf.worker.min.mjs`
(en esta carpeta), `cmaps/`, `standard_fonts/`, `wasm/` y sus licencias. Los
recursos se sirven desde el propio portal en HTTP/HTTPS. En `file://` se carga la
misma versión por HTTPS desde jsDelivr para evitar restricciones de módulos
locales. Los documentos no se envían a un servicio de conversión ni al CDN.
El lector se importa solo al abrir un PDF.

Para actualizar, fijar y verificar la nueva versión y su integridad, reemplazar
ambos módulos y los recursos de la misma versión, conservar las licencias y
ejecutar las pruebas de contenido/lector. No mezclar versiones del worker y API.
