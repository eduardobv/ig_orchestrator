# Tarea 21 - Modo dry-run

Version objetivo: `v1.21.0`

## Objetivo

Permitir probar sin enviar mensajes reales al bot ni mover archivos.

## Flag CLI

```bash
--dry-run
```

## Comportamiento

* No enviar mensajes a Telegram.
* No mover archivos.
* No ejecutar BAT.
* Si mostrar que habria hecho.
* Si validar URLs, rutas y configuracion.
* Si puede crear run simulado o resumen, dejando claro que es dry-run.

## Criterios de aceptacion

* Funciona en `process-batch` y `process-account`.
* No toca carpetas reales salvo que se decida crear estructura temporal explicitamente.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests de orquestador dry-run.
