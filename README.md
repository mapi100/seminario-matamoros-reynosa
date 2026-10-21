# seminario-matamoros-reynosa
Sitio web oficial del Seminario Diocesano de la Diócesis de Matamoros-Reynosa.

Documentación del proyecto:

- [Portal y comprobaciones del acceso](portal/README.md)
- [Esquema SQL y comprobación de RLS](supabase/README.md)
- [Instalar y probar Mis materias](docs/mis-materias.md)

El Portal Escolar permite iniciar sesión, consultar el perfil y ver las materias
inscritas del alumno. Las inscripciones se cargan desde administración y se
protegen en PostgreSQL mediante RLS. El código SQL se aplica manualmente en
Supabase; subir archivos a GitHub publica el sitio, pero no modifica la base de datos.
