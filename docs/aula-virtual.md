# Aula virtual del Seminario

El portal organiza el inicio y los cursos con una experiencia inspirada en las
capturas de Brightspace: cabecera blanca, navegación horizontal, portada del
Seminario, tarjetas de cursos a la izquierda y anuncios, fechas de entrega y
calendario a la derecha. En celular se adapta a una columna y menú desplegable.

Las clases y personas actuales se conservan. No se copian los nombres, correos,
calificaciones ni la marca universitaria de las capturas de referencia.

## Qué hace cada rol

| Función | Alumno inscrito | Profesor asignado | Control Escolar |
| --- | --- | --- | --- |
| Consultar contenido y anuncios publicados | Su curso | Sus cursos | Todos los cursos activos |
| Consultar programa, tareas y calendario | Su curso | Sus cursos | Todos los cursos activos |
| Entregar trabajos y marcar temas completados | Su propio trabajo | Consulta entregas | Consulta entregas |
| Crear y editar contenido, anuncios y tareas | No | Sus cursos | Todos los cursos activos |
| Libro de calificaciones de la clase | No | Sus cursos | Todos los cursos activos |
| Consultar notas publicadas | Solo las propias | Sus alumnos | Todos los cursos activos |
| Administrar personas, periodos e inscripciones | No | No | Sí |
| Publicar anuncios institucionales | No | No | Sí |

Los permisos se comprueban en PostgreSQL, incluyendo el acceso por URL directa,
el estado activo de la cuenta y los vínculos activos de la clase. Ocultar un
botón no concede ni reemplaza esos permisos.

## Instalar los archivos

1. Extrae el paquete fuera del repositorio, por ejemplo en Descargas.
2. Copia **el contenido** de la carpeta extraída en la raíz de
   `seminario-matamoros-reynosa`, junto a `index.html`. Combina las carpetas y
   reemplaza los archivos con el mismo nombre.
3. Comprueba que existan `portal/learning.js`, `portal/learning-files.js` y
   sus CSS junto a `portal/panel.html`.
4. En Supabase → **SQL Editor**, ejecuta primero todo el contenido de:

   ```text
   supabase/migrations/20261021080000_learning_workspace.sql
   ```

5. Después, en otra consulta, ejecuta todo el contenido de:

   ```text
   supabase/migrations/20261021090000_learning_files.sql
   ```

Estas migraciones se aplican **una sola vez**, después de las migraciones
anteriores, incluyendo `700`. No repitas las que ya dieron OK. Si alguna falla,
revisa el error antes de continuar; cada migración es transaccional.

La migración `800` crea el aula, y `900` añade adjuntos en un bucket privado de
Supabase Storage llamado `portal-coursework`. No cambian los registros DNS ni
la configuración de Gmail, Resend o las cuentas de correo existentes.

Publica los archivos desde PowerShell en la raíz del repositorio:

```powershell
git status
git add portal/ supabase/ docs/ tests/ README.md
git commit -m "Agregar aula virtual con tareas anuncios y libro de calificaciones"
git pull --rebase origin main
git push origin main
```

Si Git informa de un conflicto, resuélvelo antes de continuar. GitHub Pages
publica el sitio; no ejecuta SQL ni configura Supabase Storage por su cuenta.
Después del despliegue abre `https://seminariomr.org/portal/` y actualiza la
página con `Ctrl+Shift+R` si el navegador conserva la apariencia anterior.

## Primer recorrido como profesor o Control Escolar

1. Elige una clase activa desde **Entrar al curso**. Control Escolar también
   puede abrirla en **Clases**.
2. En **Programa**, agrega objetivos, criterios de evaluación y bibliografía.
3. En **Contenido**, crea una unidad y agrega temas con texto o enlaces.
   Publica tanto la unidad como los temas que deben ver los alumnos.
4. En **Anuncios**, publica un mensaje para esa clase. Puedes fijarlo o
   guardarlo como borrador; los alumnos solo reciben lo publicado.
5. En **Tareas**, crea una actividad con instrucciones, fecha de entrega y
   la opción de permitir o cerrar entregas tardías. Publícala.
6. En **Calendario**, registra los eventos del curso. Las fechas límite de
   las tareas también se consultan desde los pendientes y el calendario.
7. En **Calificaciones**, revisa las entregas, registra notas de 0 a 100 y
   comentarios. **Guardar borradores** conserva el trabajo del profesor;
   **Publicar calificaciones** lo hace visible al alumno.

Los anuncios institucionales de Control Escolar aparecen en el inicio, junto
con los anuncios de los cursos a los que cada persona tiene acceso.

## Recorrido como alumno

1. En el inicio, consulta tus cursos, anuncios y trabajo pendiente.
2. Abre una tarea desde su fecha límite o desde la tarjeta del curso.
3. Lee las instrucciones y entrega texto, un enlace o un archivo permitido.
4. Revisa la confirmación y la fecha de entrega. Puedes reemplazar o ampliar
   tu entrega mientras las reglas de fecha de la tarea lo permitan.
5. En **Mis calificaciones**, consulta tus notas y comentarios publicados.
6. En **Contenido**, abre los temas y marca los que ya completaste.

El alumno no recibe el libro grupal de notas ni los borradores del profesor.
Un cambio de borrador no reemplaza la nota publicada hasta que el profesor
publique de nuevo. Los controles de revisión evitan sobrescribir una nota
que otra persona haya editado simultáneamente.

## Adjuntos y límites del plan gratuito

Se permiten **PDF, JPG, PNG, TXT y DOCX**, hasta **5 MB por archivo** y **tres
archivos por alumno y tarea**. Los archivos permanecen privados: solo el alumno
correspondiente y el personal autorizado del curso pueden descargarlos.
La descarga utiliza la sesión autenticada y no publica una URL permanente.

Subir y registrar un archivo también registra la entrega. Retirar el último
archivo de una entrega requiere conservar texto, un enlace u otro archivo.
Si un resultado de red queda incierto, actualiza antes de repetir la operación.

El espacio y la transferencia tienen las cuotas del proyecto de Supabase.
El máximo por archivo no significa almacenamiento ilimitado. La entrega por
texto o enlace permite trabajar sin consumir espacio de adjuntos. Revisar el
uso y limpiar objetos huérfanos corresponde al responsable del proyecto.

## Calificación final y alcance de esta entrega

Las notas de actividades son independientes de la **calificación final** que
ya utilizaba el portal. No se calcula ni publica una nota final automáticamente
con ponderaciones inventadas; el flujo anterior de la nota final se conserva.

Esta versión incluye programa, unidades, progreso de temas, anuncios, eventos,
tareas, entregas, adjuntos privados y calificaciones por actividad. Cuestionarios
autocalificables, foros, videoconferencia, asistencia, SCORM y las integraciones
externas de Brightspace requieren módulos adicionales; no se muestran botones
que simulen esas funciones.

El modelo actual sigue organizando una clase por materia y periodo, con varios
profesores posibles. Los grupos paralelos de la misma materia y periodo
requieren ampliar el modelo antes de utilizarlos.

Cada curso admite hasta 50 unidades, 250 temas, 100 tareas y 200 anuncios/eventos
por tipo. El libro y los participantes se consultan por páginas. Los widgets
del inicio utilizan feeds acotados; el detalle de cada curso conserva su propio
contenido. No son límites impuestos por Resend: estas funciones se utilizan
dentro del portal y no envían un correo por cada consulta o calificación.

## Verificar antes de incorporar personas

Con las cuentas de prueba existentes, completa el recorrido profesor → entrega
del alumno → borrador → publicación → lectura del alumno. Comprueba también
que otro alumno no pueda abrir esa entrega o el libro de la clase, y que una
inscripción desactivada deje de autorizar consultas.

Las pruebas automatizadas utilizan PostgreSQL desechable, un fixture de Storage
y APIs simuladas con el SDK real. No crean personas ni tareas en producción.
Las cuotas, el servicio HTTP real de Storage y la entrega SMTP se comprueban
en el proyecto del Seminario después de configurar e instalar los servicios.

```powershell
python supabase/tests/run_learning_local.py
python tests/portal_learning.py
```

Las pruebas SQL requieren Docker con `postgres:17-bookworm`; las de navegador
requieren Python, Playwright y Chromium.

Validación de esta entrega: **326 comprobaciones PostgreSQL** y **204 escenarios
de navegador** aprobados (185 del portal anterior y 19 del aula virtual).
Se comprobaron también los enlaces, los recursos HTML y la sintaxis JavaScript.
