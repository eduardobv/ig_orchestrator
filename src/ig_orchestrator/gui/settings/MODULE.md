# Módulo: gui/settings

## Propósito
Diálogo Configuración: idioma, stories_first, colores, notify, purge.

## Archivos
- `dialog.py`

## Habla con
`app_settings` y `bot_errors` en SQLite GUI. Recarga catálogo al cambiar colores.
Cambio de idioma reinicia el proceso GUI.

## Tests
Cubierto indirectamente; helpers de notify/purge en `gui/shared/helpers.py`.
