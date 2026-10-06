# Tarea_v2_2_gui_ux — Mejoras GUI v2.2 (menú, editor, log, toolbar, modales, estados)

## Descripción
Implementación de mejoras UX en la GUI Tkinter v2.1.x:
1. Menú Batch: eliminar entrada duplicada "Organize stories…"
2. Editor: paste/clear en Owner Id, First Post Date, Path; textos i18n; layout estable
3. Buscador de lote: add paste button; ancho limitado
4. Modal "Run status": filtros (Warning/Error), colores en logs, botones
5. Toolbar: add botón Stories con icono custom; posicionamiento correcto
6. Cambios generales: Esc cierra modales, menú contextual en todos inputs, reglas de habilitación de botones

## Estado
- Creada: 2026-10-06
- Rama: `v2/gui-ux-v2.2`
- Versión destino: v2.2.0

## Cambios principales

### 1. Menú — eliminar duplicado
- Archivo: `chrome/menubar.py:158-173`
- Acción: Eliminar líneas 169-172 (segunda entrada "Organize stories…")

### 2. Editor — paste/clear, i18n, layout
- Archivo: `editor/panel.py`
- Campos: Owner Id, First Post Date, Path con paste/clear buttons
- i18n keys: `label.owner_id`, `label.first_post_date`, `label.path`, `label.new_account_frame`, `label.catalog_frame`
- Layout: `url_actions` frame con rowspan para posición constante
- Context menu: bind_edit_context_menu en owner/fecha/path

### 3. Buscador de lote — paste button
- Archivo: `batch_accounts/panel.py:123-147`
- Acción: add `_paste_batch_filter` handler y botón
- Width: ~30 chars, sin sticky="ew"

### 4. Modal "Run status" — filtros y colores
- Archivo: `shared/log_window.py`
- Helpers: `classify_log_level(line)` en `shared/helpers.py`
- Filtros: Warning, Error (toggle), estado conservado
- Colors: warning=#b58900, error=red
- Botones: Clear, Warning, Error, Close
- i18n keys: `log.warning`, `log.error`, `log.close`

### 5. Toolbar — botón Stories
- Archivos: `shell/app.py`, `shared/icons.py`
- Icono: `stories.png` (generar con Pillow o rasterizar manual)
- Posición: después de `rename_manual_button`
- Estado: siempre habilitado, fuera de `_set_descendants_enabled`

### 6. Cambios generales
- **Esc cierra modales**: helper `bind_escape_close()` en `shared/`
- **Context menu**: `bind_edit_context_menu` en todos Entry/Combobox/Text
- **Estados de botones**: función pura `compute_toolbar_state()` en `shared/helpers.py`
  - Save/Update: ≥1 cuenta + sin ejecución
  - Run: ≥1 cuenta + pedir guardado si no existe
  - Pause/Stop: solo en ejecución
  - Rename: solo con `batch_ready_for_rename`
  - Stories: siempre

## Testing
- `test_log_window.py`: `classify_log_level`, filtros, tags
- `test_i18n.py`: paridad de claves nuevas
- `test_helpers.py`: matriz `compute_toolbar_state`
- `test_editor.py`: paste/clear, i18n frames
- `test_log_window.py`: Esc binding
- `python -m pytest -q`: suite completa

## Verificación manual
```bash
python -m ig_orchestrator gui
# 1. Menú Batch: una sola "Organize stories…"
# 2. New account/Update: botones no se desplazan
# 3. Paste/clear en owner/fecha/path; anchos correctos
# 4. Buscador lote: paste + ancho limitado
# 5. Run status: filtros, colores, botones
# 6. Botón Stories en toolbar
# 7. Esc cierra cada modal
# 8. Clic derecho→Pegar en todos inputs
# 9. Estados de botones (nuevo batch, agregar, guardar, ejecutar, pausar)
```

## Archivos afectados
- `chrome/menubar.py` — eliminar duplicado
- `chrome/toolbar.py` — refactor estados, Stories button
- `chrome/statusbar.py` — reglas de habilitación proceso
- `editor/panel.py` — paste/clear fields, i18n, layout estable
- `editor/text_edit.py` — helpers paste/clear reutilizables
- `batch_accounts/panel.py` — paste button en filtro
- `shell/app.py` — toolbar Stories button
- `shared/log_window.py` — filtros, colores, botones
- `shared/icons.py` — registro icon `stories`
- `shared/helpers.py` — `compute_toolbar_state`, `bind_escape_close`, `classify_log_level`
- `shared/locales/{es,en}.json` — claves i18n nuevas
- `settings/dialog.py` — bind_edit_context_menu en campos
- `batches/dialog.py` — bind_escape_close
- `batch_accounts/problem_urls.py` — bind_escape_close
- `run/rename.py` — bind_escape_close
- `stories/dialog.py` — bind_escape_close
- `tests/gui/test_*.py` — nuevos tests

## Notas
- `gui/locales` y `gui/static` son duplicados obsoletos; no modificar
- `pause.png` ya existe en `shared/static/icons/`; generar `stories.png` en mismo estilo
- No cambiar APIs existentes; refactors mínimos en Username paste/clear
- `batch_ready_for_rename` existente en `run/controller.py`, `batches/dialog.py`, etc.
