# Tarea 5 - Parser de JSON por lotes

Version objetivo: `v1.5.0`

## Objetivo

Leer y validar el archivo JSON de entrada por lotes.

## Archivo

```text
src/ig_orchestrator/input/batch_json_parser.py
```

## Input

```text
config/batch.example.json
```

## Reglas

* `schema_version` obligatorio.
* `batch_name` obligatorio.
* `accounts` obligatorio.
* `username` obligatorio por cuenta.
* `start_now_date` puede heredarse de `defaults`.
* `download_stories` puede heredarse de `defaults`.
* `urls` puede estar vacio si `download_stories = true`.
* Eliminar espacios.
* No duplicar URLs dentro de la misma cuenta.
* Validar fecha `YYYY-MM-DD`.
* Validar dominio de Instagram.

## Criterios de aceptacion

* Devuelve modelos validados.
* Errores claros indicando cuenta/campo problematico.
* Actualizar `CHANGELOG.md`.

## Pruebas

* JSON valido.
* Defaults heredados.
* URL duplicada.
* Fecha invalida.
* URL no Instagram.
