# feat-uc2-23 · Ocultar carpetas -Deleted / -Inactive en el árbol

## Objetivo
Poder despejar el árbol del catálogo de las carpetas `-Deleted` e `-Inactive` de forma rápida, sin menús, sin perder acceso a ellas al mover/copiar/crear.

## Resultado de la implementación
* Decisión: dos casillas encima del buscador (visibles solo en vista árbol) en vez de mover el botón de vista; además, las mismas opciones como casillas en el clic derecho de cualquier carpeta (el árbol no tiene un nodo propio para la raíz, la raíz `G:\4K Stogram` es una carpeta más). Ambos comparten las mismas variables.
* `gui/catalog/tree.py`: `build_catalog_tree(hide_deleted=, hide_inactive=)`, `folder_suffix_kind`, `path_is_hidden` (sufijos `-Deleted/-Delete`, `-Inactive/-Inactiva/-Inactivo`, cualquier nivel del camino; también carpetas vacías).
* `gui/catalog/panel.py`: fila de casillas (filas del grid desplazadas), `_on_catalog_suffix_toggle` persiste en `app_settings` (`ui.catalog_show_deleted`/`ui.catalog_show_inactive`, por defecto «1» = visibles, sin cambio de comportamiento). Con texto en el buscador no se oculta nada.
* Los selectores de carpeta (`gui/library/folder_picker.py`) no usan el árbol del catálogo: siguen listando todas. Locales es/en: `catalog.show_deleted`, `catalog.show_inactive`.
* Pruebas: 3 nuevas en `tests/gui/test_catalog_tree.py`. Suite: 595 + 1 intermitente del watcher (pasa aislado).

## No se hizo
* No se movió el botón de vista del catálogo a la botonera superior. No se ocultan en la vista de lista (la lista no muestra eliminadas). No probado visualmente en la GUI real.
