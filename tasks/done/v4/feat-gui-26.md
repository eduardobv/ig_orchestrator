# feat-gui-26 · Iconos nuevos y botonera (v4.0.0)

## Objetivo
Spike y feat: ver si se pueden crear iconos mejores sin depender de descargas, y reorganizar la botonera.

## Resultado de la implementación
* Sí se pueden crear: `tools/gen_icons.py` dibuja PNG 32×32 RGBA con Pillow (CairoSVG no funciona aquí: falta `libcairo`). Fuentes alternativas gratuitas si se quieren otros: Lucide, Tabler Icons, Phosphor, Material Symbols (PNG 32 px, fondo transparente, registrar en `gui/shared/icons.py`).
* Ejecutar y Pausar/Reanudar comparten celda (`_sync_run_pause_buttons`); los dos botones se mantienen por dentro para no tocar la lógica de estados.
* Renombrar manual oculto (sigue en el menú); botón Pull nuevo; botones Copiar en el editor.
* Los iconos sustituidos están en `gui/shared/static/icons/_old/`.
* Pruebas: `tests/gui/test_feat_gui_26.py`.

## No se hizo
* Copiar en el buscador del catálogo ni en el filtro de cuentas del lote.
* Usar el icono combinado `play_pause.png` (queda como alternativa).
* Borrar la carpeta duplicada `gui/static/icons` (parece un resto sin uso).
* El icono de copiar se parece al de pegar en 24 px; ajustar si molesta.
