# feat-uc2-25 · Cuentas privadas, OwnerId en el editor, aviso sin G:, ficha copiable y mejoras de la GUI

## Objetivo
Once mejoras pequeñas pedidas juntas: URLs de cuentas privadas, OwnerId visible, aviso al renombrar sin G:, ordenar la tabla de cuentas del lote, clic derecho reorganizado, ficha copiable/editable, ruta con sugerencias, nombre de lote más ancho, scroll permanente del catálogo, copiar ruta de carpeta y Normalizar oculto.

## Resultado de la implementación
* Ver la lista detallada en `CHANGELOG.md` (v3.25.0).
* Cuentas privadas: detección por longitud del shortcode (>14; los públicos tienen 11). Se bloquea el alta con aviso y se ofrece marcar la cuenta. Marca en `catalog_accounts.is_private` (columna añadida en caliente) y texto morado en el catálogo.
* Ruta con sugerencias: `rank_destination_paths` (puro, probado) + `PathSuggestEntry`.
* Pruebas: `tests/gui/test_feat_uc2_25.py`.

## No se hizo
* La detección de privadas solo actúa en el editor (no en importaciones de JSON ni en `--run`).
* El username de la ficha reutiliza el flujo de cambio de username existente (requiere G: conectada).
* Normalizar no tiene opción para volver a mostrarlo desde la GUI.
* No probado visualmente con G: realmente desconectada.
