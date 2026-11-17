# Docentes visibles en las clases

Las tarjetas de **Clases** y del directorio general de **Mis cursos** muestran
**Docente** o **Docentes** debajo del periodo académico y antes del estado
Activa/Inactiva. En **Inicio del curso**, un bloque destacado bajo la portada
muestra los mismos nombres con tipografía grande. Lo ven alumnos, profesores y
Control Escolar cuando tienen acceso a la clase.

Los nombres corresponden a las asignaciones docentes activas de esa materia y
ese periodo, con perfiles activos de profesor o Control Escolar. El acceso
administrativo por rol no convierte a una persona en titular de todas las
materias. Si hay varios docentes, se muestran todos; si no hay ninguno, aparece
**Pendiente de asignación**. No se deduce el tratamiento o género por el nombre.

## Instalar

1. Integra los archivos de esta entrega en `main` y espera la publicación del sitio.
2. En GitHub, abre
   `supabase/migrations/20261117010000_course_instructors.sql` y copia todo su
   contenido con **Copy raw file**.
3. Ejecuta el contenido completo en una consulta nueva de Supabase → SQL Editor,
   con el rol `postgres` del proyecto habitual del Seminario.
4. Recarga el portal. Prueba Clases → periodo → bloque → Entrar al curso, y la
   misma materia desde una cuenta de alumno.

La migración es repetible y no cambia usuarios, asignaciones, notas ni boletas.
Conserva el lector del aula que ya estaba instalado, incluidas las ponderaciones
y el filtro personal de Control Escolar. No vuelvas a ejecutar las migraciones
antiguas después de esta actualización.

Si la consulta todavía no incluye los nombres, se muestra **Nombre del docente
no disponible**. Este estado es distinto de una clase que sí se consultó y no
tiene ninguna asignación. Revisa que el SQL nuevo esté instalado antes de
cambiar asignaciones.

## Permisos y rendimiento

Solo se devuelven nombres. Los alumnos no reciben correos, UUID de docentes,
expedientes ni acceso adicional a `profiles`. El lector existente comprueba la
inscripción o asignación y el estado de la clase antes de añadir los nombres.
El directorio sigue reservado a Control Escolar.

La consulta del directorio agrega los docentes del periodo en una lectura,
sin peticiones HTTP individuales por tarjeta. Se mantienen los modos claro,
oscuro y OLED, y el diseño se ajusta a pantallas pequeñas.

## Verificación local

```sh
python3 supabase/tests/run_course_instructors_local.py
python3 tests/portal_course_instructors.py
python3 tests/portal_class_directory.py
python3 tests/portal_school_workflow.py
python3 tests/portal_learning.py
```

Las pruebas usan PostgreSQL desechable y API simulada con datos ficticios;
ninguna prueba modifica producción.
