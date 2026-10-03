# Patch v1.26.4 - Recuperacion y seguimiento de batches desde GUI

## Objetivo

Permitir localizar, inspeccionar y reanudar ejecuciones interrumpidas desde la
GUI usando SQLite como fuente de verdad, manteniendo visible el progreso de
cada cuenta dentro de `Lote actual`.

## Alcance

* Agregar `Ejecuciones pendientes` con fecha, nombre, batch id, estado y
  resumen de cuentas.
* Permitir reanudar el lote seleccionado mediante `run_continue --batch-id`.
* Recuperar en `Lote actual` sus cuentas, fechas, stories, URLs y datos de
  renombrado.
* Permitir dar manualmente por finalizado un batch, con confirmacion y sin
  borrar sus datos.
* Marcar como `PARTIAL` un batch cancelado desde la GUI para mantenerlo
  reanudable.
* Mostrar estados por cuenta con colores y contadores de completas,
  reintentos y pendientes, actualizados desde SQLite durante la ejecucion.
* Persistir por batch la fecha global y los metadatos de cada cuenta nueva.
* Incluir migraciones compatibles, tests y documentacion.
