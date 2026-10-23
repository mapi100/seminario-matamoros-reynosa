# Etapas y semestres del Seminario

| Etapa | Nombre de la etapa formativa | Semestres |
| --- | --- | --- |
| Curso Introductorio | Propedéutica | 2 |
| Filosofía | Discipular | 6 |
| Teología | Configuradora | 8 |

La numeración comienza en 1 en cada etapa. El periodo académico tiene sus
propias fechas: por ejemplo, `Ago–Dic 2026` puede corresponder al semestre 3 de
Filosofía de un alumno y al semestre 1 de Teología de otro.

## Instalación

1. En Supabase → SQL Editor, ejecuta **una sola vez** el contenido completo de
   `supabase/migrations/20261023000000_formation_stages.sql`, después de las
   migraciones del kardex y expediente personal ya instaladas.
2. Copia los archivos de la actualización en la raíz del proyecto conservando
   sus rutas. Publica los cambios en GitHub Pages.
3. Recarga el portal y entra como Control Escolar. Aparecerá **Etapas y semestres**.

La migración registra las tres etapas. Los alumnos existentes quedan pendientes
de clasificar: Control Escolar conoce su ubicación académica y la confirma.
Los programas, materias, inscripciones y calificaciones existentes se conservan.

## Registrar la trayectoria de un alumno

1. Abre **Etapas y semestres**.
2. Selecciona el **periodo académico** que deseas organizar.
3. Busca al alumno por nombre o matrícula.
4. Pulsa **Asignar etapa y semestre**.
5. Selecciona la etapa y el semestre; el selector muestra 2, 6 u 8 opciones
   según corresponda. Guarda.

El registro corresponde a ese alumno y periodo. La ventana muestra su
trayectoria anterior para consultarla antes de guardar. El avance lo determina
el Seminario; la asignación no aprueba materias ni inscribe automáticamente en
clases. Las inscripciones se administran en el apartado existente.

Para el siguiente periodo, selecciónalo y registra el nuevo semestre. Así,
Filosofía 3 en Ago–Dic y Filosofía 4 en Ene–Jun quedan como dos registros.
Al pasar de etapa, el semestre vuelve a 1. Si se corrige un dato del mismo
periodo, queda registrada la modificación en Actividad.

Los filtros de etapa se aplican al periodo seleccionado. Puedes consultar
también alumnos inactivos con trayectoria registrada.

## Planes de estudio y kardex

En **Kardex → Programas y planes → Editar programa**, selecciona la etapa del
programa. En **Materias y créditos**, asigna a cada materia un semestre de esa
etapa. Los planes sin etapa mantienen su clasificación anterior.

Si un plan ya contiene textos como `Primero`, el selector conserva el valor
anterior como **Por clasificar**. Selecciona su semestre numérico antes de
guardar esa página; el sistema no lo interpreta ni sustituye automáticamente.
La duración de la etapa se valida también en el servidor.

En el kardex, cada periodo con etapa registrada muestra el nombre de la etapa y
el semestre cursado. El PDF y CSV de las nuevas emisiones conservan esos datos.
Una corrección posterior cambia la vista previa y requiere volver a consultarla
antes de emitir; los documentos ya emitidos conservan su copia original.

## Vista del seminarista y página pública

El alumno consulta su propia trayectoria en **Inicio** y **Mi perfil**.
La pestaña **Datos escolares** del expediente muestra los mismos registros,
en modo de consulta. Solo Control Escolar puede cambiarlos.

La página pública incluye **Formación**, con las tres etapas y sus duraciones.
Los datos individuales de alumnos se consultan dentro del portal autorizado.

## Verificación local

```bash
python supabase/tests/run_formation_local.py
python tests/portal_formation.py
```

La primera prueba usa PostgreSQL en un contenedor temporal sin red; la segunda
usa Chromium y un servidor API simulado. Cubren límites por etapa, permisos,
historial por periodo, conflictos de edición, planes, kardex y uso en celular.
No utilizan usuarios ni datos de producción.
