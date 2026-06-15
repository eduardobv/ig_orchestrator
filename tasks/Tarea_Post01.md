# Tarea Post01 - CLI opcional

Version objetivo: posterior a `v1.0.1`

## Objetivo

Crear comandos CLI con Typer si mas adelante se decide exponer una interfaz de linea de comando completa.

Esta tarea queda fuera de la secuencia principal porque el flujo previsto se ejecutara desde un `.bat` llamando al punto de entrada principal y leyendo el JSON de entrada.

## Archivo

```text
src/ig_orchestrator/cli/commands.py
```

## Comandos

```text
init-db
import-batch
process-batch
process-account
retry-failed
inspect
report
```

Comandos reservados para futuro:

```text
rename
clean-duplicates
move-final
```

## Criterios de aceptacion

* Cada comando debe tener ayuda.
* Cada comando debe mostrar salida clara con Rich.
* Los errores deben ser comprensibles.
* No exponer secretos.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests de CLI con runner cuando sea viable.
