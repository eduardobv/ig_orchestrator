# Módulo: gui/batches

## Propósito
Diálogo “Lotes guardados y ejecuciones” (activos / históricos) e import/export.

## Archivos
- `dialog.py` — mixin `_open_pending_batches` (lista de lotes, detalle de cuentas, nuevo/renombrar/borrar/mover/recuperar; sin colas desde v3.21)
- `resume.py` — listados, load draft, runtime, finish/fail
- `transfer.py` — export/import JSON
- `manage.py` — nuevo lote vacío, renombrar, listar cuentas, borrar, recuperar del histórico (feat-uc2-21)
- `pause.py` — pausar cuentas sin empezar: las mueve a un lote DRAFT `<nombre>_PAUSA` (feat-uc2-18); con `target_name` y `suggest_split_name` mueve a un lote con nombre elegido (feat-uc2-19)

## Habla con
`gui/run` (ejecutar / renombrar). El servicio `gui/queue` ya no se usa desde la GUI.

## Tests
`tests/gui/test_resume.py`, `tests/gui/test_transfer.py`, `tests/gui/test_pause_accounts.py`, `tests/gui/test_batch_management.py`
