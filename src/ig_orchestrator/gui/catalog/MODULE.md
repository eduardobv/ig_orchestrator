# Módulo: gui/catalog

## Propósito
Panel izquierdo: lista/árbol de cuentas históricas.

## Archivos
- `panel.py` — mixin widgets + handlers
- `service.py` — lectura/escritura SQLite (sin Tk)
- `colors.py` — paleta
- `tree.py` — `build_catalog_tree` (`hide_deleted`/`hide_inactive` ocultan carpetas `-Deleted`/`-Inactive` solo en el árbol; `folder_suffix_kind`, `path_is_hidden`). Casillas en `panel.py` (`_on_catalog_suffix_toggle`), ajustes `ui.catalog_show_deleted`/`ui.catalog_show_inactive`.

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

## Colores y ventanas (v3.14)

`colors.load_catalog_colors` fuerza que *Eliminada* use el color de *Disabled*. Todas las ventanas se centran con `gui/shared/window_position.py` (`install_auto_centering`).

## v3.16

Menú de carpeta: *Eliminar carpeta vacía…* (`fsops_actions._catalog_delete_empty_folder`). Papelera con caducidad y «quitar del catálogo» (`catalog_advanced._open_trash_dialog`). Barra de estado: `StagingPanelMixin._refresh_staging_hint`.
  Si el texto es un Owner ID (solo dígitos, ≥5; `parse_owner_id`), el filtro busca por
  id en **todo** el catálogo (`find_entries_by_owner_id`, incluye ARCHIVED/DELETED) y
  sustituye la lista filtrada por las coincidencias (feat-uc2-20).

## Tests
`tests/gui/test_catalog_owner_search.py`
