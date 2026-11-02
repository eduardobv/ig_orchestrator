# telegram — conversación con el bot y descargas

- **`cryptg` obligatorio** (v4.4.0) para el rendimiento. Las respuestas del bot llegan por eventos, con sondeo de respaldo.
- Se ignoran los mensajes del bot con id menor que el enviado.

## Fin de la espera (v4.8.0)

Termina por `EXPECTED_COUNT`: nombres únicos ≥ items anunciados, o descripción, o silencio breve de 2,5 s (ya no 10 s de silencio). Primera respuesta: 30 s (reel/post/story/error) o 75 s (carrusel, `/p/`, highlights); después, plazo de 120 s renovado por cada mensaje.

## Descarga (v4.4.1)

Una descarga por `(nombre, tamaño)`; las miniaturas solo como respaldo; en paralelo (`TELEGRAM_PARALLEL_DOWNLOADS`); carpeta propia opcional (`TELEGRAM_DOWNLOAD_TEMP_FOLDER`); vigilante de carpeta apagado por defecto (`TELEGRAM_WATCHER_FALLBACK`).

## Reels > 50 MB (v4.5.0, `large_file.py`)

El bot responde `error_file_too_large_link` + URL; se descarga directo como `<media_id>.mp4`. Fallo → `FILE_TOO_LARGE_DOWNLOAD_FAILED` (reintentable).

## Stories (v4.11.0)

El bot responde con miniaturas y, con 1-2 items, un 2.º mensaje con los adjuntos; con 3+ solo miniaturas. En `STORY` solo cuentan como items las miniaturas sin nombre, y se esperan los adjuntos (`run.bot.story_attachment_wait_seconds`).

## Bot sin respuesta (v4.16.0)

La lógica de modo espera está repartida con `orchestration/url_job_processor.py`: ver `orchestration/CLAUDE.md`. Aquí: `BotConversationResult.late_results`, atribución por `reply_to`.

Los patrones de error del bot (`bot_response_parser.py`) y su política de reintento están en `orchestration/CLAUDE.md`. Los tests nunca usan Telegram real.
