# Tarea 15 - Servicio de conversacion con bot

Version objetivo: `v1.15.0`

## Objetivo

Procesar una URL completa contra el bot.

## Archivo

```text
src/ig_orchestrator/telegram/bot_conversation_service.py
```

## Flujo

1. Marcar URL como `SENT_TO_BOT`.
2. Enviar URL al bot.
3. Guardar `sent_message_id`.
4. Esperar respuesta.
5. Si hay error no reintentable, marcar `FAILED_FINAL`.
6. Si hay error reintentable, marcar `RETRY_PENDING`.
7. Si no hay error, activar watcher.
8. Asociar archivos detectados.
9. Marcar como `DOWNLOADED` o fallo temporal si no hay archivos.

## Criterios de aceptacion

* No procesar dos URLs al mismo tiempo en `v1.0.1`.
* Una URL debe tener logs propios o trazas claras.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests con mocks de Telegram y watcher.
