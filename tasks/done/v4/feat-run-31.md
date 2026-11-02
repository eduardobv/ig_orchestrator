# feat-run-31 · Descarga de respaldo por HTTP y detección de bot caído (v4.20.0)

## Objetivo
Que el lote no se quede parado cuando el bot no responde a posts/reels: descargarlos por la API web de Instagram con ritmo prudente, y distinguir «URL problemática» de «bot caído» con una URL de prueba.

## Resultado de la implementación
* Módulo `http_fallback/` + enganches en orquestadores, `UrlJobProcessor.process_http`, CLI, ajustes (34 nuevos), pestaña Ejecución y modal *Ver URLs…* (descarga manual). Ver `CHANGELOG.md` (v4.20.0) y `http_fallback/CLAUDE.md`.
* Decisiones del usuario: 2 intentos al bot, aparcar la cuenta tras 3 HTTP seguidas, modo final con prueba al bot cada 10 descargas, franja 00:00–06:00 a 5 min, bot caído = HTTP cada 2 min en bloques de 1 h (HTTP manda sobre la espera de 1 h, que queda para cuando no hay HTTP), 401/403 desactivan HTTP solo en esa ejecución, sesión en Ajustes (una sola), pausa solo en la llamada `info`.
* POC previa: `tasks/spikes/poc_ig_media_info/`.

## No se hizo / límites
* Varias sesiones con rotación; stories/highlights; guardar la descripción del post; columna «método» en el informe de ejecución (solo la tabla `http_downloads`).
* Contadores en memoria: al reanudar con `run_continue` empiezan de cero.
* Sin pruebas contra bot caído real, franja nocturna real, 429/403 reales ni vídeos por HTTP.
* Respuestas tardías del bot tras recuperarse (mensajes de sondas viejas) se mitigan con una espera de 15 s y el filtro `reply_to`; no hay garantía total.
