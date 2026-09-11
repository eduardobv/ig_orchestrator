# Módulo: gui/draft

## Propósito
Modelo en memoria del lote en edición y persistencia DRAFT.

## Archivos
- `models.py` — `AccountDraft`, `BatchDraft`
- `service.py` — validar, normalizar URLs, `save_batch_draft`

## No debe
Importar Tk.

## Tests
`tests/gui/test_draft.py`, `tests/gui/test_editor.py` (validación)
