# Módulo: db/v2/adapters

Repositorios GUI que implementan la misma API que v1 sobre tablas v2.

## Archivos
- `batch.py`, `account.py`, `url_job.py`, `run.py`, `download.py`
- `mapping.py` — `_row_to_*`, paths relativos / `path_roots`

`db/gui_adapters.py` reexporta las cinco clases.

## Tests
`tests/db/test_gui_repositories.py`, `tests/db/test_gui_database.py`
