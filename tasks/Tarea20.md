# Tarea 20 - Modo dry-run

Version objetivo: `v1.20.0`

## Objetivo

Permitir probar sin enviar mensajes reales al bot ni mover archivos.

## Modo de ejecucion

El punto de entrada debe poder activar dry-run desde el flujo principal, incluido el uso desde un `.bat`.

## Comportamiento

* No enviar mensajes a Telegram.
* No mover archivos.
* No ejecutar BAT.
* Si mostrar que habria hecho.
* Si validar URLs, rutas y configuracion.
* Si puede crear run simulado o resumen, dejando claro que es dry-run.

## Criterios de aceptacion

* Funciona al procesar un lote y al procesar una cuenta.
* No toca carpetas reales salvo que se decida crear estructura temporal explicitamente.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests de orquestador dry-run.
