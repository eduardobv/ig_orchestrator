# T2.D6 — La GUI usa orchestrator_gui.sqlite

## Objetivo

Arrancar la GUI contra el fichero nuevo, con catálogo importado y cero lotes.

## Hecho

* `_run_gui` llama `init_gui_database` y, si el catálogo está vacío, importa
  `account_history` del SQLite v1 en **solo lectura**.
* `run_continue` usa `prepare_sqlite` (no aplica el esquema v1 sobre el GUI).
* El subproceso de ejecución recibe `SQLITE_DB_PATH` = fichero GUI.
* No se generan reportes Markdown en esquema GUI (la GUI no los usa).
* El diálogo Lotes sigue siendo el de v1.31.0; lee/escribe vía vistas.

## Fuera de alcance

* Rediseño visual de la GUI (T2.1+).
