# Tarea 18 - Reporte Markdown

Version objetivo: `v1.18.0`

## Objetivo

Generar un reporte Markdown tras cada ejecucion.

## Archivo

```text
src/ig_orchestrator/reports/markdown_report_builder.py
```

## Contenido obligatorio

```text
Fecha y hora de ejecucion
```

Tabla:

```text
Username
Tipo
Urls
Fichero
Estado
Directory
```

## Reglas

* La informacion debe salir de SQLite.
* Si una URL tiene varios ficheros, listarlos en la misma celda.
* Si una URL no tiene ficheros, mostrar `0 files`.
* Guardar ruta del reporte en `runs.report_path`.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios del render Markdown.
* Test con una URL con 0 archivos y otra con N archivos.
