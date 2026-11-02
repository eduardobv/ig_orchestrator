# telemetry (v4.6.0)

@MODULE.md

- Solo **observa**: un fallo aquí nunca debe romper el lote.
- No guarda textos de descripciones (solo clase y longitud).
- Para analizar rendimiento, consulta `url_job_attempts`, `bot_message_events` y `run_wait_events` en la base de la GUI.
- Informe de ejecución (v4.10.0): `report.py` + modal `gui/batches/execution_report.py`; botón de purga en *Configuración > Ejecución*.
