# feat-uc2-24 · El árbol conserva lo expandido al refrescar

## Objetivo
Evitar que cada refresco del árbol del catálogo (casillas, mover carpeta, crear…) lo comprima; y que -Deleted/-Inactive estén ocultas por defecto.

## Resultado de la implementación
* `gui/catalog/panel.py`: `_refresh_catalog_tree` guarda los ids `folder:*` abiertos (`_open_catalog_folders`) y el scroll antes de reconstruir, y los restaura después; si hay cuenta enfocada, `see()` la deja visible como antes.
* `gui/shell/app.py`: valores por defecto de `ui.catalog_show_deleted` / `ui.catalog_show_inactive` = «0» (ocultas). Quien ya guardó su elección la conserva.
* Prueba: `test_open_catalog_folders_lists_only_expanded_folder_nodes` (se omite sin pantalla).

## No se hizo
* Una carpeta renombrada o movida pierde su estado abierto (su id cambia). El estado no se guarda entre sesiones. No probado visualmente.
