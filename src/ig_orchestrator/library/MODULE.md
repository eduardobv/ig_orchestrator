# Módulo: `library`

Herramientas de biblioteca (serie v3). Hoy: auditoría de solo lectura.

## Archivos

- `audit.py` — `run_audit(app_conn, lite_path, complete_path=None, *, check_disk=True, progress=None) -> AuditReport`.
  Abre lite/complete con `mode=ro`; el disco solo se toca con `os.path.exists`.
- `audit_report.py` — `Finding`, `AuditReport`, `Severity`, `render_markdown`, `render_csv` (CSV con BOM para Excel).
- `audit_cli.py` — `run_audit_cli` (rutas por defecto desde `app_settings['stories.accounts_db_path']`).

## Importador (feat 3)

- `import_bdsc1.py` — `import_from_bdsc1(app_conn, lite, complete, dry_run=, include_media=, library_root=)` → `ImportReport`.
  `accounts_complete` es la fuente principal; lite manda en las rutas. Cruza por username (sin mayúsculas); no sobrescribe `instagram_user_id`
  existente (incidencia `OWNER_MISMATCH`); las cuentas nuevas entran `ARCHIVED`. Todo en un `SAVEPOINT` (simulación = rollback).
- `media_index` se rellena desde `complete.media` por cuenta (clave `catalog_accounts.id`); se reindexa solo si cambia (`media_index_state`).
- `paths.py` (relativo ↔ absoluto a la raíz `LIBRARY`), `filenames.py` (regex del nombre de fichero), `import_cli.py`.
- Incidencias en `library_import_issues`: `USERNAME_DUP`, `OWNER_DUP`, `OWNER_MISMATCH`, `FOLDER_MISMATCH`, `PATH_CLASH`, `OUTSIDE_ROOT`, `ONLY_IN_APP`, `PARSE_ERROR`.

## Códigos (auditoría)

`PATH_MISSING`, `OWNER_DUP` (detalle: `SAME_CATEGORY` / `DELETED_PAIR` / `ALL_DELETED` / `CROSS_CATEGORY`), `OWNER_MISMATCH`,
`FOLDER_MISMATCH`, `ONLY_IN_APP`, `ONLY_IN_LITE`, `COMPLETE_STALE`, `LAST_MODIFIED_MIXED`, `NAME_CASE`, `USERNAME_DUP`, `DISK_OFFLINE`.

## Reglas

- Sin dependencias de Tk. Nunca escribe en BD ni en disco.
- La carpeta del catálogo es la de la persona; lite guarda `<carpeta>/<username>` (ambas cuentan como coincidencia).

## Tests

`tests/library/test_audit.py`, `tests/gui/test_audit_dialog.py`.
