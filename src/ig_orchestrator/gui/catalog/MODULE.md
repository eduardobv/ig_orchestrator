# Módulo: gui/catalog

## Propósito
Panel izquierdo: lista/árbol de cuentas históricas.

## Archivos
- `panel.py` — mixin widgets + handlers
- `service.py` — lectura/escritura SQLite (sin Tk)
- `colors.py` — paleta
- `tree.py` — `build_catalog_tree`

## Estado que lee / escribe (en App)
Lee: `connection`, `catalog_entries`, `catalog_view_mode`, `catalog_colors`, `accounts`
Escribe: `username_var`, selección de lista/árbol, `catalog_entries`

## Habla con
- editor: `self._load_catalog` rellena username
- settings: colores (`save_color` → `_refresh_catalog`)

## No debe
Lanzar `run_continue` ni mutar `self.accounts` (salvo pintar tag in_batch).

## Tests
`tests/gui/test_catalog.py`, `tests/gui/test_catalog_tree.py`
