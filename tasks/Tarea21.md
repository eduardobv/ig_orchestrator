# Tarea 21 - Tests minimos obligatorios

Version objetivo: `v1.21.0`

## Objetivo

Asegurar cobertura minima antes de considerar cerrada la version `v1.0.1`.

## Tests obligatorios

```text
settings
batch_json_parser
batch_importer
url_classifier
retry_policy
bot_response_parser
file_watcher
file_classifier
folder_service
file_mover
sqlite repositories
markdown_report_builder
account_orchestrator dry-run
batch_orchestrator dry-run
```

## Criterios de aceptacion

* La suite se ejecuta con `pytest`.
* No requiere Telegram real.
* No requiere rutas reales de produccion.
* Usa temporales para SQLite y filesystem.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Ejecutar `pytest`.
