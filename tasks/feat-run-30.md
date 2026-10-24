# feat-run-30 · Spike v3: acelerar la descarga, observar la ejecución y configurar el lote (propuesta v4.4.0+)

> Estado: **SPIKE (revisión 3), sin código del proyecto tocado.** Incluye los resultados de una **prueba real contra el bot** (2026-10-24, 10 casos + 3 benchmarks de solo lectura). Pendiente de la sección 11 y de la orden para implementar.

## 1. Resumen ejecutivo

La prueba cambia el diagnóstico: **el bot no es el cuello de botella** en el caso normal (responde en 1-5 s). El tiempo se va en cómo descargamos:

| # | Causa (medida) | Efecto por item | Arreglo |
|---|---|---|---|
| C1 | Telethon **sin `cryptg`** ni `libssl`: cifra con AES en Python puro (`pyaes`) → **~175-240 KB/s** | Un reel de 2,3 MB tarda ~14 s en bajar | Añadir `cryptg` a las dependencias: **4,5× más rápido en serie y hasta 35× en paralelo** (medido) |
| C2 | El sondeo `iter_messages` cada ~0,5 s provoca **`FloodWait` de 11 s** de Telegram (Telethon duerme sin avisar), uno cada ~30 s de sondeo | 11-19 s ocultos por item lento | Sustituir el sondeo por eventos `NewMessage` (o sondear ≥ 1,5 s: sin flood en la prueba) |
| C3 | Se descarga **dos veces el mismo vídeo** (M1 y M2 son el mismo fichero con el mismo nombre) y también miniaturas de fotos que luego se descartan | Reel normal: 2 × 14 s | Descargar una vez por nombre de fichero y no bajar las miniaturas |
| C4 | Espera fija de **10 s** de «estabilidad» tras el último fichero | 10 s en cada item | Fin por conteo / descripción + gracia de 2-3 s |
| C5 | `error_file_too_large_link` no se reconoce → 300 s + 300 s + reintentos | Un reel grande puede costar > 30 min y no se descarga | Descarga directa por enlace (probado: **54,6 MB en 2,7 s**) |
| C6 | Reintentos bloqueantes por cuenta con espera de 90-900 s | Minutos por fallo, bloquean el lote | Cola global al final del lote |

Reconstrucción de un **reel normal** (38 s de mediana en tu base): bot 4 s + 2 descargas × 14 s + 10 s de estabilidad ≈ **42 s**. Con C1+C3+C4: bot 4 s + 1 descarga ≈ 1,5-3 s + gracia 2 s ≈ **7-9 s** (estimación a partir de las medidas; hay que confirmarla con la telemetría).

**Corrección a lo que se creía**: «si pasan 20 s sin respuesta, no responderá». En la prueba, un carrusel de 20 items y un highlight de 16 items **tardaron 31,7 s y 31,3 s** en dar la primera respuesta. Un plazo único de 30 s habría hecho fallar ambos (ver 7.3).

## 2. Línea base real (base `orchestrator_gui.sqlite`, 4 771 URLs con tiempos desde 2026-09-15)

Duración del **último intento** (`finished_at − started_at`; `started_at` se pisa en cada intento, por eso hace falta telemetría propia):

| Tipo / estado | N | p50 | p90 | máx |
|---|---|---|---|---|
| REEL completado | 3 138 | 38 s | 64 s | 500 s |
| POST completado | 989 | 35 s | 104 s | 834 s |
| STORY completada | 631 | 30 s | 70 s | 214 s |
| HIGHLIGHTS completado | 6 | 129 s | 245 s | 245 s |

Errores del bot en la base (43 587 URLs): `GEOBLOCK_REQUIRED` 173, `MEDIA_NOT_FOUND_OR_UNAVAILABLE` 116 (120 reintentos), `STORIES_NOT_FOUND` 34, `NOT_FOUND` 6, `PRIVATE_ACCOUNT_STORIES` 2.

## 3. Prueba real contra el bot (resultados)

Script independiente (fuera del repo, en el scratchpad de la sesión): no toca la base de la app ni mueve ficheros. Una URL cada vez, observando durante 20 s de silencio. Sesión de Telethon del usuario con su permiso; GUI cerrada. `t` = segundos desde el envío.

### 3.1 Mensajes y tiempos por caso

| Caso | Primera respuesta | Mensajes recibidos | Fin del contenido |
|---|---|---|---|
| Post inexistente | 1,4 s | 1 texto `Media not found or unavailable` | — |
| Post de 1 foto sin descripción | 1,4 s | foto (miniatura) + documento `.jpg` (248 KB) | sin mensaje de descripción |
| Reel normal (2,3 MB) | 3,8 s | **documento `.mp4` con nombre** (M1) + **el mismo documento** (M2, mismo nombre y tamaño) + texto (descripción) | 4,1 s |
| Carrusel 12 items | 3,3 s | álbum de 10 fotos + álbum de 2 fotos (0,75 s después) + 12 documentos `.jpg` + descripción | 7,7 s |
| Carrusel 20 items (fotos + 4 vídeos) | **31,7 s** | 2 álbumes de 10 (con los 4 vídeos como documentos con nombre) + 20 documentos + descripción | 39,8 s |
| Highlights (16 items) | **31,3 s** | 2 álbumes (10 + 6), todo **documentos `.mp4` con nombre**; sin adjuntos ni descripción | 31,3 s |
| Story con varios items (9) | 11,6 s | 1 álbum con fotos y vídeos; sin adjuntos ni descripción | 12,0 s |
| Reel grande (> 50 MB) | 4,7-6,7 s | **1 texto**: `error_file_too_large_link` + URL de 1 058 caracteres | — |

### 3.2 Hipótesis resueltas

| ID | Resultado |
|---|---|
| H1 (M1 trae N miniaturas y siguen N adjuntos) | **Confirmada.** Álbum de 12 → 12 adjuntos; álbum de 20 → 20 nombres únicos. Matiz: los **vídeos** aparecen en el álbum ya como documento con nombre y se repiten como adjunto (carrusel de 20: 24 entradas con nombre, 20 únicas). Las **fotos** del álbum son miniaturas sin nombre; el original llega como adjunto `.jpg` |
| H2 (la descripción llega la última) | **Confirmada** en los 4 casos con descripción (0-0,5 s después del último adjunto). No hay mensaje final si la publicación no tiene descripción (post de 1 foto) |
| H3 (> 10 items → varios álbumes) | **Confirmada.** Álbumes de máx. 10 items con `grouped_id` distinto, llegan con ≤ 0,75 s de diferencia |
| H4 (se descargan miniaturas/duplicados redundantes) | **Confirmada.** Reel normal: 2 descargas del mismo fichero. Carrusel 12: 12 miniaturas + 12 originales. Carrusel 20: 24 ficheros con nombre, 20 únicos |
| H5 (los items de ~6 min son reels grandes) | **Muy probable**, ver C5 (no se pudo cruzar con los logs de esas cuentas) |
| H6 (primera respuesta p99 < 30 s) | **Refutada**: 31,3 y 31,7 s en carrusel grande y highlights |

### 3.3 Atribución de respuestas (envío adelantado)

* `reply_to` es **siempre `None`** en las respuestas del bot (los 10 casos).
* Dos mensajes seguidos (reel + inexistente): el bot respondió primero el **error** (1,2 s) y después el reel (3,8 s): **orden de finalización, no de envío**.
* Dos URLs en un solo mensaje: respuestas en el orden de las URLs (reel y luego el error a los 5,2 s).
* Atribución posible sin `reply_to`: para un reel/post simple, el nombre del fichero **coincide con el shortcode decodificado** (verificado: `De1jzesDHug` → `4014272112143137696`, `DUmATXqE99I` → `3829749864197250888`). En carruseles los ficheros llevan el id de cada item (≠ id del post) y los errores no llevan URL: no es atribuible.
* **Conclusión: no hacer pipelining.** Además, con el bot respondiendo en 1-5 s y las descargas ya rápidas, la ganancia sería pequeña frente al riesgo.

### 3.4 Sondeo y `FloodWait` (solo lectura)

| Sondeo | Resultado en 75 s |
|---|---|
| `iter_messages(limit=50)` cada 0,5 s (como la app) | 79 consultas, media 0,44 s, **2 paradas de 11 s**; log de Telethon: `Sleeping for 11s on GetHistoryRequest flood wait` (a los 21 s y a los 52 s) |
| Cada 1,5 s | 45 consultas, media 0,18 s, **sin paradas** |
| Eventos `NewMessage` (medido en la sonda) | Llegan **0,05-0,5 s antes** que el sondeo detecta el mensaje; no consumen `GetHistory` |

Con 0,5 s de intervalo la app recibe un `FloodWait` aproximadamente cada 30 s: un item de 38 s tiene ~1 parada de 11 s. El log de la app no lo muestra porque Telethon duerme dentro de la llamada.

### 3.5 Velocidad de descarga (mismos mensajes, solo lectura)

| Motor | 2 vídeos (4,7 MB) serie | 2 vídeos paralelo | 6 fotos (5,6 MB) serie | 6 fotos paralelo |
|---|---|---|---|---|
| `pyaes` (hoy) | 24,4 s · 193 KB/s | 20,0 s · 236 KB/s | 27,8 s · 202 KB/s | 23,7 s · 237 KB/s |
| `cryptg` | 5,4 s · 868 KB/s | 1,5 s · 3 214 KB/s | 3,9 s · 1 431 KB/s | **0,8 s · 6 914 KB/s** |

Telethon lo avisa en su log: `cryptg module not installed and libssl not found, falling back to (slower) Python encryption`. Medido en un entorno aislado (`pip install cryptg` instaló la rueda sin compilar en el Python del proyecto, 3.12). Con `pyaes` el paralelismo apenas ayuda (la CPU es el límite); con `cryptg` sí.

### 3.6 Reel grande (descarga por enlace)

* El texto del bot es `error_file_too_large_link\n<URL>`; la URL mide 1 058 caracteres (hay que extraerla **entera**).
* `GET` con `User-Agent: curl/8.4.0`: **HTTP 200, `video/mp4`, 54 649 091 bytes en 2,67 s (20 MB/s)**, primer byte a 0,44 s. (En la primera pasada dio 403 porque mi script truncó la URL a 300 caracteres: el fallo era mío.)
* Nombre: `Deys2HkxrIy` → `4013467450971959858` (shortcode decodificado, sin pedir el HTML a Instagram; verificado también contra los `"media_id"` de `docs/response-post-ok.html` y `docs/response-reels-ok.html`).

## 4. Hallazgos en el código (`bot_conversation_service.py`) actualizados

| # | Hallazgo | Estado tras la prueba |
|---|---|---|
| F1 | Se descarga con Telethon todo mensaje con media; las miniaturas sin nombre se «promueven» si hay vídeos | **Confirmado**: doble descarga (M1 y M2 con el mismo nombre) |
| F2 | La descripción (texto `OK`) se ignora; se espera `stable_seconds` | Confirmado; la descripción llega 0-0,5 s tras el último adjunto |
| F3 | `error_file_too_large_link` se parsea como `OK` → plazo completo + vigilante + reintentos | Confirmado el texto real; falta cruzar con logs antiguos |
| F4 | El vigilante toma ficheros nuevos de la carpeta de Telegram Desktop por fecha de modificación, no por «foto» previa | Confirmado por el código. Recomendación: desactivar por defecto |
| F5 | El plazo de 30 s hasta la primera respuesta queda anulado por el de 300 s | Confirmado. Pero la prueba muestra que 30 s **no sirve** para carruseles grandes/highlights (ver 7.3) |
| F6 | **Nuevo:** sondeo cada 0,5 s + `limit=50` desencadena `FloodWait` de 11 s | Medido (3.4) |
| F7 | **Nuevo:** sin `cryptg` | Medido (3.5) |
| F8 | **Nuevo:** las descargas se hacen dentro del bucle de sondeo, una a una; mientras se descarga no se lee el chat | Por el código |

## 5. Informe de delays (actualizado)

Valores de `.env`: `MAX_RETRIES=5`, `RETRY_BASE_SECONDS=90`, `RETRY_MAX_SECONDS=900`, `DOWNLOAD_WAIT_TIMEOUT_SECONDS=300`, `DOWNLOAD_STABLE_SECONDS=10`.

| # | Tipo de delay | ms hoy | Propuesta | ¿Configurable hoy? |
|---|---|---|---|---|
| 1 | **Descarga de ficheros** (CPU de `pyaes`) | ~14 000 por 2,3 MB; 90 000 en un highlight de 16 vídeos | `cryptg` + descargas en paralelo (4) + una sola descarga por nombre | no |
| 2 | **`FloodWait` oculto de Telethon** | 11 000 cada ~30 s de sondeo | Eventos `NewMessage` (sin `GetHistory` en el bucle) o sondeo ≥ 1 500 | no |
| 3 | Backoff de reintento (bloqueante, por cuenta) | 90 000 / 180 000 / 360 000 / 720 000 / 900 000 | Cola global al final del lote; no dormir si `next_retry_at` ya pasó; contar desde el fallo | `.env` |
| 4 | Espera de estabilidad | 10 000 por item | Fin por conteo/descripción; gracia 2 000-3 000 | `.env` |
| 5 | Plazo hasta la primera respuesta | 300 000 (anulado) | **Por tipo** (7.3): story/reel/error 30 000, carrusel y highlights 75 000 | no |
| 6 | Plazo total tras la primera respuesta | 300 000 | 120 000 (con descargas rápidas; configurable) | `.env` |
| 7 | Respaldo del vigilante | hasta 300 000 + 10 000 más | Desactivado por defecto | no |
| 8 | Sondeo | 500 + red | Eventos; sondeo de respaldo ≥ 1 500 | no |
| 9 | Comprobación de post eliminado | 2 000 / 15 000 | timeout 8 000; interruptor | no |
| 10 | Latencia del bot | 1-5 s (reel/post/error), 12 s (story), 31 s (carrusel 20 / highlights) | No controlable; se mide | — |
| 11 | Descarga por enlace (reel > 50 MB) | n/a (hoy 600+ s y fallo) | ~3 s medidos; timeouts configurables | — |

## 6. Respuestas del usuario aplicadas

| Pregunta | Decisión |
|---|---|
| Reintentos | Cola global al final del lote (7.2) |
| Fin de descarga | Conteo de items + descripción + gracia (7.1) |
| Vigilante | Desactivar por defecto; razón en F4 |
| Envío adelantado | **Descartado** con datos (3.3) |
| Primera respuesta | El usuario propuso 30 s y «a la cola de reintentos»; la prueba exige **plazos por tipo** (7.3) |
| Histórico | Tabla de telemetría (8) con housekeeping posterior |
| Defaults | Optimizados |
| `stories_first` | Se mueve a la pestaña «Ejecución» |

## 7. Propuesta técnica

### 7.1 Fin de descarga por conteo (reemplaza los 10 s)

Reglas por tipo de URL, derivadas de 3.1:

* **`/p/`, `/reel/` (reel, post, carrusel):**
  1. Contar los items anunciados en **M1**: suma de mensajes de cada `grouped_id` (álbumes de ≤ 10) o 1 si no es álbum.
  2. **Descargar solo documentos con nombre**, una vez por `(nombre, tamaño)`. No descargar miniaturas sin nombre (las fotos originales llegan como adjunto).
  3. Terminar cuando los **nombres únicos descargados == items anunciados**; o al llegar la **descripción** tras ≥ 1 adjunto; o, si no llega nada más, tras `grace_seconds` (2-3 s). Los álbumes extra de un carrusel > 10 llegan en ≤ 0,75 s: no concluir hasta pasados 1,5 s del último álbum.
  4. Si tras la gracia no hay adjuntos pero sí miniaturas (posible caso de foto sin originales), descargar las miniaturas como hoy.
* **Story / highlights:** los items del álbum **son** el contenido (fotos y vídeos como documentos con nombre). Se descargan todos los mensajes del bloque; fin cuando no llegan más mensajes durante la gracia. No hay adjuntos ni descripción.
* Salvaguarda `completion_mode = STABLE` para volver al comportamiento actual.

### 7.2 Cola global de reintentos

* `AccountOrchestrator` termina la pasada principal de cada cuenta; los jobs `RETRY_PENDING` quedan con `next_retry_at = fallo + backoff`.
* `BatchOrchestrator` añade una **ronda final** con todos los reintentos del lote ordenados por `next_retry_at`, durmiendo solo lo que falte. El orden `stories_first` no cambia; las stories mantienen 2 reintentos y `Media not found` 3 (más la comprobación anónima de borrado).
* Una cuenta con reintentos pendientes queda `PARTIAL`/`INCOMPLETE` hasta cerrar la ronda. Reanudar tras una interrupción ya funciona (`RETRY_PENDING` + `next_retry_at` en SQLite).
* `NO_BOT_RESPONSE` tiene su propio tope (`run.retry.no_response_max`, propuesto 3).

### 7.3 Plazos de primera respuesta por tipo

El tipo se conoce por la URL (el clasificador ya distingue `STORY`, `HIGHLIGHTS`, `REEL` y `POST` con `img_index` = carrusel). Valores iniciales con la muestra (n = 1 por caso, **a calibrar con telemetría**):

| Tipo | Observado | Plazo propuesto |
|---|---|---|
| Error / reel / post simple | 1,2-6,7 s | 30 s |
| Story | 11,6 s | 30 s |
| Carrusel (`img_index`) | 3,3 s (12 items), 31,7 s (20 items) | 75 s |
| Highlights | 31,3 s | 75 s |
| `/p/` sin `img_index` | desconocido (puede ser carrusel) | 75 s |

Una vez llega el primer mensaje, el plazo pasa a ser el total (120 s) y se **renueva** con cada mensaje nuevo. Tras vencer → `NO_BOT_RESPONSE` a la cola global.

### 7.4 Sustituir el sondeo por eventos

* Registrar `events.NewMessage(chats=bot)` antes de enviar, y volcar los mensajes a una cola `asyncio.Queue` que consume la conversación. Sin `GetHistory` en el bucle.
* Respaldo: una única `get_messages(limit=30)` al vencer un plazo o al concluir, para recuperar mensajes perdidos por una reconexión.
* `response_poll_interval_ms` pasa a ser el intervalo del respaldo (≥ 1 500).
* Las descargas pasan a una tarea aparte con `asyncio.Semaphore(parallel_downloads)`, de modo que seguir recibiendo mensajes no queda bloqueado.

### 7.5 Dependencia `cryptg`

* Añadir `cryptg` a `pyproject.toml` y `requirements.txt`. Al arrancar el cliente, registrar un aviso si no está (`telethon.crypto.AES` cae a `pyaes`) y mostrar «descarga acelerada: sí/no» en el log de la ejecución.
* Es la mejora de mayor impacto y menor riesgo; no cambia ninguna regla.

### 7.6 Reels grandes (`error_file_too_large_link`)

1. `bot_response_parser`: nuevo estado `LARGE_FILE_LINK`; extrae la URL completa (primera `https://…` del mensaje).
2. Nombre: `<media_id>.mp4`, con `media_id` = shortcode decodificado (alfabeto `A-Za-z0-9-_`, base 64); respaldo: `"media_id"` del HTML junto a `"shortcode":"<sc>"` si falla la decodificación.
3. `GET` en streaming (`asyncio.to_thread`) a `.part`, comprobación de `Content-Length`, renombrado atómico y flujo normal (`REEL` → `reels\`). Header `User-Agent: curl/8.4.0` (el mismo que usa la comprobación de Instagram).
4. Fallos (403/410 por URL caducada, corte, tamaño distinto) → `RETRY_PENDING` con tipo `FILE_TOO_LARGE_DOWNLOAD_FAILED`; el reintento pide un enlace nuevo al bot.
5. Alcance: `/p/` y `/reel/`.

### 7.7 Base de datos y `bot_errors`

`bot_errors` ya existe (`code`, `match_pattern`, `match_kind`, `is_retryable`, `max_retries_override`, `notify_template`) pero el parser usa listas fijas en código. Se añaden las filas `FILE_TOO_LARGE_LINK` y `FILE_TOO_LARGE_DOWNLOAD_FAILED`. Fase posterior: que el parser lea la tabla. Nota: la tabla tiene `max_retries_override = 1` para `MEDIA_NOT_FOUND_OR_UNAVAILABLE` y el código aplica 3; unificar.

## 8. Settings: pestaña «Ejecución» (sin tablas nuevas)

Claves `run.*` en `app_settings` (y `app_config` en v1), leídas al arrancar el hijo `run_continue` (recibe `SQLITE_DB_PATH` = base de la GUI, `gui/run/controller.py:370`). Precedencia: GUI > `.env` > defecto. Código: `orchestration/run_settings.py` (`RunSettings`: carga, validación, guardado), `gui/settings/run_tab.py`, textos en `gui/shared/locales/es.json` y `en.json`. `stories_first` se mueve aquí.

| Grupo | Clave | Defecto optimizado (hoy) |
|---|---|---|
| Orden | `processing.stories_first` | 1 (1) |
| Reintentos | `run.retry.global_queue` | 1 (0) |
| | `run.retry.max_retries` / `story_max` / `media_not_found_max` / `no_response_max` | 5 / 2 / 3 / 3 (5 / 2 / 3 / 5) |
| | `run.retry.base_seconds` / `max_seconds` | por calibrar con datos (90 / 900) |
| Bot | `run.bot.first_response_timeout_seconds` (fallback) y por tipo `…_story`, `…_carousel`, `…_highlights` | 30 / 30 / 75 / 75 (300) |
| | `run.bot.total_timeout_seconds` | 120 (300) |
| | `run.bot.completion_mode` | `EXPECTED_COUNT` (`STABLE`) |
| | `run.bot.grace_seconds` | 2,5 (10) |
| | `run.bot.use_events` | 1 (0, sondeo) |
| | `run.bot.fallback_poll_ms` | 1500 (500) |
| | `run.bot.parallel_downloads` | 4 (1) |
| | `run.bot.skip_thumbnail_download` | 1 (0) |
| Vigilante | `run.watcher.fallback_enabled` / `timeout_seconds` | 0 / 30 (1 / 300) |
| Enlace grande | `run.largefile.enabled` / `connect_timeout_s` / `read_timeout_s` / `max_mb` | 1 / 10 / 120 / 500 |
| Instagram | `run.availability.enabled` / `min_interval_ms` / `timeout_ms` | 1 / 2000 / 8000 |
| Telethon | `run.telethon.flood_sleep_threshold` | 60 (60); y registrar cada dormida |
| Telemetría | `run.telemetry.level` (`OFF`/`ATTEMPTS`/`FULL`) / `retention_days` | `FULL` / 90 |

## 9. Observadores: telemetría y balance del lote

### 9.1 Principios

* `RunObserver` (protocolo) inyectado en `BotConversationService`, `AccountOrchestrator`/`BatchOrchestrator` y la comprobación de Instagram; `NullObserver` (base v1 / telemetría `OFF`) y `SqliteObserver`.
* Un `AttemptTrace` en memoria con relojes monotónicos (inyectables en pruebas) se **vuelca al terminar el intento** en una transacción: sin escrituras en el bucle. Un fallo de telemetría nunca rompe el lote.
* Privacidad: no se guarda el texto de las descripciones (clase y longitud); de errores, el código; de textos desconocidos, 120 caracteres.
* Con la prueba ya sabemos qué medir: además de las fases, **bytes descargados, ficheros duplicados evitados, `FloodWait` sufridos y motor de cifrado**.

### 9.2 Tablas (aditivas, `db/gui_migrations.py`, solo base v2)

`url_job_attempts` (una fila por intento): `id`, `url_job_id`, `batch_id`, `batch_run_id`, `account_id`, `attempt_no`, `publication_type`, `expected_items`, `album_size_bucket` (1, 2-4, 5-10, 11+), `started_at`, `finished_at`, `t_send_ms`, `t_first_response_ms`, `t_first_media_ms`, `t_last_media_ms`, `t_description_ms`, `t_end_wait_ms`, `t_download_ms`, `t_move_ms`, `t_total_ms`, `retry_wait_ms`, `queue_wait_ms`, `flood_wait_ms`, `exit_reason` (`COUNT_REACHED`, `DESCRIPTION`, `GRACE`, `DEADLINE_FIRST`, `DEADLINE_TOTAL`, `ERROR_TEXT`, `LARGE_FILE_LINK`, `UNKNOWN_TEXT`), `outcome`, `error_code`, `messages_count`, `media_count`, `files_count`, `bytes_downloaded`, `duplicates_skipped`, `aes_backend` (`cryptg`/`pyaes`), `settings_json`.

`bot_message_events` (solo `FULL`): `attempt_id`, `message_id`, `grouped_id`, `offset_ms`, `kind` (`TEXT`/`PHOTO`/`DOCUMENT_FILE`/`VIDEO_NONAME`), `mime`, `has_filename`, `size_bytes`, `download_ms`, `text_class`, `text_len`.

`run_wait_events`: `attempt_id` (nullable), `kind` (`BACKOFF`, `FLOOD_WAIT`, `AVAILABILITY_THROTTLE`), `ms`, `at`. Los `FloodWait` de Telethon se capturan con un manejador del logger `telethon.client.users`.

Índices: `(batch_id)`, `(url_job_id)`, `(started_at)`, `(attempt_id)`. Estimación: ~10 mensajes por intento → ~430 000 filas de eventos por 43 000 URLs (~35-40 MB) → retención 90 días y housekeeping (`purge_telemetry(older_than | batch_id)`, botón en Settings, patrón de `db/downloaded_files_cleanup.py`).

### 9.3 Informe de ejecución de un lote

Acceso: modal «Lotes guardados y ejecuciones…» → clic derecho en el lote → **«Informe de ejecución…»** (y *Lote → Informe de ejecución* para el actual). Modal con pestañas; exportable a Markdown/CSV y como sección del informe `run_*.md`:

1. **Resumen**: duración, tiempo activo vs esperas, URLs/hora, % por fase (bot / descarga / fin de espera / backoff / `FloodWait` / movimiento / otros), bytes descargados.
2. **Más lentos**: top 20 con desglose por fase y explicación automática del «por qué» (fase dominante + `exit_reason`).
3. **Por tipo y tamaño**: p50/p90/máx de primera respuesta y total por reel, carrusel (por bucket), story, highlights. Es la fuente para calibrar los plazos de 7.3.
4. **Errores**: por código de `bot_errors`: nº, tiempo hasta el mensaje, reintentos consumidos, tiempo perdido.
5. **Reintentos**: éxito por nº de intento y por espera previa.
6. **Recomendaciones** (reglas deterministas): ej. «p99 de primera respuesta en carrusel = 34 s con plazo 30 s → subir a 75 s», «`aes_backend = pyaes` en el 100 % → instalar `cryptg`», «`flood_wait_ms` > 5 % del tiempo → activar eventos».

```
Lote descargas_21_oct   |  79 cuentas · 214 URLs · 3 h 12 min   (47 URLs/h)
Tiempo por fase   bot 12 %  descarga 51 %  FloodWait 14 %  fin de espera 14 %  backoff 7 %  otros 2 %
Más lentos  1. euamandaleon_ item 2   5:55   reel grande: 300 s sin soporte de enlace + 2 intentos
```

Código: paquete `telemetry/` (`trace.py`, `observer.py`, `sqlite_observer.py`, `report.py`, `housekeeping.py`, `MODULE.md`) y `gui/batches/execution_report.py`.

## 10. Plan por feats (reordenado tras la prueba)

Primero lo que da más con menos riesgo y no cambia reglas; la telemetría va pronto para poder medir el efecto de todo lo demás:

| Orden | Feat | Versión | Contenido | Ahorro esperado por item |
|---|---|---|---|---|
| 1 | feat-run-30 | v4.4.0 | **Rendimiento sin cambio de reglas**: `cryptg`, eventos en vez de sondeo (con respaldo ≥ 1,5 s), una descarga por nombre, sin miniaturas redundantes, descargas en paralelo, vigilante desactivable (off) | ~25-30 s en un reel normal; hasta ~85 s en un highlight |
| 2 | feat-run-31 | v4.5.0 | Reel grande: `LARGE_FILE_LINK` + descarga por enlace + nombre por shortcode | Un fallo de > 30 min pasa a ~3 s |
| 3 | feat-run-32 | v4.6.0 | Telemetría: tablas + `AttemptTrace` + observador (sin informe) | — (medir) |
| 4 | feat-run-33 | v4.7.0 | `RunSettings` + pestaña «Ejecución» (incluye `stories_first`) con defectos optimizados | — |
| 5 | feat-run-34 | v4.8.0 | Fin por conteo/descripción y plazos de primera respuesta por tipo | ~8-10 s |
| 6 | feat-run-35 | v4.9.0 | Cola global de reintentos + tope `no_response_max` | Minutos por lote con fallos |
| 7 | feat-run-36 | v4.10.0 | Informe de ejecución + recomendaciones + housekeeping | — |

El feat 1 podría abordarse en un solo commit pequeño, pero sus subtareas son independientes (dependencia, eventos, descargas). Los ajustes `run.*` del feat 4 hacen configurables lo introducido en 1-2; hasta entonces entran con valores fijos documentados.

## 11. Preguntas abiertas

* **P11-1.** ¿Apruebas el orden de la sección 10? ¿Prefieres separar el feat 1 en dos (primero `cryptg` + eventos; luego descargas/duplicados)?
* **P11-2.** `cryptg` es una dependencia nativa (la rueda de Windows instaló sin compilar en este Python 3.12). ¿Hay algún equipo/instancia (p. ej. la otra instancia de intercambio) con otra versión de Python o sin posibilidad de instalar ruedas?
* **P11-3.** Plazos por tipo de 7.3: ¿te parecen razonables como punto de partida (30 s / 75 s)? Los carruseles y highlights más grandes de tu uso habitual, ¿llegan a 20 items o más?
* **P11-4.** La prueba mide sin descargar fuera de `bot_chat`, pero Telegram Desktop abierto en el chat puede autodescargar. Para no mezclar ficheros, ¿descargamos a una carpeta temporal propia en el feat 1 (y dejamos la de Telegram Desktop solo como respaldo opcional)?
* **P11-5.** Telemetría: descripciones no guardadas (solo clase y longitud) y retención de 90 días. ¿Correcto?
* **P11-6.** Informe: ¿clic derecho en el modal «Lotes guardados y ejecuciones» y además en el menú *Lote*? No he verificado el menú contextual actual de ese modal.
* **P11-7.** ¿Repetimos la prueba real con algún caso más? Candidatos: una story con muchos items, un highlight de > 20 items, un +18, un reel de 30-49 MB y una cuenta privada con stories. Puedo repetir el mismo script cuando me des las URLs.

## 12. Documentación y pruebas al implementar (cada feat)

`CHANGELOG.md`, `docs/manual-usuario.md`, `docs/tutorial-v3.md`, `docs/arquitectura-v3.md` (claves `run.*`, tablas de telemetría, dependencia `cryptg`, limitaciones), `MODULE.md` de `orchestration/`, `telegram/`, `telemetry/`, `gui/settings/`, `gui/batches/`, `README.md` si cambia lo visible (instalación de `cryptg`), fila en `docs/plan-v3-features.md`, y mover cada especificación a `tasks/done/v4/` con su «Resultado de la implementación».

Pruebas previstas: cliente de Telegram y reloj falsos con las **secuencias reales de mensajes** de esta prueba (reel con M1=M2 duplicado, carrusel de 12 con dos álbumes, carrusel de 20 con vídeos repetidos, highlights de 16, story, error, enlace grande) como fixtures; decodificación shortcode→media_id (casos verificados y entradas inválidas); descarga por enlace con servidor local (200, 403, corte, tamaño distinto); migraciones con base antigua; `RunSettings`; cola global (orden, `next_retry_at`, reanudación, topes); telemetría que falla sin romper el lote; consultas del informe con datos sintéticos. Nada contra Telegram/Instagram reales ni sobre `G:` en la suite automática; las mediciones reales las hace la sonda o el usuario.

## Anexo A · Cómo se hizo la prueba

* Script independiente (`probe_bot.py`, `bench.py`, `redo_large.py`, en el scratchpad de la sesión, fuera del repo): envía las URLs una a una al bot real con la sesión de Telethon del usuario, registra por mensaje `id`, instante, `reply_to`, `grouped_id`, tipo, nombre, tamaño y clase de texto, y mide descargas después de la observación. No usa la base de la app. Los ficheros descargados y la copia temporal de la sesión se borraron al terminar.
* Candidato a convertirse en el comando `python -m ig_orchestrator probe` (fuera de este feat) para repetir la medición cuando cambie el bot.
* Límites: muestra de 1 intento por caso; los tiempos del bot varían con la carga; los percentiles salen de la telemetría de lotes reales.

## Resultado de la implementación

### v4.4.0 (parte 1) · 2026-10-24
Hecho: `cryptg` en dependencias + aviso en el log; conversación por eventos `NewMessage` (suscripción antes de enviar) con sondeo de respaldo cada 1,5 s. Decisiones del usuario: orden aprobado; feat 1 dividido en dos commits; carpeta temporal de descarga propia y configurable (v4.4.1); telemetría con retención de 90 días e informe en el modal de lotes y el menú Lote; sin más pruebas reales (se mide con telemetría); tamaño por URL queda como idea futura. `media_id`: los nombres de fichero no se tocan.
### v4.4.1 (parte 2) · 2026-10-24
Hecho: descarga única por `(nombre, tamaño)`; miniaturas sin nombre solo como respaldo (si los originales son todo imágenes, no se bajan); descargas en paralelo (`TELEGRAM_PARALLEL_DOWNLOADS`=4); carpeta propia opcional (`TELEGRAM_DOWNLOAD_TEMP_FOLDER`, vacío = la de Telegram Desktop); vigilante off por defecto (`TELEGRAM_WATCHER_FALLBACK`). Estos ajustes están en `.env` con valores fijos hasta el feat 4 (`RunSettings`). No se hizo: fin por conteo/descripción (feat 5), plazos por tipo (feat 5).
### v4.5.0 (feat 2, «feat-run-31») · 2026-10-24
Hecho: estado `LARGE_FILE_LINK`, descarga por enlace como `<media_id>.mp4`, fallo → `FILE_TOO_LARGE_DOWNLOAD_FAILED` con reintento, filas en `bot_errors`. Desviación: si el shortcode no se pudiera decodificar no se usa el `"media_id"` del HTML de Instagram; se trata como fallo (un shortcode de `/p/` o `/reel/` siempre decodifica). Límites fijos (10/120 s, 500 MB) hasta el feat 4.
### v4.6.0 (feat 3, «feat-run-32») · 2026-10-24
Hecho: paquete `telemetry/`, tres tablas aditivas, `AttemptTrace`, `SqliteObserver`/`NullObserver`, captura de `FloodWait`, purga por retención al arrancar, `TELEMETRY_LEVEL`/`TELEMETRY_RETENTION_DAYS`. Motivo de salida actual `STABLE` (los de conteo/descripción llegan con el feat 5); `expected_items`, `retry_wait_ms` y `queue_wait_ms` quedan vacíos hasta los feats 5 y 6. Sin informe ni botón de purga en la GUI (feat 7). Corregido de paso `ProjectLogger` (`exc_info`).
### v4.7.0 (feat 4, «feat-run-33») · 2026-10-24
Hecho: `RunSettings` + pestaña «Ejecución» con 23 claves cableadas (sin tablas nuevas), precedencia GUI > `.env` > defecto, validación, guardado solo de diferencias, restablecer, `stories_first` movido. Desviaciones: no se añaden las claves de los feats 5-6 (plazos por tipo, `completion_mode`, `grace_seconds`, `global_queue`, `no_response_max`, `skip_thumbnail_download`) porque aún no hay código que las use; los defectos de plazo total y silencio siguen siendo 300/10 s hasta el feat 5. `skip_thumbnail_download` no se expone (la regla de v4.4.1 es fija).
### v4.8.0 (feat 5, «feat-run-34») · 2026-10-24
Hecho: modo `EXPECTED_COUNT` (conteo / descripción / silencio breve) con `STABLE` como salvaguarda, plazos de primera respuesta por tipo, plazo total renovable (120 s), filtro de mensajes rezagados, regla de miniaturas por tipo de URL, `expected_items` en la telemetría, ajustes nuevos en *Ejecución*. Desviaciones: el plazo de primera respuesta de «/p/ sin img_index» usa el de carrusel (75 s); `run.bot.skip_thumbnail_download` sigue sin exponerse; el defecto de `stable_seconds` se mantiene en 10 (solo afecta al modo `STABLE`). Pendiente de validar con el bot real: que 2,5 s de silencio no corte álbumes lentos.
### v4.9.0 (feat 6, «feat-run-35») · 2026-10-24
Hecho: cola global de reintentos (ronda final del lote ordenada por `next_retry_at`, `defer_retries`, `only_job_id`), tope propio de `NO_BOT_RESPONSE` (3), ajustes `run.retry.global_queue` y `run.retry.no_response_max`, modo anterior conservado al desactivar la cola. Desviaciones: la ronda reintenta de uno en uno (sin paralelismo); el retroceso se respeta esperando solo lo que falta. Sin probar con Telegram real.
Pendiente: feat 7.
