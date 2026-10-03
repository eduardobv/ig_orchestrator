# Tarea 9 - Cliente Telegram con Telethon

Version objetivo: `v1.9.0`

## Objetivo

Crear wrapper para Telethon.

## Archivo

```text
src/ig_orchestrator/telegram/telegram_client.py
```

## Responsabilidades

* Inicializar cliente Telethon.
* Iniciar sesion si no existe sesion.
* Reutilizar sesion existente.
* Enviar mensaje a bot.
* Leer ultimos mensajes del bot.
* Obtener mensajes nuevos despues de un timestamp.

## Criterios de aceptacion

* La primera ejecucion debe pedir login si no hay sesion.
* Las siguientes ejecuciones deben reutilizar sesion.
* No loguear credenciales.
* No depender de Telegram real en tests.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios con mocks.
