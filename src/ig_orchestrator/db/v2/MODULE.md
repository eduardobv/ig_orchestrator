# Módulo: db/v2

Persistencia GUI (`data/orchestrator_gui.sqlite`, `user_version = 100`).

## Archivos
- `schema.sql`, `compat_views.sql`
- `adapters/` — `Gui*Repository` por entidad
- `catalog/` — importador y `GuiCatalogRepository`
- `lookups.py`, `cleanup.py` — reexportan los módulos de `db/`

Migraciones: `db/gui_migrations.py` lee `v2/schema.sql`.
