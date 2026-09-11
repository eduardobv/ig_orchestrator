# Módulo: db/v1

Schema CLI rollback (`data/orchestrator.sqlite`).

## Archivos
- `schema.sql` — canónico; `db/migrations.py` lo carga

Los repositorios v1 siguen en `db/*_repository.py` porque son la API de
despacho (`__new__` elige `Gui*Repository` si `user_version >= 100`).
No moverlos sin revisar ese ciclo de imports.
