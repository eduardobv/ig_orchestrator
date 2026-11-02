# cli — flujo de ejecución

@MODULE.md

## Dry-run (`--dry-run`)

Lee `.env`, inicializa SQLite si falta, parsea y valida el JSON, importa el lote y simula el procesamiento: no envía a Telegram, no mueve archivos, no crea carpetas, genera un run simulado en SQLite.

## Real (`--run`, o sin `--dry-run`)

1. Carga `.env`, inicializa SQLite, valida el JSON.
2. Rechaza el JSON si `batch_name` ya existe (sugerir `run_continue`).
3. Importa el lote nuevo y registra usernames en `account_history`.
4. Ordena en memoria (ver `orchestration/CLAUDE.md`).
5. Arranca Telethon con la sesión `TELETHON_SESSION_NAME`.
6. Procesa el lote (dos barridas si `processing.stories_first`, defecto; si no, cuenta entera y siguiente).
7. Envía URLs al bot, espera descargas, mueve archivos.
8. Aplica reintentos para errores temporales.
9. Genera el reporte Markdown.
10. Si `POST_PROCESS_ENABLED=true` y sin fallo de infraestructura, ejecuta el post-proceso.

`run_continue --batch-id N` / `--batch-name X` procesa desde SQLite sin reimportar el JSON.

Tras importar un lote real se respalda el JSON en `config/bkp` y `batch.json` queda limpio (URLs fuera, metadata intacta).

## Logs y reportes

- Cada invocación usa **una sola** carpeta `logs/YYYYMMDD_HHMMSS`, fijada al inicio; cuentas, lotes unidos y reintentos escriben en ella.
- `logs\app.log` (global) y `logs\YYYYMMDD_HHMMSS\username.log` (por cuenta).
- Reporte: `REPORTS_FOLDER\run_YYYYMMDD_HHMMSS.md`.
- `--run` siempre importa un lote nuevo; `run_continue` y los joins reutilizan los existentes.
