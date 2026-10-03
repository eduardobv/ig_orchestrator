# Tarea 14 - Movimiento de archivos por tipo

Version objetivo: `v1.14.0`

## Objetivo

Mover archivos descargados a la carpeta correcta del usuario.

## Archivo

```text
src/ig_orchestrator/filesystem/file_mover.py
```

## Reglas

* `REEL` + video => `username/reels/`.
* `POST` + imagen => `username/`.
* `STORY` => `username/story/`.
* `HIGHLIGHTS` => `username/highlights/`.
* `REEL` con solo imagenes => reclasificar URL como `POST`.
* Evitar sobrescritura accidental.
* Si el destino existe, anadir sufijo seguro.

## Output

```text
List[DownloadFile]
```

## Criterios de aceptacion

* Registrar rutas resultantes para guardar en SQLite.
* No borrar archivos.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests con carpeta temporal.
