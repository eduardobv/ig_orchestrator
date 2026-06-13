# Tarea 10 - Parser de respuestas del bot

Version objetivo: `v1.10.0`

## Objetivo

Detectar errores conocidos y respuestas utiles del bot.

## Archivo

```text
src/ig_orchestrator/telegram/bot_response_parser.py
```

## Errores reintentables

```text
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable
```

## Errores no reintentables

```text
We're sorry, we couldn't find that.
Stories for user_name not found
We can't get stories from a private account (instagram limit)
```

## Output esperado

```text
BotResponseStatus.OK
BotResponseStatus.RETRYABLE_ERROR
BotResponseStatus.NON_RETRYABLE_ERROR
BotResponseStatus.UNKNOWN
```

## Criterios de aceptacion

* Detectar errores aunque cambien mayusculas/minusculas.
* Guardar mensaje original como `last_error`.
* Devolver `last_error_type`.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios para cada error conocido.
