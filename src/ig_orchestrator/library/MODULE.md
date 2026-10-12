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

## Operaciones de disco (feat 4)

- `fsops.py` — `FsOperationService`: toda modificación de carpetas de la biblioteca pasa por aquí. `plan_*` (sin efectos) → `execute(plan)`:
  por paso, fila en `fs_operations` (`PLANNED`) → `os.rename` → `DISK_DONE` → actualizar `catalog_folders`/`catalog_accounts` (prefijo) → `COMMITTED`.
  `recover()` resuelve pasos interrumpidos mirando el disco; `undo(op_group)` crea las operaciones inversas.
- `fsops_plan.py` — `Plan`/`Step`/`Conflict` (códigos: `OFFLINE`, `OUTSIDE_ROOT`, `SRC_MISSING`, `DEST_EXISTS`, `DEST_IN_CATALOG`, `INVALID_NAME`, `INTO_ITSELF`, `IS_ROOT`, `NO_CHANGE`, `NO_PATH`, `ACCOUNT_IN_ACTIVE_BATCH`).
- `compat_lite.py` — `mirror_to_lite`: solo actualiza `accounts_dir.path` donde difiere (idempotente); `compat.lite.enabled` lo desactiva.
- Renombrar el username de una cuenta NO está aquí (feat 7); borrar/fusionar tampoco (feats 5, 7, 12).

## Ciclo de vida de cuentas (feat 5)

- `account_lifecycle.py` — `AccountLifecycleService`: `plan_mark_deleted(ids, suffix_on_conflict=)` calcula destino (`<carpeta eliminadas>\\<cuenta>` o con grupo), avisos
  (favorita, id de Instagram compartido, lote borrador) y bloqueos (lote en ejecución, destino existente); el movimiento de carpeta es un paso `MOVE_DIR` del diario de fsops.
  Tabla `account_lifecycle` guarda estado/favorito/ruta anteriores por grupo de operaciones: `restore_after_undo(op_group)` los repone tras `FsOperationService.undo`.
- `suggest_destination(account_id)` → `(carpeta destino, motivo)`: `<Modelo>-Deleted` hermana si existe, si no la carpeta de eliminadas; `plan_mark_deleted(dest_overrides=)` permite elegir otra (incluso inexistente: se crea con pasos `MKDIR`).
- Cuentas sin carpeta o ya dentro de la carpeta de eliminadas: solo cambia el estado. `DELETED` se oculta del catálogo igual que `ARCHIVED`.

## Renombrar / fusionar cuentas (feat 7)

- `account_rename.py` — `plan_rename(account_id, new_username, survivor=auto|old|new, confirm_unverified=)` → `RenamePlan` (`RENAME` simple, `MERGE`, `STATUS_ONLY`).
  Simple: `RENAME_DIR` + misma fila de `catalog_accounts` + alias en `account_usernames` + reescritura de URLs de stories en lotes borrador.
  Fusión: ambos ids de Instagram deben coincidir (o confirmación explícita si falta uno); se conserva la ubicación aún en uso (no `09.DELETED`/`-Deleted`), luego la de más contenido;
  `MERGE_DIR` (fichero a fichero con `merge.py`) + `RENAME_DIR`; en BD se re-apuntan lotes (filas del mismo lote se unen), alias e índice de ficheros y se elimina la fila sobrante.
  Deshacer: `FsOperationService.undo` + `restore_after_undo` (snapshot en `account_lifecycle.payload`); `undo_blocker` explica por qué no se puede (p. ej. filas del mismo lote fusionadas).
- `merge.py` — `plan_merge` / `execute_merge` / `can_undo` / `undo_merge`: `IDENTICAL`, `SUFFIXED` (`_1`), `DUPLICATE` (mismo `media_id` → `_duplicates/`), `MOVED`.
- `owner_groups.py` — `find_owner_groups` (pistas `RENAME_PROBABLE`, `SAME_CATEGORY`, `CROSS_CATEGORY`, `ALL_DELETED`), `ignore_group`.
- Los nombres de fichero de la biblioteca no contienen el username, así que renombrar la carpeta no obliga a renombrar ficheros.

## Códigos (auditoría)

`PATH_MISSING`, `OWNER_DUP` (detalle: `SAME_CATEGORY` / `DELETED_PAIR` / `ALL_DELETED` / `CROSS_CATEGORY`), `OWNER_MISMATCH`,
`FOLDER_MISMATCH`, `ONLY_IN_APP`, `ONLY_IN_LITE`, `COMPLETE_STALE`, `LAST_MODIFIED_MIXED`, `NAME_CASE`, `USERNAME_DUP`, `DISK_OFFLINE`.

## Reglas

- Sin dependencias de Tk. Nunca escribe en BD ni en disco.
- La carpeta del catálogo es la de la persona; lite guarda `<carpeta>/<username>` (ambas cuentan como coincidencia).

## Tests

`tests/library/test_audit.py`, `tests/gui/test_audit_dialog.py`.
