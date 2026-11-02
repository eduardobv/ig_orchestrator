# feat-gui-31 · Avisos por bot de Telegram (v4.24.0)

## Objetivo
Que los avisos (fin de lote, errores del bot) hagan sonar el móvil. Origen: `tasks/spikes/spike_4_6_push_notifications.md`.

## Resultado de la implementación
* Ajustes `notify.bot_token` y `notify.bot_chat_id` (pestaña Notificaciones). Con ambos, `deliver_notification` envía por la Bot API (`urllib`, en hilo); si no, Telethon como antes.
* Los errores nunca incluyen el token.
* *Enviar prueba* usa el bot si está relleno.

## No se hizo / límites
* No se crea el bot solo: lo hace el usuario con @BotFather.
* El token se guarda en SQLite (`data/`, no versionado) en claro.
* No hay canal ntfy/WhatsApp (descartados o pospuestos en el spike).
* No probado con un bot real.
