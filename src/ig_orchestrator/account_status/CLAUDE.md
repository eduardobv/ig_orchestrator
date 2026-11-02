# account_status (v4.13.x–v4.14.0)

@MODULE.md

Reglas rápidas:
- Menú: clic derecho en carpeta del catálogo > *Comprobar estado de las cuentas…* y *Catálogo > Revisar análisis de estado…* (`gui/library/account_status_dialog.py`).
- Comprobación anónima: `profile_id` en `instagram.com/<cuenta>/`; espera `run.accountcheck.interval_seconds` entre cuentas; **para solo en el primer 429**.
- Los análisis se guardan en `account_check_runs` / `account_check_results`; mover cuentas usa `FsOperationService.plan_move_accounts`.
- **El disco nunca se toca en el hilo de Tk**: los hilos de trabajo abren su propia conexión.
- Reutilización (v4.14.0): un análisis nuevo copia las respuestas de otros análisis de las últimas `accountcheck.reuse_hours` (48 h, *Configuración > Catálogo*) con `source_run_id` y no las vuelve a consultar; la casilla *Re-analizar…* fuerza la consulta.
