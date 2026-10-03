# Tarea 22 - Integracion con script actual de renombrado

Version objetivo: `v1.22.0`

## Estado

No implementar en `v1.0.1`.

## Objetivo futuro

Crear o actualizar `config.json` para el script actual y ejecutar `ManualRenameFiles.bat`.

## Archivos futuros

```text
src/ig_orchestrator/rename/rename_config_builder.py
src/ig_orchestrator/rename/manual_rename_runner.py
src/ig_orchestrator/rename/rename_result_parser.py
```

## Criterios futuros

* Mantener formato JSON valido.
* No perder otras claves existentes.
* Capturar stdout, stderr y exit code.
* Marcar proceso como `FAILED` si falla.
* Actualizar `CHANGELOG.md`.

## Nota

Esta tarea queda documentada para mantener el plan completo, pero la primera version solo quiere observar el sistema de descarga.
