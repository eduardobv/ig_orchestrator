# Módulo: cli

Entrypoint `python -m ig_orchestrator`.

## Archivos
- `main.py` — argparse, `gui`, `--run`, `run_continue`, dry-run

`ig_orchestrator/main.py` es shim. Tests de humo parchean
`ig_orchestrator.cli.main` (no el shim).

## Tests
`tests/test_package_smoke.py`, `tests/test_main_batch_modes.py`
