# feat-uc2-28 · Biblioteca completa recordada y carpetas existentes (v4.15.0)

## Objetivo
Que el catálogo arranque completo sin pulsar *Mostrar biblioteca completa*, y que crear una carpeta cuyo nombre ya existe en el disco (vacía, sin fila en el catálogo) la agregue en vez de fallar.

## Resultado de la implementación
* `ui.catalog_show_archived` (por defecto 1) se lee al arrancar y se guarda al cambiar el menú.
* `FsOperationService.existing_unregistered_folder` / `adopt_folder`: solo registran filas (`ensure_folder_rows`), sin tocar el disco; usado por *Nueva carpeta aquí…* y por el selector de destino.
* Test en `tests/library/test_fsops.py`.

## No hecho
* No se ofrece «reemplazar»: implicaría borrar la carpeta existente.
* La sincronización no registra carpetas vacías por sí sola.
* No probado en la GUI real ni sobre `G:`.
