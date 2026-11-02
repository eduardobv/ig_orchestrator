# http_fallback — descarga HTTP de posts/reels sin respuesta del bot (v4.20.0)

- Solo **posts y reels**; stories/highlights nunca. Endpoint privado `GET https://<api_host>/api/v1/media/<id>/info/` con `sessionid` (+`x-ig-app-id`). El `media_id` se decodifica del shortcode (`telegram/large_file.media_id_from_url`); no se carga la página.
- Cada elemento del carrusel → `<pk>.jpg|mp4` (mejor resolución) en la carpeta de descarga del bot; luego `UrlJobProcessor.process_http` (mismo flujo que una descarga del bot). Las URLs del CDN están firmadas y caducan: se descarga justo después de la llamada.
- `coordinator.py` es la máquina de estados: `after_attempt` (llamado por `AccountOrchestrator` tras cada intento), `run_final_mode` (llamado por `BatchOrchestrator._process_http_phase`), bot caído (`_bot_down_mode`), `download_job` (GUI manual). Contadores en memoria.
- Errores: 401/403 (o `login_required`/`checkpoint_required`) desactivan HTTP en la ejecución con `SESSION_ADVICE`; 429 pausa y a los N seguidos desactiva; 404 → deja el job como `MEDIA_NOT_FOUND_OR_UNAVAILABLE` (lo resuelve la política existente).
- La cookie nunca se escribe en logs ni mensajes. `manual.py` corre en un hilo con su propia conexión (la GUI no toca red ni disco en el hilo de Tk).
- Los tests usan clientes y reloj simulados; **nunca** Instagram ni Telegram reales.
