# telemetry

Mide cada intento de descarga para poder ver dónde se va el tiempo. Solo observa: un fallo aquí nunca rompe el lote.

## Piezas
* `trace.py` · `AttemptTrace` (en memoria, reloj monotónico inyectable): tiempos por fase desde el envío al bot, mensajes recibidos (`MessageEvent`), esperas (`WaitEvent`), motivo de salida y resultado. Se vuelca una sola vez al terminar el intento.
* `observer.py` · `RunObserver` (protocolo), `NullObserver` (base v1 o `TELEMETRY_LEVEL=OFF`), `SqliteObserver` (escribe en la base de la GUI), `build_observer` (elige uno y purga lo antiguo) y `install_flood_wait_capture` (convierte el log «Sleeping for Ns … flood wait» de Telethon en una espera `FLOOD_WAIT`).
* `schema.py` · tablas aditivas `url_job_attempts`, `bot_message_events`, `run_wait_events` (sin claves foráneas); `ensure_telemetry_schema` se llama desde `db/gui_migrations.py`.
* `report.py` · informe de un lote (`build_batch_report`, `report_to_markdown`, `attempts_to_csv`) con recomendaciones por reglas fijas; solo lee.
* `housekeeping.py` · `purge_telemetry(older_than_days=…, batch_id=…)`.

## Dónde se engancha
* `BotConversationService` crea la traza al enviar la URL, registra cada mensaje del bot, descargas y motivo de salida, y la devuelve en `BotConversationResult.trace`.
* `UrlJobProcessor` la completa (movimiento, resultado, `batch_id`) y llama a `observer.finish_attempt`.
* `cli/main.py` construye el observador con `TELEMETRY_LEVEL` y `TELEMETRY_RETENTION_DAYS`.

## Niveles
`OFF` no guarda nada; `ATTEMPTS` una fila por intento; `FULL` (defecto) además un registro por mensaje del bot.

## Privacidad
No se guarda el texto de las descripciones: solo clase y longitud. De los errores se guarda el código (máx. 120 caracteres).

## Campos de tiempo
Todos en ms. `t_first_*`, `t_last_media`, `t_description` cuentan desde el envío. `t_end_wait` = tiempo muerto desde el último mensaje hasta cerrar la espera. `t_download` = tiempo esperando las descargas tras el último mensaje (las descargas en paralelo se solapan con la recepción; el detalle por fichero está en `bot_message_events.download_ms`). `exit_reason`: `COUNT_REACHED`, `DESCRIPTION`, `GRACE` (modo `EXPECTED_COUNT`), `STABLE` (modo antiguo), `ERROR_TEXT`, `LARGE_FILE_LINK`, `DEADLINE_FIRST` (sin respuesta), `DEADLINE_TOTAL`, `SEND_FAILED`. `expected_items` = items anunciados por el primer mensaje del bot (miembros de álbum, o 1).
