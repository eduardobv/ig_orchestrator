# T2.D1 — Seguridad v2: WAL, path GUI y rollback a v1.31.0

## Objetivo

Preparar el terreno de v2 sin cambiar el comportamiento de la GUI v1 ni tocar
`data/orchestrator.sqlite`.

## Hecho

* Tag `v1.31.0` ya existía.
* Rama `v2/orchestrator`.
* Copia local `data/old/orchestrator.v1.31.0.sqlite` (gitignored).
* `connect()` activa WAL, `synchronous=NORMAL` y `temp_store=MEMORY`.
* Setting opcional `SQLITE_GUI_DB_PATH` (default `data\orchestrator_gui.sqlite`).
* La GUI **sigue** abriendo `SQLITE_DB_PATH` hasta T2.D6.

## Fuera de alcance

* Diálogo Lotes / ejecuciones (importar/exportar): no se toca.
* Importador de catálogo y cambio de path en `_run_gui`.
