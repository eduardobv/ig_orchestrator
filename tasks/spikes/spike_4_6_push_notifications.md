# Spike 4.6 — Notificaciones que sí suenen en el móvil

Tipo: spike (sin cambios en `src/`, sin versión ni tag). Fecha: 2026-11-02.

## Problema

En Ajustes → Notifications, con `Target = me` (o con tu `@user`) el aviso llega a «Mensajes guardados» y el móvil no suena.

## Causa (verificada en código)

`telegram/notify_service.py` → `send_user_notification` → `client.send_message_to(target, text)`.
Ese cliente es la sesión Telethon de **tu propia cuenta**. Un mensaje enviado por ti
(a ti mismo o a tu @user, que es lo mismo) nunca genera notificación en tus propios
dispositivos: Telegram lo trata como «mensaje propio». No es un fallo de ajustes ni del móvil.

## Opciones evaluadas

| # | Opción | Suena en móvil | Esfuerzo | Coste | Notas |
|---|---|---|---|---|---|
| A | **Bot propio de Telegram (Bot API)** | Sí | Bajo | Gratis | Creas un bot con @BotFather, le das /start una vez, y la app hace `POST https://api.telegram.org/bot<TOKEN>/sendMessage` con tu `chat_id`. El remitente es el bot, no tú, así que notifica como cualquier chat. Sin Telethon: solo `httpx`/`urllib`. **Recomendada.** |
| B | **ntfy.sh** (app ntfy en el móvil) | Sí, con prioridad alta incluso en No molestar si lo permites | Muy bajo | Gratis (o servidor propio) | `POST https://ntfy.sh/<tema-secreto>` con el texto. Sin cuentas ni tokens; la privacidad depende de que el nombre del tema sea largo y aleatorio. Buen plan B / segundo canal. |
| C | Pushover / Pushbullet | Sí | Bajo | De pago (Pushover, pago único por plataforma) | Fiable, pero de pago. |
| D | WhatsApp (CallMeBot o Twilio/Meta Cloud API) | Sí | Medio/alto | CallMeBot gratis pero no oficial y frágil; Twilio/Meta de pago y con trámites | No lo recomiendo: riesgo de cortes y de bloqueo del número. |
| E | Discord webhook | Sí | Bajo | Gratis | Requiere app Discord en el móvil. |
| F | Correo (SMTP) | Depende de la app de correo | Medio | Gratis | Más lento y menos visible. |
| G | Truco con Telethon: segunda cuenta de Telegram que te escribe | Sí | Medio | Gratis | Necesita otra cuenta/número y otra sesión; peor que A. |

Descartado: seguir enviando con Telethon a `me`/@user (no puede funcionar) y enviar a un
canal/grupo propio (los mensajes que envías tú tampoco te notifican).

## Recomendación

1. **Feat nuevo: canal «Bot de Telegram» (opción A)** en Ajustes → Notifications:
   campos `Bot token` y `Chat ID` (con botón «Probar» y ayuda para obtener el chat_id con `getUpdates` tras el /start).
   Dejar `me` como alternativa y marcar en la UI que no suena.
2. Opcional en el mismo feat o posterior: **ntfy** como canal alterno (un solo campo: URL del tema).
3. Diseño: una interfaz `Notifier` con implementaciones (Telethon, BotApi, Ntfy) tras `send_user_notification`;
   el resto (`notify_batch_complete`, `notify_bot_error`) no cambia. El envío por Bot API no necesita el
   cliente Telethon, así que también funcionaría en `send_ephemeral_notification` sin abrir sesión.
4. Seguridad: el token del bot es un secreto: guardarlo en `.env`/ajuste no commiteado y no escribirlo en logs.

## Qué no se probó

No se ha enviado ninguna notificación real ni se ha creado ningún bot. La afirmación de que el
Bot API notifica se basa en el comportamiento documentado de Telegram (mensajes de un bot a un
usuario que lo inició); conviene confirmarlo en 2 minutos con @BotFather + un `curl` antes de implementar.
Precios y estado de CallMeBot/Pushover pueden haber cambiado: verificar si se elige C o D.

## Prueba rápida manual (sin código del proyecto)

1. En Telegram, habla con @BotFather → `/newbot` → copia el token.
2. Abre tu bot y pulsa Start / envía «hola».
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia `message.chat.id`.
4. `curl "https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>&text=prueba"`
   → debe sonar en el móvil.
