# orchestration — orden, reintentos y ajustes de ejecución

## Orden de procesamiento del lote (`processing.stories_first`, v4.3.0)

1. **Barrida de stories:** todas las cuentas con stories pendientes; primero las de *prioridad* (rango 1, 2…), después por orden de alta en el lote. Cuentas solo-stories primero; las mixtas quedan `INCOMPLETE` hasta la barrida 2.
2. **Barrida de posts/reels/highlights:** de la cuenta con menos URLs pendientes a la que más; empate → más reels; empate → menos posts; empate → cuenta ya existente antes que nueva; empate → orden del lote. Al terminar → `COMPLETED`.

Modo legado (`stories_first` apagado): cuenta entera y siguiente.

## Reintentos

- No son inmediatos mientras queden URLs nuevas. Cola global al final del lote (`run.retry.global_queue`, v4.9.0), ordenada por `next_retry_at`. Stories generadas primero, URLs manuales después.
- Backoff por defecto: 90, 180, 360, 720, 900 s. Tras `MAX_RETRIES` → `FAILED_FINAL`.
- `STORY`: máximo **2 reintentos** (si `MAX_RETRIES` es menor, manda el menor).
- `NO_BOT_RESPONSE`: máximo 3 (`run.retry.no_response_max`).
- `Media not found or unavailable`: máximo 3 aunque `MAX_RETRIES > 1`, y solo si el post sigue existiendo. Antes de reintentar se consulta la página pública del post (sin login, `post_availability.py`): `PolarisErrorRoot` + `httpErrorPage` = ya no existe → `FAILED_FINAL` tipo `MEDIA_REMOVED`; página normal (`og:title`) o indeterminado (muro de login, 429, red caída) → se reintenta. Solo posts/reels.

### Errores definitivos (no reintentar)

```
We're sorry, we couldn't find that.
Stories for {username} not found          # se detecta por patrón: {username} cambia
We can't get stories from a private account (instagram limit)
```

En respuestas mixtas se conservan todos los videos y fotos; un documento sin nombre no invalida fotos sin nombre.

### Errores reintentables

```
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable
NO_BOT_RESPONSE                           # sin mensaje ni archivo antes del timeout
```

## Ajustes de ejecución (`run.*`, v4.7.0)

Viven en `app_settings`, editables en *Configuración > Ejecución*; precedencia GUI > `.env` > defecto (`run_settings.py`). **Una opción nueva de la descarga debe añadirse a `RUN_SETTING_SPECS` y a los locales** (`gui/locales`).

## Pausa entre URLs y bot mudo (v4.16.0)

`run.bot.between_urls_seconds` (2 s) espacia los envíos. Tras una URL sin respuesta, la siguiente espera `run.bot.stall_probe_delay_seconds` (10 s); si tampoco responde, modo espera sin enviar más (barra de estado de la GUI, marcador `[GUI_BOT_STATUS]`) hasta que el bot conteste, y se recogen las dos respuestas (`BotConversationResult.late_results`, atribución por `reply_to`). `run.bot.stall_enabled` lo desactiva. Código: `url_job_processor.py` y `telegram/bot_conversation_service.py`.

## Respaldo HTTP y bot caído (v4.20.0)

`AccountOrchestrator` y `BatchOrchestrator` reciben `fallback=` (el coordinador de `http_fallback/`, duck-typed para evitar ciclos). Tras cada intento del pase principal llaman a `after_attempt`; si pide aparcar la cuenta, el bucle de la cuenta se corta. `BatchOrchestrator._process_http_phase` (antes de la ronda de reintentos) corre el modo final. Con HTTP o bot caído activos, `cli/main.py` apaga el modo espera sin límite de v4.16.0. Detalle: `http_fallback/CLAUDE.md`. Ajustes `run.http.*`, `run.night.*`, `run.botdown.*`, `run.httpsession.*` (tipos nuevos `text`, `secret`, `list`, `time` en `RunSettingSpec`).

## Post-proceso

`post_processing.py` (`POST_PROCESS_ENABLED`); al final del lote real se limpian `telegram_media*` en la raíz y `*_1.mp4` duplicados en `reels\` (`filesystem/batch_cleanup.py`).
