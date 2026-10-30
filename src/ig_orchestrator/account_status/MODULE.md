# account_status

Comprobación anónima del estado de las cuentas de una carpeta del catálogo (feat-uc2-26, v4.13.0).

* `schema.py` · tablas aditivas `account_check_runs` y `account_check_results`; `ensure_account_status_schema` se llama desde `db/gui_migrations.py`.
* `checker.py` · `check_account` / `classify_profile`: `profile_id` en el HTML = `AVAILABLE`; 200 sin él o 404 = `UNAVAILABLE`; 429 = `rate_limited`; red u otro HTTP = `UNKNOWN`. El `fetcher` se inyecta (tests sin red).
* `service.py` · `AccountStatusService` (crear análisis desde `FsOperationService.accounts_under`, resultados, resumen, `refresh_paths` tras mover) y `run_checks` (espera entre cuentas, parada manual con `threading.Event`, parada en el primer 429, solo procesa PENDING/UNKNOWN para poder reanudar).

Reutilización (v4.14.0): `create_run(folder_id, reuse_hours)` copia de otros análisis la respuesta `AVAILABLE`/`UNAVAILABLE` más reciente dentro de la ventana (`reuse_hours(conn)` lee `accountcheck.reuse_hours`, 48 h) y la marca con `source_run_id`; `run_checks` solo procesa PENDING/UNKNOWN, así que no las consulta; `force_reanalysis` las devuelve a PENDING.

`CheckResult.moved` / `destination`: se calculan comparando `rel_path` (donde se encontró la cuenta al analizar, no se reescribe) con la ruta actual de `catalog_accounts`, así que detectan también movimientos hechos fuera del análisis.

La GUI vive en `gui/library/account_status_dialog.py`; los hilos de trabajo (comprobación, planificación y ejecución del movimiento) abren su propia conexión y nada de disco se hace en el hilo de Tk; la vista previa es hija de la modal. Mover usa `FsOperationService.plan_move_accounts` (vista previa, diario y deshacer existentes). No guarda nada fuera de la base de la GUI.
