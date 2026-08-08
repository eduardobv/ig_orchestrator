# v1.27.2 - Patch - Catálogo: cuenta exacta primero en el grupo de carpeta

## Objetivo

Tras el match exacto del buscador (v1.27.1), el listado de peers de la misma
carpeta (`field1`) dejaba la cuenta buscada mezclada en el orden del catálogo.
Había que buscarla a ojo entre muchas hermanas.

## Cambio

En `filter_catalog_entries`, cuando hay match exacto con `destination_path`:

1. La cuenta buscada va **siempre primera**.
2. El resto de peers de la misma carpeta mantienen su orden original relativo.

## Archivos

* `src/ig_orchestrator/gui/account_catalog_service.py`
* `tests/test_gui_services.py`
* `README.md`, `PLAN.md`, `tasks/task-gui.md`, `CHANGELOG.md`

## Pruebas

* `python -m pytest -q tests/test_gui_services.py -k catalog_filter`
* `python -m pytest -q tests/test_package_smoke.py`
