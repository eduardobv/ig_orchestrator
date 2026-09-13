# Módulo: db

SQLite es la fuente de verdad. v1 (`orchestrator.sqlite`) y v2 GUI
(`orchestrator_gui.sqlite`) no se mezclan.

| Qué | Dónde |
|---|---|
| Conexión WAL | `connection.py` |
| `user_version` / `is_gui_schema` | `schema_mode.py` |
| Repositorios v1 + despacho a adapters v2 | `*_repository.py` en este directorio |
| Schema v1 | `v1/schema.sql` (cargado por `migrations.py`) |
| Schema v2, adapters, catálogo | `v2/` |

`batch_accounts.priority` (INTEGER, default 0) se añade con
`_add_column_if_missing` sin subir `user_version`.

API pública: `ig_orchestrator.db` (`__init__.py`). Las rutas antiguas
(`gui_adapters`, `catalog_importer`, `gui_migrations`) son shims.

## Tests
`tests/db/`
