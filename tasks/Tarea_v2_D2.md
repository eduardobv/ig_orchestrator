# T2.D2 — Esquema GUI v2 vacío

## Objetivo

Crear `data/orchestrator_gui.sqlite` con diccionarios de estados/tipos,
`bot_errors`, `path_roots` y tablas de hecho vacías (cero lotes).

## Hecho

* `src/ig_orchestrator/db/schema_v2.sql` (`PRAGMA user_version = 100`).
* `init_gui_database` / `apply_gui_migrations`.
* Rechaza ficheros v1 (`user_version` 1–3) para no mezclar SQLite.
* Semilla de estados, tipos de publicación, errores del bot conocidos y
  settings de UI/notify/retention.
* Vista `v_all_statuses` para inspeccionar todos los diccionarios.

## Fuera de alcance

* Importar `account_history` (T2.D3).
* Cablear la GUI a este fichero (T2.D6).
* Diálogo Lotes / ejecuciones.
