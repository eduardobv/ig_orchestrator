# Módulo: gui/stories

## Propósito
Diálogo **Organizar stories**: mover ficheros `{username}-…` desde una
carpeta inbox a `{accounts_dir.path}\story`.

## Archivos
- `dialog.py` — mixin + Toplevel
- `settings.py` — `stories.inbox_path` y `stories.accounts_db_path` en
  `app_settings`

## Habla con
- `filesystem/story_inbox.py` (puro, sin Tk)
- SQLite GUI solo para recordar rutas
- SQLite **externa** `accounts_dir` (solo lectura)

## No debe
Escribir en `orchestrator.sqlite` ni en la BD de `accounts_dir`.
Lanzar `run_continue`.

## Tests
`tests/filesystem/test_story_inbox.py`, `tests/gui/test_stories_dialog.py`
