# Temas Claro, Oscuro y OLED

Actualización sobre `f2ffc46`. Añade un selector de apariencia al Portal Escolar,
incluidos acceso, creación de contraseña y panel de los tres roles. No añade SQL,
dependencias ni servicios externos.

## Uso

Pulsar el botón de apariencia en el encabezado (sol/luna/círculo OLED) y elegir:

- **Claro**: conserva la paleta actual del portal y es el valor inicial.
- **Oscuro**: fondos gris carbón, superficies diferenciadas y azules claros para
  enlaces, foco y acciones.
- **OLED**: negro puro en página, encabezado y tarjetas principales; divisiones,
  formularios y estados conservan diferencias de tono para poder identificarlos.

El selector muestra una vista pequeña de cada paleta y una descripción. En
pantallas estrechas el botón muestra solo el icono, conservando nombre accesible
y título. Se puede operar con teclado mediante los radios nativos. Escape
cierra el selector y devuelve el foco al botón; pulsar fuera, cambiar de sección
o redimensionar la ventana también lo cierra.

La preferencia se guarda en `localStorage`, clave `seminario.portal.theme`, con
los únicos valores válidos `light`, `dark`, `oled`. Se conserva entre visitas,
acceso y cierre de sesión, y se sincroniza entre pestañas del mismo origen.
Es una preferencia del navegador, no de una cuenta ni un dato de Supabase. Si el
almacenamiento está bloqueado, el selector sigue funcionando durante la visita.
Valores desconocidos vuelven a Claro.

## Diseño y alcance

Los temas oscuros adaptan encabezados y menús, tarjetas, anuncios, calendario,
cursos, lector de contenido, formularios, archivos, calificaciones y administración.
Los colores de éxito, error, avisos y categorías de evaluación conservan su
significado mediante tonos legibles en fondos oscuros. Los controles del
navegador reciben `color-scheme` acorde con el tema.

Las fotos, el escudo y los PDF no se invierten ni se filtran. Las vistas de boleta
y kardex mantienen papel blanco y texto oscuro. Las reglas oscuras están dentro
de `@media screen`; la impresión conserva sus estilos y oculta el selector.
El sitio público no carga estos archivos y conserva su apariencia.

En celular el selector ocupa el lugar disponible en el encabezado; el acceso a
Mi perfil se mantiene en el menú lateral. Las herramientas adicionales del
encabezado se ocultan en anchos intermedios para dejar espacio a la apariencia,
el nombre del curso y el cierre de sesión. El menú de secciones conserva una fila
en escritorio.

## Implementación

- `portal/theme.js`: inicializa el tema antes de pintar la página, valida la
  preferencia y crea el botón y selector al cargar el DOM. No accede a Supabase,
  no modifica autenticación y no contiene datos personales.
- `portal/theme.css`: variables semánticas de color, variantes oscuras, selector,
  adaptación del encabezado y exclusiones de documentos/impresión.
- `portal/index.html`, `panel.html`, `activar.html`: cargan el script en el head,
  antes de las hojas de estilo, la hoja de tema al final y un punto de montaje
  `data-theme-control` en el encabezado.

El elemento raíz utiliza `data-theme` (`light/dark/oled`) y `data-theme-tone`
(`light/dark`). La variante OLED reutiliza las reglas oscuras y cambia sus
variables de fondo, bordes y acentos. El modo Claro no aplica las sustituciones
de color del modo oscuro. No se recrean las vistas ni se envían solicitudes de
datos al cambiar de apariencia.

Al añadir componentes, usar las variables `--theme-card`, `--theme-ink`,
`--theme-muted`, `--theme-line`, `--theme-accent` y los colores de estado cuando
corresponda, y revisar su contraste en ambos temas oscuros. Las superficies y
textos de documentos oficiales deben conservar sus excepciones de papel.

## Instalar

Corrección del acceso integrado (`panel.html` abierto desde `file://`): al cerrar
sesión, la sección `.local-access.access-page` conservaba su fondo claro propio y
ocultaba el selector junto con las acciones de la sesión. El tema ahora deja ese
fondo transparente, aplica la paleta elegida al acceso y mantiene visible solo
el selector de apariencia. No cambia el comportamiento de autenticación.
`tests/portal_local_access_theme.py` comprueba los tres temas tras cerrar sesión,
en escritorio y celular de 320 px, además del contraste y cambio de apariencia.

Combinar las carpetas del paquete con el repositorio y reemplazar sus archivos,
publicar en GitHub y recargar con Ctrl+F5. No hay migraciones que ejecutar ni
cambios de configuración en Supabase.

## Verificación

```bash
python3 -B tests/portal_themes.py
python3 -B tests/portal_workspace.py
python3 -B tests/portal_enrollment_stages_readability.py
```

Las pruebas usan Chromium, SDK real de Supabase y API simulada, sin datos reales
ni escrituras en producción. Revisan los tres roles y temas en escritorio y
celular, 320 px, persistencia y sincronización entre pestañas, entrada/activación,
almacenamiento bloqueado, valores inválidos, teclado/foco, lector y formularios,
calificaciones, administración, selección múltiple y papel/impresión.
Los textos principales, enlaces y controles habilitados seleccionados en estas
vistas se comprueban con una relación de contraste mínima de 4.5:1. Las capturas
de prueba contienen personas y materias ficticias.
