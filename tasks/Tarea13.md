# Tarea 13 - Clasificador de archivos

Version objetivo: `v1.13.0`

## Objetivo

Clasificar archivos descargados.

## Archivo

```text
src/ig_orchestrator/filesystem/file_classifier.py
```

## Reglas

```text
.jpg, .jpeg, .png, .webp => IMAGE
.mp4, .mov, .mkv, .webm => VIDEO
otro => UNKNOWN
```

## Criterios de aceptacion

* Extensiones case-insensitive.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios.
