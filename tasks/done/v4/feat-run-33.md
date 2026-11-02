# feat-run-33 · Sacar completadas a un lote por renombrar (v4.22.0)

## Objetivo
Con un lote parado, sacar las cuentas completadas a un lote nuevo para renombrarlo/publicarlo.

## Resultado de la implementación
* `gui/batches/extract.py` + botón **Sacar completadas…**. Estado destino AWAITING_RENAME (publicable: `PUBLISHABLE_STATUSES`). Mantiene filas de cuenta (banderas), URLs y `batch_run_id`; actualiza `duplicate_urls`.
* Solo desde PARTIAL/FAILED; error si no hay completadas o lo están todas.

## No se hizo
* Sin prueba de publicar/traer desde otra instancia real; `batch_runs.batch_id` histórico sigue apuntando al lote original.
