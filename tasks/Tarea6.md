# Tarea 6 - Importador JSON a SQLite

Version objetivo: `v1.6.0`

## Objetivo

Importar el JSON validado a SQLite y convertirlo en batch, cuentas y url jobs.

## Archivo

```text
src/ig_orchestrator/input/batch_importer.py
```

## Reglas

* Crear `input_batches`.
* Crear `accounts`.
* Guardar `download_stories`.
* Si `download_stories = true`, generar `https://www.instagram.com/stories/{username}/`.
* Insertar story generada como `url_job` tipo `STORY`, `source = GENERATED_STORY`.
* Insertar URLs manuales como `source = INPUT_URL`.
* Clasificar cada URL con el clasificador.
* Evitar duplicados razonables al reimportar el mismo batch.
* Guardar configuracion operativa en `app_config` cuando aplique.

## Criterios de aceptacion

* Tras importar, la ejecucion puede leer todo desde SQLite.
* El JSON deja de ser fuente de verdad tras importarse.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Importar batch con dos cuentas.
* Importar cuenta con `download_stories = true`.
* Reimportar sin duplicar URLs iguales.
