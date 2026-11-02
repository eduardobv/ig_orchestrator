# db — persistencia y trazabilidad

@MODULE.md

- v1 (`orchestrator.sqlite`) y v2 GUI (`orchestrator_gui.sqlite`) no se mezclan. **No escribir en v1 desde la GUI.** v1 es el rollback y lo usa la CLI.
- Los subpaquetes `v1/`, `v2/`, `v2/adapters/`, `v2/catalog/` tienen su propio `MODULE.md`.
- Esquemas aditivos de módulos (`telemetry`, `account_status`…) se registran desde `gui_migrations.py`.
- `input_batches.batch_name` es único y no se reutiliza. `account_history` conserva usernames globales sin repetir entre lotes.
- Tests de repositorios con SQLite temporal; nunca commitear bases reales de `data/`.

## Cada URL debe guardar

URL original · tipo (`POST`, `REEL`, `STORY`, `HIGHLIGHTS`, `UNKNOWN`) · origen (`GENERATED_STORY` / `INPUT_URL`) · estado (`PENDING`, `SENT_TO_BOT`, `WAITING_DOWNLOAD`, `COMPLETED`, `FAILED_FINAL`…) · mensaje enviado al bot · error original y su tipo · contador de reintentos · archivos asociados · timestamps.
