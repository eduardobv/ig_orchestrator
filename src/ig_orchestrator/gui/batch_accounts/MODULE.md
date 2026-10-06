# Módulo: gui/batch_accounts

## Propósito
Tabla “Cuentas del lote actual”, progreso runtime y diálogo de URLs problemáticas.

## Archivos
- `panel.py` — treeview, filtro, sort, eliminar, guardar selección
- `progress.py` — poll de estado, menú contextual, completar cuenta
- `problem_urls.py` — completed/retry/failed + abrir carpeta

## Habla con
- editor: al seleccionar fila, `_load_selected_row` hidrata el username
  con `_apply_username_identity(..., hydrate=True)` y luego los checks
- run: `runtime_progress`, fail/complete manual
- batches/resume: `get_account_runtime_progress`, `list_account_problem_urls`

## Tests
`tests/gui/test_batch_accounts.py`, parte de `tests/gui/test_resume.py`
