# Módulo: gui/queue

## Propósito
Cola FIFO de lotes y secuencia (añadir, quitar, reordenar, ejecutar).

**Desde v3.21 (feat-uc2-21) la GUI ya no usa colas**: el servicio y las tablas `batch_queues` se conservan, pero sin interfaz; borrar/finalizar aún desvinculan el lote de colas abiertas heredadas.

## Archivos
- `service.py` — modelos y operaciones SQLite (sin Tk)

Su panel visual fue retirado de `batches/dialog.py`.

## Tests
`tests/gui/test_queue.py`
