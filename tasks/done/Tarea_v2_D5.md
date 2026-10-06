# T2.D5 — Inserts de lote GUI en una transacción

## Objetivo

Registrar un lote con muchas URLs sin un `commit()` por fila.

## Hecho

* `create_gui_batch` / `replace_gui_draft_batch` con `executemany` de
  `batch_urls`.
* `create_batch` y `update_draft_batch` despachan al camino GUI si el
  esquema es v2.
* Test: 40 URLs + story en menos de 1 s, y `load_batch_draft` funciona.
