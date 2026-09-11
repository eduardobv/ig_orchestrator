# Módulo: gui/run

## Propósito
Ejecutar lote / cola, cancelar, renombrar, leftovers.

## Archivos
- `controller.py` — save/execute/queue/cancel, callbacks de proceso
- `process_runner.py` — subprocess + comandos
- `rename.py` — rename manual
- `leftovers.py` — carpetas no movidas

## Habla con
CLI `run_continue` vía ProcessRunner. SQLite vía draft/resume/queue.

## Tests
`tests/gui/test_run.py`, `tests/gui/test_rename.py`
