# Módulo: gui/batches

## Propósito
Diálogo “Lotes guardados y ejecuciones” (activos / históricos) e import/export.

## Archivos
- `dialog.py` — mixin `_open_pending_batches` (incluye panel de cola embebido)
- `resume.py` — listados, load draft, runtime, finish/fail
- `transfer.py` — export/import JSON
- `pause.py` — pausar cuentas sin empezar: las mueve a un lote DRAFT `<nombre>_PAUSA` (feat-uc2-18)

## Habla con
`gui/queue` (servicio) y `gui/run` (ejecutar / renombrar).

## Tests
`tests/gui/test_resume.py`, `tests/gui/test_transfer.py`, `tests/gui/test_pause_accounts.py`
