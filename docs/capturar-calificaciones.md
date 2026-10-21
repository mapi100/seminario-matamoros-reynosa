# Instalar y usar la captura de calificaciones

Esta actualización añade **Calificar** junto al nombre de cada alumno en la
lista del profesor. Se puede guardar un borrador y publicarlo por separado.
Reutiliza tu profesor, alumno y materias DEMO actuales.

## 1. Extraer la actualización

Guarda `seminario-captura-calificaciones.zip` dentro de la carpeta de tu
repositorio. Desde la terminal en esa carpeta:

```bash
cp -a portal "../portal-respaldo-$(date +%Y%m%d-%H%M%S)"
unzip -o seminario-captura-calificaciones.zip
```

## 2. Aplicar solamente la nueva migración

Abre `supabase/migrations/20261021040000_enable_grade_capture.sql` con tu editor.
Copia el archivo completo en **Supabase → SQL Editor → New query** y pulsa **Run**.
Ejecuta esta migración una sola vez desde la cuenta administrativa de confianza.
No repitas las cuatro migraciones anteriores ni los datos DEMO.

El archivo crea borradores privados, historial de cambios y funciones con
autorización para consultar, guardar y publicar. No publica notas por sí solo.
Ante un error, ejecuta `rollback;` y revisa el mensaje antes de continuar.

Puedes comprobar la configuración con `supabase/tests/grade_capture_rls.sql` en
otra consulta: sustituye `PROFESSOR_UID_AQUI` por el UID de tu profesor de prueba.
Es de solo lectura y debe mostrar **Captura: RLS y permisos OK**. Conserva el
marcador en GitHub. Los detalles están en [supabase/README.md](../supabase/README.md).

## 3. Publicar los archivos

Desde la terminal, dentro del repositorio:

```bash
git add README.md portal/ supabase/ tests/ docs/
git commit -m "Permitir guardar y publicar calificaciones del profesor"
git pull --rebase origin main
```

Si termina sin conflictos:

```bash
git push origin main
```

Cuando Pages termine de publicar, abre el portal y recarga con **Ctrl + Shift + R**.

## 4. Registrar una nota de prueba

1. Inicia sesión como **Profesor de prueba**.
2. En **Historia — ejemplo**, pulsa **Ver alumnos**.
3. Junto a **Usuario de prueba**, pulsa **Calificar**.
4. Se abre el editor. Escribe **90** en **Calificación de 0 a 100**.
5. Pulsa **Guardar borrador**. Debe confirmar el guardado y habilitar
   **Publicar calificación**. La nota que ve el alumno todavía no cambia.
6. Pulsa **Publicar calificación**. Debe confirmar la publicación.
7. Cierra sesión y entra como alumno. Historia debe mostrar **90 / 100**.

Usa las materias DEMO para esta comprobación. Publicar es la acción que cambia
la nota visible; abrir el editor o guardar un borrador no la modifica.

Si corriges el número después de guardar, Publicar se deshabilita hasta guardar
de nuevo. Para editar una nota publicada, sigue el mismo flujo: el alumno conserva
la anterior hasta que publiques la corrección.

## Conflictos y conexión

Si otro profesor o pestaña guarda primero, la versión antigua no se sobrescribe.
Pulsa **Volver a consultar**, revisa el estado actualizado y vuelve a guardar.
Las asignaciones compartidas permiten a ambos profesores capturar las mismas
notas; el control de revisión detecta cambios realizados mediante este flujo.

Ante un fallo después de guardar o publicar, la operación pudo haberse completado.
El editor bloquea otra escritura hasta consultar de nuevo, sin reenvíos
automáticos. Cerrar el editor u ocultar la pestaña limpia los datos de la pantalla;
una petición ya enviada puede terminar en la base de datos.

La auditoría registra las operaciones de las funciones de captura. Los cambios
manuales de un administrador SQL no pasan automáticamente por esa auditoría o
control de revisión. Para este flujo de prueba, captura las notas desde el portal.
