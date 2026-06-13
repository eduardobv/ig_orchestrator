# Tarea 3 - Modelos de dominio

Version objetivo: `v1.3.0`

## Objetivo

Crear modelos de dominio con Pydantic o dataclasses.

## Archivos

```text
src/ig_orchestrator/models/account.py
src/ig_orchestrator/models/app_config.py
src/ig_orchestrator/models/input_batch.py
src/ig_orchestrator/models/url_job.py
src/ig_orchestrator/models/download_file.py
src/ig_orchestrator/models/run_summary.py
```

## Entidades

```text
AppConfig
InputBatch
Account
UrlJob
DownloadFile
RunSummary
```

## Criterios de aceptacion

* Los estados deben representarse con Enum.
* Incluir tipos `POST`, `REEL`, `STORY`, `HIGHLIGHTS`, `UNKNOWN`.
* Incluir origen de URL: `GENERATED_STORY`, `INPUT_URL`.
* Incluir estados de URL y archivo definidos en `PLAN.md`.
* Validar datos minimos.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios de creacion y validaciones minimas.
