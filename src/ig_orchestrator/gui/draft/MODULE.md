# Módulo: gui/draft

## Propósito
Modelo en memoria del lote en edición y persistencia DRAFT.

## Archivos
- `models.py` — `AccountDraft`, `BatchDraft` (`priority: int = 0`)
- `priority.py` — ranks exclusivos y orden de la tabla
- `service.py` — validar, normalizar URLs/username, `save_batch_draft`

## No debe
Importar Tk.

## Tests
`tests/gui/test_draft.py`, `tests/gui/test_editor.py` (validación)
