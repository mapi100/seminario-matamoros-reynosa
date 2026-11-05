# Ficha de inscripción, matrícula y Prefecto de Estudios

## Instalación pública

1. Combinar los archivos de esta actualización con el repositorio.
2. Ejecutar una vez `supabase/migrations/20261104000000_registration_records.sql`.
   Requiere el expediente personal y el módulo de kardex. No requiere la extensión de boletas semestrales.
3. Publicar por el procedimiento habitual de GitHub Pages y recargar con Ctrl+F5.

La migración registra como prefecto a **Pbro. Martín Nicolás Hinojosa** en la
configuración del plantel y refuerza el guardado de ese campo mediante
`portal_kardex_write('institution_save',…)`. El guardado base antiguo no incluye
prefect_name; depende de la extensión de boletas semestrales. Sin verificar la base
real no se puede atribuir el síntoma a una versión concreta instalada. La nueva
migración conserva y amplía el guardado instalado, con o sin esa extensión. No modifica
los criterios de los programas ni obliga a instalar boletas semestrales.
Las boletas/kardex ya emitidos conservan sus snapshots y firmas originales.

## Matrícula desde el expediente

Control Escolar: **Expedientes → Abrir expediente → Datos escolares → Editar matrícula**.
El alumno consulta su matrícula, pero no la modifica. La edición conserva CURP,
nacimiento, fechas escolares y todas las relaciones académicas. Acepta hasta 40
caracteres, normaliza mayúsculas, trata ceros como pendiente y rechaza duplicados.
Los cambios concurrentes exigen actualizar antes de volver a guardar.

`portal_student_number_save` verifica Control Escolar activo y el token del expediente,
actualiza únicamente kardex_students.student_number y registra auditoría sin guardar
el número en detalles genéricos. La matrícula sigue siendo la misma usada en kardex
 y boletas nuevas, no un segundo campo independiente.

## Datos de la ficha

Se añaden campos para lugar de nacimiento tal como fue declarado, teléfono de casa,
redes sociales, zona pastoral, decanato declarado y curso indicado en la ficha.
La sección Seguro médico permite cobertura y proveedor; los PDF siguen en Archivos.
Los datos del curso declarado no cambian automáticamente etapa, semestre ni inscripciones.
No se deduce país/estado ni se transforma un padre/tutor en contacto de emergencia.

## Paquete privado de importación

Las fichas, nombres, correos, nacimientos, domicilios, teléfonos y matrículas no están
incluidos en esta actualización pública. Se entregan por separado, fuera del repositorio.
**No subir ese paquete a GitHub.**

- `01_revisar.sql`: normaliza coincidencias por correo personal, alias institucional y
  nombre completo; presenta la cuenta de destino, matrícula previa/propuesta y una
  huella del estado revisado. Utiliza tablas temporales y termina con rollback.
- `02_aplicar.sql`: requiere pegar esa huella. Bloquea el lote si cambiaron datos,
  hay coincidencias ambiguas, roles distintos de student, varias fichas para una
  cuenta o matrículas duplicadas/ocupadas. Los valores de matrícula de formato no habitual
  se señalan y no sustituyen el valor actual, sin impedir aplicar sus datos personales. No crea usuarios ni cambia Auth.
- Las escrituras reutilizan las funciones de expediente y matrícula en una única
  transacción. Los valores no vacíos de la fuente actualizan sus campos; los vacíos
  no borran datos actuales. Una matrícula pendiente no sustituye una matrícula real.
  Una fecha que contradiga la CURP actual provoca error y rollback, no una corrección
  inventada. Las calificaciones, documentos emitidos, archivos y etapas permanecen.
- El protocolo se ensaya con datos ficticios. Las cuentas reales solo se pueden
  verificar al ejecutar la revisión en el proyecto de producción. No se ha aplicado
  el lote real desde esta sesión ni hay credenciales de producción disponibles.

La revisión/aplicación toma bloqueos breves para mantener coherencia. Ejecutar en un
momento tranquilo y esperar a que termine el script; no dejar una transacción abierta.
No reenviar el lote si se perdió una respuesta sin consultar primero el estado actual.
Las advertencias de la preparación y la copia original se conservan solo en el paquete privado.

## Verificación

```bash
python3 supabase/tests/run_registration_local.py
python3 tests/portal_registration.py
python3 tests/portal_personal_record.py
```

Las pruebas usan PostgreSQL desechable y API simulada, sin producción. Cubren el
prefecto al guardar/releer, permisos y conflictos de matrícula, ceros/duplicados,
campos nuevos y conservación del funcionamiento anterior del expediente.
