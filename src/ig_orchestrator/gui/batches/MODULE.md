# Módulo: gui/batches

## Propósito
Diálogo “Lotes guardados y ejecuciones” (activos / históricos) e import/export.

## Archivos
- `dialog.py` — mixin `_open_pending_batches` (lista de lotes, detalle de cuentas, nuevo/renombrar/borrar/mover/recuperar; sin colas desde v3.21)
- `resume.py` — listados, load draft, runtime, finish/fail
- `transfer.py` — export/import JSON
- `manage.py` — nuevo lote vacío, renombrar, listar cuentas, borrar, recuperar del histórico (feat-uc2-21)
- `pause.py` — pausar cuentas sin empezar: las mueve a un lote DRAFT `<nombre>_PAUSA` (feat-uc2-18); con `target_name` y `suggest_split_name` mueve a un lote con nombre elegido (feat-uc2-19)

- `restart.py` — `restart_batch`: reinicia un lote ejecutado (URLs/cuentas a PENDING, lote a IMPORTED; no toca archivos; feat-run-37; botón Reiniciar… de `dialog.py`, feat-run-38). Test: `tests/gui/test_restart_batch.py`

- `extract.py` — `extract_completed_accounts`: saca las cuentas COMPLETED de un lote PARTIAL a un lote nuevo AWAITING_RENAME conservando banderas, URLs e historial (feat-run-33). Test: `tests/gui/test_extract_completed.py`

`execution_report.py` · modal *Informe de ejecución* (telemetría de un lote; abre desde el menú Lote y el clic derecho del modal de lotes).

## Habla con
`gui/run` (ejecutar / renombrar). El servicio `gui/queue` ya no se usa desde la GUI.

## Tests
`tests/gui/test_resume.py`, `tests/gui/test_transfer.py`, `tests/gui/test_pause_accounts.py`, `tests/gui/test_batch_management.py`
