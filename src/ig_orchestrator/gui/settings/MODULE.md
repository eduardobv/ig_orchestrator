# Módulo: gui/settings

## Propósito
Diálogo Configuración: idioma, ejecución (`run.*`, incluye stories_first), colores, notify, purge.

## Archivos
- `dialog.py`
- `run_tab.py` (pestaña «Ejecución»: claves `run.*` de `orchestration/run_settings.py`; valida antes de guardar y solo persiste los valores distintos del defecto/`.env`)

## Habla con
`app_settings` y `bot_errors` en SQLite GUI. Recarga catálogo al cambiar colores.
Cambio de idioma reinicia el proceso GUI.

## Tests
Cubierto indirectamente; helpers de notify/purge en `gui/shared/helpers.py`.
