# T2.D7 — Vaciar ficheros descargados

## Hecho

* `purge_downloaded_files` / `maybe_purge_downloaded_files_for_batch`.
* `finish_batch` (tras COMPLETED) borra `downloaded_files` del lote si
  `retention.downloaded_files = on_complete`.
* Configuración de la GUI: botón para vaciar toda la tabla.
* Los estados de `batch_urls` no se tocan.
