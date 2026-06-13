# Tarea 4 - SQLite schema, migraciones y repositorios

Version objetivo: `v1.4.0`

## Objetivo

Crear la base de datos SQLite, migraciones seguras y repositorios.

## Archivos

```text
src/ig_orchestrator/db/schema.sql
src/ig_orchestrator/db/connection.py
src/ig_orchestrator/db/migrations.py
src/ig_orchestrator/db/config_repository.py
src/ig_orchestrator/db/batch_repository.py
src/ig_orchestrator/db/account_repository.py
src/ig_orchestrator/db/url_job_repository.py
src/ig_orchestrator/db/download_repository.py
src/ig_orchestrator/db/run_repository.py
```

## Tablas

Implementar las tablas de `PLAN.md`:

```text
app_config
input_batches
accounts
url_jobs
download_files
runs
```

## Criterios de aceptacion

* `init-db` crea tablas si no existen.
* Si la BD existe, no borra informacion.
* Se puede crear batch, cuenta, URL job, archivo descargado y run.
* Se puede actualizar estado y consultar por estado.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests de integracion con SQLite temporal.
