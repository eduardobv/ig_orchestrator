# feat-run-39 · Pausa entre URLs y modo espera con el bot sin respuesta (v4.16.0)

## Objetivo
1. Una pausa configurable entre una URL y la siguiente (2 s por defecto): el bot se saturaba en cuentas con cientos de URLs.
2. Si el bot deja de responder, no seguir enviando URLs: sondear con una segunda URL tras una espera configurable (10 s) y, si tampoco responde, esperar (avisando en la barra de estado) hasta que conteste y recoger las respuestas de las dos.

## Resultado de la implementación
* Ajustes `run.bot.between_urls_seconds` (2), `run.bot.stall_enabled` (sí) y `run.bot.stall_probe_delay_seconds` (10) en *Configuración > Ejecución > Bot y descargas* (`orchestration/run_settings.py`, locales).
* `BotConversationService`: `_pause_before_send` (pausa y espera de sondeo), `_guard_against_silent_bot` (estado `_unanswered`), `_wait_for_bot_recovery` (modo espera sin envíos, sin límite), `_collect_late_answer` (respuesta tardía de la URL anterior, `late_results`), `_finish_after_wait` (extraído), filtro de mensajes con varios ids propios y `_claimed_message_ids` para no asignar un mensaje a dos URLs.
* `UrlJobProcessor`: cierra las respuestas tardías (archivos, `COMPLETED`), recalcula el estado de la cuenta y expone `stall_pending`; los orquestadores no aplican el *backoff* mientras `stall_pending` (la URL muda se reenvía a los 10 s).
* CLI imprime `[GUI_BOT_STATUS] STALLED|RESUMED`; la GUI lo muestra en la barra de estado (`gui/run/controller.py`).
* Tests: `tests/telegram/test_stall_guard.py`, `tests/orchestration/test_stall_guard_flow.py`, ajustes en `test_run_settings.py` y `test_run_tab.py`.

## No hecho / límites
* No probado con el bot real ni con la GUI abierta.
* La asignación de respuestas desordenadas se basa en `reply_to`; sin él, todo lo no atribuible va a la URL más antigua y la otra se reintenta (se reenvía).
* El modo espera no tiene tope de tiempo; se sale con Pausar/Detener. No hay ajuste de tope máximo.
* La respuesta tardía no genera un intento propio en la telemetría (el intento original ya cerró como `NO_BOT_RESPONSE`); la actual lleva `stall_recovered` en `settings`.
* Si la URL muda se responde mientras se envía la siguiente (el bot revive justo entonces), la respuesta a la anterior se ignora por `reply_to` y esa URL se reintenta (comportamiento anterior).
