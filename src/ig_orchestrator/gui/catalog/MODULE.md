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
- editor: `self._load_catalog` rellena username y llama
  `_apply_username_identity` (resetea checks si el username cambió).
  Pegar en el buscador (botón, menú, Ctrl+V) escribe el texto en
  Username y selecciona el match en lista/árbol.
- settings: colores (`save_color` → `_refresh_catalog`)

## No debe
Lanzar `run_continue` ni mutar `self.accounts` (salvo pintar tag in_batch).

## Tests
`tests/gui/test_catalog.py`, `tests/gui/test_catalog_tree.py`

## Catálogo avanzado (v3.12)

El árbol usa `selectmode="extended"`. `gui/library/catalog_advanced.py` (mixin) aporta ficha de cuenta, mover varias cuentas (`FsOperationService.plan_move_accounts`), arrastrar y soltar (`_drop_on_catalog_tree`), abrir carpeta/copiar ruta y la papelera (`library/trash.py`).
