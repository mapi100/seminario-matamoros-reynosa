# seminario-matamoros-reynosa
Página Web Oficial del Seminario Diocesano de Matamoros-Reynosa.

Documentación del proyecto:

- [Campus autónomo: navegación, clases, personas e invitaciones](docs/campus-autonomo.md)
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
Control Escolar puede administrar personas, materias, periodos, clases,
profesores e inscripciones desde el portal, con bajas que conservan el historial.
Las invitaciones están preparadas y requieren activar SMTP y la Edge Function
según la guía del campus. Los buzones institucionales se contratan o tramitan
por separado, según la elegibilidad del Seminario. Los datos se
protegen en PostgreSQL mediante RLS. El código SQL se aplica manualmente en
Supabase; subir archivos a GitHub publica el sitio, pero no modifica la base de datos.
