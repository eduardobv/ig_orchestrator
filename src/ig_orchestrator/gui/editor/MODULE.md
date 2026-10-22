# Módulo: gui/editor

## Propósito
Panel de username, stories, nueva cuenta / update, URLs.

## Archivos
- `panel.py` — mixin
- `text_edit.py` — clipboard y menú contextual

## Habla con
- catalog: combobox de usernames, `save_new_account_to_catalog`;
  `_load_catalog` llama `_apply_username_identity`
- draft: `AccountDraft` / `inspect_account_draft` / `normalize_url_lines` /
  `normalize_username`
- batch_accounts: `_upsert_account` escribe `self.accounts` y refresca tabla;
  `_load_selected_row` hidrata flags con `hydrate=True`

## Identidad de username
Los checks Stories / New account / Update / Priority van ligados al
username normalizado (`strip`, quitar `@`, `casefold`). Si esa identidad
cambia (catálogo, pegar, combobox, limpiar Username) los checks vuelven
al estado inicial. Cargar una fila del lote hidrata los flags de esa
cuenta. Priority 1 es exclusivo: al agregar, esa cuenta queda primera y
cualquier otra con el mismo rank pasa a 0.

## Tests
`tests/gui/test_editor.py`, `tests/gui/test_text_edit.py`

## v3.25 (feat-uc2-25)
- `path_suggest.py` — `rank_destination_paths` (puro) y `PathSuggestEntry`: campo Ruta con sugerencias al escribir (contenedoras primero sin texto). Sustituye al combobox; `set_values(paths, containers)`.
- `panel.py` — `_block_private_urls` (URLs de cuentas privadas: avisa, no agrega y ofrece marcar la cuenta), `_refresh_owner_display` (etiqueta OwnerId junto al username), botón Normalizar creado pero sin empaquetar (`normalize_button`).
- Tests: `tests/gui/test_feat_uc2_25.py`.
