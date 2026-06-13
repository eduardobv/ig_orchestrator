# Tarea 12 - Watcher de descargas

Version objetivo: `v1.12.0`

## Objetivo

Detectar archivos nuevos descargados por Telegram Desktop.

## Archivo

```text
src/ig_orchestrator/filesystem/file_watcher.py
```

## Inputs

```text
folder
start_time
timeout_seconds
stable_seconds
```

## Output

```text
List[Path]
```

## Reglas

* Solo devolver archivos creados o modificados despues de `start_time`.
* Esperar a que el tamano del archivo sea estable.
* Ignorar directorios.
* Ignorar archivos temporales.
* No mover archivos.

## Criterios de aceptacion

* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios o de integracion con carpeta temporal.
