# Tarea 19 - Logs

Version objetivo: `v1.19.0`

## Objetivo

Crear logs por ejecucion y por cuenta.

Toda la trazabilidad debe vivir bajo la carpeta `logs`.

## Archivo

```text
src/ig_orchestrator/logging_config.py
```

## Salidas

```text
logs/app.log
logs/YYYYMMDD_HHMMSS/username.log
```

`logs/app.log` debe contener trazas generales de aplicacion, warnings y errores.

`logs/YYYYMMDD_HHMMSS/username.log` debe contener las trazas relacionadas con
los ficheros, URLs, posts, Telegram, errores y reintentos de ese username dentro
de esa ejecucion.

## Debe registrar

* cuenta procesada;
* URL procesada;
* mensaje enviado al bot;
* respuesta del bot;
* archivos detectados;
* errores;
* reintentos;
* reporte generado.

No registrar:

* `api_hash`;
* codigos de login;
* contenido sensible de `.env`.

## Criterios de aceptacion

* Logs claros y utiles para depurar.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios donde aplique o verificacion manual documentada.
