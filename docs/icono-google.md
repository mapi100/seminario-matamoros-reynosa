# Escudo del Seminario en Google y en el navegador

Se utiliza el escudo oficial existente sobre un lienzo blanco cuadrado. La
exportación conserva las proporciones y el diseño del archivo original
`images/escudo_seminario_nuevo-Photoroom.png`.

| Archivo | Uso |
| --- | --- |
| `favicon-96x96.png` | Ícono cuadrado de 96 × 96 declarado en las páginas |
| `favicon.ico` | Compatibilidad con navegadores, tamaños 16, 32, 48 y 96 |
| `apple-touch-icon.png` | Acceso guardado en dispositivos Apple, 180 × 180 |
| `images/escudo-seminario-blanco.png` | Logo cuadrado de 512 × 512 para los datos estructurados de la institución |

El ícono anterior apuntaba a una imagen rectangular. El favicon nuevo tiene
fondo blanco opaco y margen alrededor del escudo para su presentación en un
recorte circular. Las URL de los íconos deben mantenerse estables.

## Publicar y comprobar

1. Copia todos los archivos de la actualización en la raíz del proyecto,
   conservando sus carpetas, y publica en GitHub Pages.
2. Abre `https://seminariomr.org/favicon-96x96.png`: debe mostrarse el escudo
   oficial sobre blanco. Comprueba también `https://seminariomr.org/favicon.ico`.
3. Abre la página principal en una pestaña nueva. El navegador puede conservar
   temporalmente un ícono anterior en su caché.
4. En Google Search Console → Inspección de URLs, introduce
   `https://seminariomr.org/`, pulsa **Probar URL publicada** y, si es accesible,
   **Solicitar indexación**.

Google elige cuándo vuelve a rastrear y mostrar el favicon. La publicación
prepara el sitio para ese rastreo; el cambio en resultados puede tardar días o
semanas y no se garantiza que Google muestre un ícono concreto. Solicitar la
indexación repetidamente no acelera el proceso.

El favicon pequeño situado junto al nombre del sitio es independiente de las
miniaturas grandes que Google puede seleccionar para algunos resultados.
`robots.txt` permite consultar la portada y los archivos del ícono.

## Origen de los archivos

Los archivos finales se exportaron directamente del PNG oficial.
El sello conserva sus símbolos y texto; el único cambio de presentación es el
lienzo blanco cuadrado y la escala necesaria para cada tamaño de ícono.
