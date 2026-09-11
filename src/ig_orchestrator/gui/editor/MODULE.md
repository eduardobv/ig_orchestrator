# Módulo: gui/editor

## Propósito
Panel de username, stories, nueva cuenta / update, URLs.

## Archivos
- `panel.py` — mixin
- `text_edit.py` — clipboard y menú contextual

## Habla con
- catalog: combobox de usernames, `save_new_account_to_catalog`
- draft: `AccountDraft` / `inspect_account_draft` / `normalize_url_lines`
- batch_accounts: `_upsert_account` escribe `self.accounts` y refresca tabla

## Tests
`tests/gui/test_editor.py`, `tests/gui/test_text_edit.py`
