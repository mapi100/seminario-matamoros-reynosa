# Colores de las clases, materiales y distribución del inicio

## Qué cambia

- Las tarjetas de cursos, las cabeceras dentro de cada clase y las tarjetas de
  unidades usan colores. El color se mantiene según el código de la materia.
- El inicio de Control Escolar coloca **Mis cursos** y los accesos de
  administración en filas distintas. Los anuncios, las tareas y el calendario
  permanecen a la derecha en computadora; en móvil se apilan.
- **Contenido → Agregar contenido** permite seleccionar archivos desde la
  computadora, además de escribir indicaciones y añadir un enlace.

## Instalar

1. Copia el contenido del ZIP en la raíz del proyecto, combinando carpetas y
   reemplazando archivos. La actualización incluye los cambios anteriores de
   Control Escolar docente y eliminación definitiva.
2. Si todavía no aplicaste `20261022000000_staff_teaching_deletion.sql`, ejecútalo
   primero en Supabase → SQL Editor. **No lo repitas si ya lo aplicaste.**
3. Ejecuta completo **una sola vez** el SQL nuevo:
   `supabase/migrations/20261022010000_course_content_files.sql`.
   Requiere también las migraciones previas, incluidas 800 y 900.
4. Publica los cambios y recarga con Ctrl + F5:

```powershell
git add portal docs supabase tests
git commit -m "Agregar archivos de contenido y corregir inicio del portal"
git push origin main
```

Instalar el SQL crea el almacenamiento privado y las funciones; no borra datos
existentes ni cambia sus estados de publicación. No requiere servicios de pago,
SMTP ni Edge Functions adicionales.

## Publicar material

Entra con un profesor asignado, o con Control Escolar:

1. Abre la clase → Contenido → Agregar contenido en una unidad.
2. Escribe el título. Las indicaciones, el enlace y los archivos son opcionales.
3. En **Subir archivos desde la computadora**, selecciona uno o varios archivos.
4. Elige si el tema queda publicado y pulsa **Guardar**.

Se admiten PDF; Word DOC/DOCX; PowerPoint PPT/PPTX; Excel XLS/XLSX; RTF, TXT,
JPG/JPEG, PNG, WEBP y ZIP. Límite: **10 MB por archivo y 5 archivos por tema**.
Los adjuntos de las tareas de alumnos conservan sus límites anteriores.
Los archivos se suben al guardar. Si una subida falla, **Reintentar subida**
continúa los archivos pendientes sin crear otro tema ni duplicar registros.
Si no se pudo confirmar el guardado del tema, se pide actualizar antes de repetir.

En **Editar contenido** puedes descargar o quitar adjuntos. Quitar pide
confirmación. **Actualizar archivos** vuelve a comprobar la lista. Si una subida
quedó sin registrar, **Limpiar subidas incompletas** permite liberar ese espacio.

## Acceso y eliminación

Los alumnos inscritos pueden descargar los archivos de los temas publicados en
unidades publicadas de cursos activos. La autorización se comprueba otra vez al
descargar: una copia antigua de la página no da acceso a un tema retirado o a un
curso del que se dio de baja al alumno. Los borradores quedan disponibles solo
para el personal autorizado. No hay enlaces públicos permanentes a los archivos.

Las descargas se realizan como archivos, sin ejecutar documentos dentro del
portal. Los enlaces externos siguen abriéndose aparte.

Eliminar una clase, materia o periodo también retira sus materiales docentes y
programa la eliminación física de los objetos. Se usa la misma limpieza
reanudable de la actualización anterior, ampliada a los buckets privados de
entregas y contenido. Si hay una falla, Control Escolar puede reintentar desde el
aviso de archivos pendientes.

## Verificación local

- `python3 supabase/tests/run_content_files_local.py`: permisos reales de
  PostgreSQL/RLS/RPC, publicación, límites, registro idempotente y eliminación en
  ambos buckets, usando Auth y Storage como fixtures.
- `python3 tests/portal_content_files.py`: SDK real y API simulada, Word/PDF con
  enlaces, reintentos, descargas, confirmación y distribución de inicio/móvil.
- Regresiones: `supabase/tests/run_staff_deletion_local.py`,
  `tests/portal_learning.py`, `tests/portal_workspace.py` y
  `tests/portal_staff_deletion.py`.

Las pruebas no acceden a datos reales, envían correos ni validan el transporte
HTTP del Storage de producción.
