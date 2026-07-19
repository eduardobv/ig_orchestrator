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

## Carpetas y creacion perezosa

```text
username/
```

Al iniciar una cuenta solo se crea `username/`. Las subcarpetas `story/`,
`reels/` y `highlights/` se crean al mover el primer archivo que realmente
corresponda a ese tipo, evitando carpetas vacias por descargas fallidas o tipos
no presentes.

## Criterios de aceptacion

* Si la carpeta existe, no destruir contenido.
* No crear subcarpetas sin un archivo que vaya a guardarse en ellas.
* Devolver estructura de rutas.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios con carpeta temporal.
