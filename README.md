# seminario-matamoros-reynosa
Sitio web oficial del Seminario Diocesano de la Diócesis de Matamoros-Reynosa.

Documentación del proyecto:

- [Configurar seminariomr.org con Porkbun, Cloudflare, HTTPS e indexación](docs/dominio-seminariomr.md)
- [Portal y comprobaciones del acceso](portal/README.md)
- [Esquema SQL y comprobación de RLS](supabase/README.md)
- [Instalar y probar Mis materias](docs/mis-materias.md)
- [Instalar y probar calificaciones publicadas](docs/calificaciones.md)
- [Instalar y probar el panel de profesor](docs/profesores.md)
- [Guardar y publicar calificaciones desde el portal](docs/capturar-calificaciones.md)
- [Crear periodos y materias desde Control Escolar](docs/control-escolar.md)

El Portal Escolar permite iniciar sesión, consultar el perfil y ver las materias
inscritas del alumno con sus calificaciones publicadas en escala de 0 a 100.
El profesor puede consultar sus materias asignadas, ver sus alumnos activos y
guardar y publicar calificaciones mediante funciones autorizadas en PostgreSQL.
Control Escolar puede consultar y crear periodos y materias desde el portal.
Las inscripciones se cargan desde administración. Los datos se
protegen en PostgreSQL mediante RLS. El código SQL se aplica manualmente en
Supabase; subir archivos a GitHub publica el sitio, pero no modifica la base de datos.
