# Tarea 24 - Duplicados del renombrador y movimiento final

Version objetivo: `v1.24.0`

## Estado

No implementar en `v1.0.1`.

## Objetivo futuro

Detectar archivos renombrados como duplicados y mover la carpeta procesada al destino final.

## Archivos futuros

```text
src/ig_orchestrator/filesystem/duplicate_cleaner.py
src/ig_orchestrator/filesystem/final_move_service.py
```

## Duplicados

Buscar archivos cuyo nombre contenga:

```text
_duplicated
```

Estrategias:

```text
MOVE_TO_DUPLICATED_FOLDER
DELETE
KEEP
```

Estrategia inicial futura:

```text
MOVE_TO_DUPLICATED_FOLDER
```

## Movimiento final

Mover:

```text
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user
```

a:

```text
G:\4K Stogram\00.FAVORITES\Jhon Lennon\example_user
```

Si destino existe:

```text
FAIL
MERGE
RENAME_WITH_TIMESTAMP
```

Recomendacion inicial:

```text
FAIL
```

## Criterios futuros

* No borrar nada salvo configuracion explicita.
* No mezclar carpetas automaticamente al inicio.
* Actualizar `CHANGELOG.md`.
