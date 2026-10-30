# feat-uc1-10 · Renew: volver a empezar el renombrado de una cuenta existente (v4.17.0)

## Objetivo
Poder tratar como «nueva» a efectos de renombrado una cuenta que ya existe en el catálogo y en disco pero cuyos ficheros no tienen el formato final.

## Resultado de la implementación
* Casilla **Renew** en el editor (entre *Update* y *Priority*), excluyente con *New account* y *Update*; solo pide la **Fecha del primer post**. Owner Id y ruta se mantienen.
* `renaming/planner.py: process_renew_tree`: por carpeta, une los ficheros solo-id (`^\d{10,}\.(jpg|jpeg|mp4)$`) de la carpeta de la cuenta en `G:` con los descargados y los renombra como cuenta nueva (bloques entre el primer post y `startNowDate`). Los de `G:` se renombran en sitio, los descargados se mueven después. Otros nombres se ignoran; un descargado con id ya presente → `_duplicated`.
* `renaming/service.py`: `NewAccountSpec.renew`, estado `RENEW`, omisiones con motivo (sin carpeta registrada / `G:` inaccesible / sin Owner Id), guarda `catalog_accounts.start_init_date` y reescanea la cuenta.
* Persistencia sin cambios de esquema: `is_new_account=0` + `rename_start_init_date` (sin owner/ruta); se infiere al recargar, y se exporta/importa como `is_renew`.
* Tests: `tests/renaming/test_renew_rename.py`, `tests/gui/test_renew_batch.py`.

## Decisiones / no hecho
* Los ficheros de `G:` que **ya** tienen formato no se tocan ni se usan como referencia de fechas (aviso); mezclar ambos no está soportado.
* Renew no usa el índice de la app: necesita `G:` conectado. El renombrador externo `sc2` ignora las cuentas Renew.
* Si la cuenta no tiene carpeta en las descargas, se omite (no se renombra solo `G:`).
* No probado en la GUI abierta ni sobre `G:` real.
