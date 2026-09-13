# Módulo: gui/chrome

## Propósito
Cromado de ventana: menú, toolbar, barra de estado / consola.

## Archivos
- `menubar.py`
- `toolbar.py` — modo de lote, botones enable/disable
- `statusbar.py` — consola, status, enable/disable al ejecutar,
  `_set_status_tone` (idle / busy / success / warning / error)

Los botones de la toolbar se crean en `shell/app.py` `_build_widgets`.

## Tests
`tests/gui/test_theme.py`, `tests/gui/test_helpers.py`
