# Tarea 8 - Servicio de carpetas

Version objetivo: `v1.8.0`

## Objetivo

Crear estructura temporal de trabajo para una cuenta.

## Archivo

```text
src/ig_orchestrator/filesystem/folder_service.py
```

## Input

```text
username
working_folder
```

## Carpetas creadas

```text
username/
username/story/
username/reels/
username/highlights/
username/_errors/
username/_logs/
```

`username/_duplicated/` queda reservado para versiones posteriores.

## Criterios de aceptacion

* Si la carpeta existe, no destruir contenido.
* Si falta una subcarpeta, crearla.
* Devolver estructura de rutas.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios con carpeta temporal.
