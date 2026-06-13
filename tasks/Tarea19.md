# Tarea 19 - CLI

Version objetivo: `v1.19.0`

## Objetivo

Crear comandos CLI con Typer.

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
