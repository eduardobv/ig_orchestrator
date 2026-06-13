# Tarea 20 - Logs

Version objetivo: `v1.20.0`

## Objetivo

Crear logs por ejecucion y por cuenta.

## Archivo

```text
src/ig_orchestrator/logging_config.py
```

## Salidas

```text
logs/app.log
username/_logs/run_YYYYMMDD_HHMMSS.log
```

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
