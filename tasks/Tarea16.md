# Tarea 16 - Procesador de URL job

Version objetivo: `v1.16.0`

## Objetivo

Coordinar Telegram, watcher, clasificacion, movimiento y repositorios para una URL.

## Archivo

```text
src/ig_orchestrator/orchestration/url_job_processor.py
```

## Input

```text
url_job_id
```

## Output

```text
UrlJob actualizado
DownloadFiles registrados
```

## Criterios de aceptacion

* Si Telegram devuelve error definitivo, no reintentar.
* Si Telegram devuelve error temporal, marcar `RETRY_PENDING`.
* Si se descargan archivos, registrar cada archivo.
* Si no se descarga nada dentro del timeout, marcar error temporal.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests con mocks.
