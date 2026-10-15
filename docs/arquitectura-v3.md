# Arquitectura y guía técnica (v3.12)

Documento de referencia para quien (persona o IA) abra el proyecto sin contexto previo. Complementa `CLAUDE.md` (reglas), `docs/manual-usuario.md` (qué hace cada opción de la GUI), `docs/tutorial-v3.md` (cada feat con cómo probarlo) y `CHANGELOG.md` (historial exacto).
**Si cambias algo relevante, actualiza este documento.**

---

## 1. Estado del proyecto

| | |
|---|---|
| Versión | **v3.17.1** (tags `v3.2.0` … `v3.17.1`; los feats nuevos pedidos se añaden como feats incrementales de v3, ver `CLAUDE.md`) |
| Rama de trabajo | `v3/integration` (PR a `master` pendiente: se hace al terminar la serie v3) |
| Serie | v1.x CLI/Tk + SQLite v1 (rollback) · v2.x GUI modular + SQLite v2 · **v3.x** integra los procesos manuales en la app |
| Base de datos única (**bdapp**) | `data/orchestrator_gui.sqlite` (esquema v2 + parches aditivos v3). Es la fuente de verdad. |
| Base v1 | `data/orchestrator.sqlite`: solo CLI y rollback. No escribir en ella desde la GUI. |
| Plataforma | Windows, Python 3.11+, Tkinter. Rutas con `pathlib`/`os.path`. |

Objetivo de v3 (todo hecho, falta validar en uso real): la app, con su única base, carga el catálogo completo como `G:`, mueve/renombra/elimina cuentas y carpetas con efecto real en disco, tiene registro de instancias, **renombra sin scripts externos ni `G:`**, y se sincroniza con el disco.

### Glosario

| Término | Significado |
|---|---|
| **bdapp** | La base de datos de la app (`orchestrator_gui.sqlite`). |
| **Biblioteca / LIBRARY / G:** | `G:\4K Stogram` (`path_roots.LIBRARY`): `categoría\grupo\cuenta`. Todas las rutas en la base son **relativas** a ella (`rel_path`). |
| **sc1** | `GenerateDirMap` (script antiguo que generaba `accounts_lite`/`accounts_complete`). Sustituido por la sincronización incremental (feat 8). |
| **sc2** | `ManualRenameFiles` (renombrado externo). Sustituido por `renaming/` (feat 9); sigue disponible como motor `legacy_sc2`. |
| **bdsc1** | `accounts_lite.sqlite` / `accounts_complete.sqlite` en `G:`. Solo se importan una vez (feat 3) y, si `compat.lite.enabled`, se mantiene un espejo de `accounts_lite`. |
| **inst1** | Laptop 24/7 que descarga lotes; **pc1** = PC principal. Se registran en `instances`. |
| **Almacén (staging)** | Carpeta local opcional con cuentas renombradas pendientes de volcar a `G:`. |
| **Papelera** | `LIBRARY\.trash`. |
| **Índice** | `media_index`: por cada fichero de la biblioteca guarda `(account_id, kind, media_id, taken_at, owner_id, ext, suffix)`; permite renombrar sin `G:`. |

---

## 2. Mapa de módulos (`src/ig_orchestrator/`)

| Paquete | Responsabilidad | Piezas clave |
|---|---|---|
| `cli/` | Entrada `python -m ig_orchestrator` (`gui`, `init-db`, `run_continue`, `audit`, `scan`, `import`, `--input/--run`). | `cli/main.py` |
| `settings.py` | Lectura de `.env`. | |
| `input/` | Parser/importador de lotes JSON y clasificador de URLs. | |
| `db/` | Conexión, esquema v2, **migraciones aditivas** (`gui_migrations.py`), repositorios (`instances_repository.py`…), adaptadores v2. | `_patch_gui_schema`, `_patch_library_schema`, `_add_column_if_missing` |
| `orchestration/` | Orquestadores de descarga, reintentos, política (`processing_policy`). | |
| `telegram/` | Telethon y parser de respuestas del bot. | |
| `filesystem/` | Watcher, clasificación y movimiento de descargas, `story_inbox`. | |
| `reports/` | Reporte Markdown. | |
| `library/` | **Catálogo = disco**: rutas, escáner, operaciones de disco con diario, ciclo de vida, renombre de usernames, fusión, papelera, ficha, auditoría, importación bdsc1, espejo lite. | ver §3 |
| `renaming/` | Renombrado integrado (port de `sc2 --newRename`) y mover a biblioteca. | `service.py`, `planner.py`, `timeline.py`, `consult.py`, `mover.py`, `settings.py` |
| `staging/` | Almacén y volcado verificado. | `service.py` |
| `exchange/` | Intercambio entre instancias: manifiestos, publicar, traer, importar resultados, comparar con lote. | |
| `gui/` | Tkinter. `shell/app.py` compone **mixins** (la clase vive ahí; `gui/app.py` es solo un shim). Subpaquetes: `chrome` (menú/toolbar), `catalog`, `editor`, `batch_accounts`, `run` (ejecutar/renombrar), `library` (acciones de disco, escaneo, almacén, papelera…), `settings`, `shared` (i18n, helpers), `draft`. | |

Cada paquete importante tiene `MODULE.md` con sus interfaces. Leer el del paquete antes de tocarlo.

### 2.1 `library/` en detalle

| Módulo | Qué hace |
|---|---|
| `paths.py` | `to_rel`, `to_abs`, `rel_key` (comparación sin mayúsculas/barras), `parent_rel`. **Nunca** guardar rutas absolutas de `G:` en la base. |
| `fsops.py` + `fsops_plan.py` | **Único punto de entrada** para cambiar carpetas de la biblioteca (disco + bdapp). Contrato: `plan_*` (sin efectos) → vista previa → `execute(plan)`. Cada paso se registra en `fs_operations` (`PLANNED → DISK_DONE → COMMITTED`) para `recover()` tras un corte y `undo(grupo)`. Un cerrojo global evita dos operaciones de disco a la vez. Tipos: `MKDIR`, `MOVE_DIR`, `RENAME_DIR`, `RMDIR` (solo deshacer MKDIR), `MERGE_DIR`, `UNMERGE_DIR`. Planes: `plan_mkdir`, `plan_rename_folder`, `plan_move_folder`, `plan_move_account`, `plan_move_accounts` (varias, omite las bloqueadas). |
| `scanner.py` | Sincronización incremental por fecha de carpeta (`dir_mtime_*`). Ámbitos: `ALL`, `CATEGORY`, `ACCOUNT`, `DEEP`. Genera **hallazgos** (`scan_findings`): `NEW_FOLDER`, `MOVED_FOLDER`, `MISSING_FOLDER`, `OWNER_CHANGED`, `USERNAME_DUP`. Reemplaza `media_index` de cada `(cuenta, kind)` que relee. `scan_findings.accept_finding` hace que la app siga al disco. |
| `rules.py` | Reglas de sc1 configurables (`library.*`): carpetas no-cuenta (incluye `.trash`), subcarpetas de medios, extensiones, profundidad. |
| `filenames.py` | Parser de nombres `AAAA-MM-DD HH.MM.SS {media_id}_{owner}{sufijo}.{ext}`. |
| `account_lifecycle.py` | «Eliminada en Instagram»: mover a carpeta `-Deleted`/eliminadas con destino editable; restaurar; sugerir; etiquetar. **El estado sigue a la carpeta** tras un `MOVE_DIR` hecho desde la app: `location_kind` (deleted/inactive/normal), `_transition` (reglas: a `-Deleted` → DELETED; a `-Inactive` → INACTIVE; de `-Deleted`/`-Inactive` a normal → estado previo, según el **origen**), `preview_status_changes` (vista previa), `sync_with_location` (aplica; filas `DELETE`/`INACTIVATE`/`RESTORE` en `account_lifecycle`), `affected_accounts(grupo)`; se llama desde `gui/library/fsops_actions._run_plan` y tras deshacer. |
| `account_rename.py` | «Cambió de username»: renombrar la cuenta (misma PK) o fusionarla con otra; reasigna `media_index`. |
| `merge.py` | Fusión de carpetas sin sobrescribir (idéntico → omitir; mismo `media_id` → `_duplicates`; mismo nombre distinto tamaño → sufijo) con manifiesto para deshacer. |
| `owner_groups.py` | Detección y resolución de ids de Instagram repetidos. |
| `folder_suggestions.py` | Sugerencias de carpeta destino (inversas `X ↔ X-Deleted/-Inactive`, hasta 3; crea la hermana si falta) y búsqueda de carpetas por nombre. Usado por `gui/library/folder_picker.pick_folder`. |
| `account_card.py` | Ficha: validar y guardar id, fecha del primer post, notas, favorita. |
| `trash.py` | Papelera: cuarentena (caducidad según `trash.retention_days`), restaurar, vaciar con palabra `ELIMINAR`, `remove_from_catalog` (borra las filas de cuentas purgadas que no estén en un lote), `expired()`. Tabla `trash_items` (se crea sola). |
| `import_bdsc1.py` / `import_cli.py` | Importación única desde `accounts_lite/complete` (simulación + aplicar, con copia de seguridad). |
| `audit*.py` | Auditoría bdapp ↔ bdsc1 ↔ disco (códigos y gravedad; exporta MD/CSV). |
| `compat_lite.py` | Espejo `accounts_lite`: `mirror_to_lite`, `add_to_lite`, `lite_path_from_settings` (respeta `compat.lite.enabled`). |

### 2.2 `renaming/` en detalle

- `files.py`: regex (`^\d{10,}\.(jpg|jpeg|mp4)$` para descargas), listados con `os.listdir` (el **orden importa** para reproducir `sc2`).
- `timeline.py`: asignación de fechas e id de propietario. `TimelineContext(rng, now, forced_user_id, flag_new)`. **El orden de llamadas al generador aleatorio es el de `sc2`**; no reordenar.
- `planner.py`: `process_folder_tree` recursivo; `ConsultProvider` (`DiskConsultProvider` o `IndexConsultProvider`); `RealOps`/`DryOps` → vista previa y ejecución comparten código.
- `consult.py`: proveedor desde `media_index`, `write_through`, `verify_index`, `has_index`, `index_status`.
- `mover.py`: `move_renamed_folder` (semántica sc2: carpeta padre de la cuenta + nombre de la carpeta descargada), `move_folder_to` (destino explícito), `preview_move[_to]`. Fusiona sin sobrescribir; un choque aborta esa cuenta.
- `service.py`: `RenameService(conn).preview(job, seed, now)` / `.run(preview)`. `RenameJob(source_folder, start_now_date, new_accounts, no_duplicated, move_renamed, reference='auto|index|disk', destination='library|staging')`. Estados por cuenta: `RENAMED`, `NEW`, `SKIPPED`, `MOVE_CONFLICT`, `NO_FILES`, `ERROR`, `RENAMED_PENDING_MOVE`, `STAGED`. `move_pending()` mueve lo pendiente. Historial en `rename_runs` / `rename_run_accounts`.
- Cuentas «registradas» = `catalog_accounts.rel_path IS NOT NULL`. Cuenta nueva: se registra (id, fecha de inicio, ruta, carpeta) **solo tras mover con éxito** (o al volcar).
- `settings.py`: `renaming.engine`, `renaming.preview`, `staging.*`, `compat.lite.enabled` (con valores por defecto y tolerancia a base v1).

### 2.3 `staging/`
`StagingService`: `record`, `plan` (NUEVA/FUSIONAR/CONFLICTO/FALTA), `dump` (copia → comprueba tamaño → `os.replace` → borra origen; reanudable; sin sobrescribir), `summary`, `forget_dumped`. Destino recalculado al volcar desde `rel_path`.

---

## 3. Modelo de datos (bdapp)

Tablas principales (los parches viven en `db/gui_migrations.py`; todos son **aditivos e idempotentes**):

| Grupo | Tablas |
|---|---|
| Lotes y descargas (v2) | `batches`, `batch_accounts`, `batch_urls`, `batch_runs`, `batch_queues`, `batch_queue_items`, `downloaded_files`, `bot_errors`, `duplicate_urls`, tablas de estados (`*_statuses`), `url_sources`, `media_types`, `publication_types` |
| Catálogo | `catalog_accounts` (`username`, `instagram_user_id`, `folder_id`, `status_id`, `is_favorite`, `start_init_date`, `rel_path`, contadores, `last_media_at`, `disk_state`, `scan_state`, `dir_mtime_*`, `notes`, `previous_rel_path`, `deleted_at`, `legacy_lite_id`), `catalog_folders` (`rel_path`, `kind`), `catalog_account_statuses` (ENABLED, INACTIVE, DISABLED, CHANGED, ARCHIVED, DELETED), `account_usernames`, `account_lifecycle`, `owner_dup_ignored`, `path_roots` (`LIBRARY`, `WORKING`, `TELEGRAM_DESKTOP`, `FINAL_BASE`) |
| Disco | `fs_operations` (diario), `scan_runs`, `scan_findings`, `library_import_issues`, `trash_items` |
| Índice | `media_index`, `media_index_state` |
| Renombrado | `rename_runs`, `rename_run_accounts` (incluye columnas de pendiente: `manual_path`, `destination`, `account_id`, `spec`, `resolved`) |
| Almacén | `staged_accounts`, `dump_runs` |
| Instancias / intercambio | `instances`, `exchange_publications`, `exchange_imports` |
| Ajustes | `app_settings(key, value, value_type, updated_at)` |

`disk_state`: `PRESENT`, `MISSING`, `TRASHED`, `UNKNOWN`. `media_index.kind`: 0 raíz, 1 reels, 2 story, 3 highlights; `ext`: 0 jpg, 1 jpeg, 2 mp4; `taken_at`: fecha del nombre como segundos naive.
Cambiar el esquema: añade el parche en `gui_migrations.py` (`CREATE TABLE IF NOT EXISTS` / `_add_column_if_missing`) y comprueba que una base antigua se actualiza. Se hace copia de seguridad antes de la migración de biblioteca v3.

### Claves de `app_settings`

| Clave | Para qué |
|---|---|
| `ui.*` | Idioma, tema, vista del catálogo, colores, posición de ventana, paneles visibles |
| `processing.stories_first` | Barridas de stories |
| `notify.*` | Aviso por Telegram al terminar lote |
| `stories.inbox_path`, `stories.accounts_db_path` | Stories Inbox y ruta de `accounts_lite` (usada por el espejo) |
| `retention.downloaded_files` | Retención de la tabla de ficheros |
| `compat.lite.enabled` | Mantener actualizado `accounts_lite` (1/0) |
| `library.deleted_folder_rel`, `library.deleted_keep_group`, `library.*` (reglas) | Carpeta de eliminadas y reglas del escáner |
| `renaming.engine` (`integrated`/`legacy_sc2`), `renaming.preview` | Motor y vista previa |
| `trash.retention_days` | Días de retención de la papelera (0 = sin límite) |
| `staging.root`, `staging.after_rename` (`ASK`/`STAGING`/`LIBRARY`) | Almacén |

---

## 4. Invariantes y reglas de diseño (no romper)

1. **bdapp es la fuente de verdad.** Nada se lee de `accounts_lite` para decidir; el espejo es solo de salida y se puede apagar.
2. **Toda operación sobre carpetas de la biblioteca pasa por `FsOperationService`** (plan → vista previa → ejecutar, con diario y deshacer). Excepciones documentadas: renombrado/mover de descargas (`renaming/`), volcado (`staging/`) y papelera (`trash.py`), que tienen su propia lógica de seguridad.
3. **Nunca sobrescribir.** Choques de nombre → conflicto o sufijo, nunca reemplazo.
4. **Rutas relativas** a `LIBRARY` en la base. La letra de unidad cambia sin migrar nada.
5. **Una cuenta = una PK.** Renombrar el username no cambia el id; el índice usa `account_id`.
6. **Vista previa = ejecución**: mismo código (`DryOps`/`RealOps`), misma semilla y reloj.
7. **Sin `G:`** las acciones de disco se desactivan o avisan; renombrar sigue funcionando con el índice.
8. **No se escribe en la base v1 desde la GUI.**
9. **No commitear** `.env`, `*.session*`, bases SQLite reales, secretos.
10. Cada cambio actualiza **CHANGELOG, manual de usuario, tutorial (si v3 en curso), MODULE.md y este documento** (ver `CLAUDE.md`).

---

## 5. Flujos principales

| Flujo | Recorrido |
|---|---|
| **Descargar un lote** | Editor → *Registrar lote* → *Ejecutar* → orquestador envía URLs al bot (Telethon) → watcher detecta ficheros → mueve a `WORKING\usuario\…` → reporte. |
| **Renombrar** | *Lote → Renombrar* → modal → `RenameService.preview` (árbol, semilla) → `run` en hilo con su propia conexión → mueve a `G:` o al almacén o deja pendiente → refresca contadores/índice (`LibraryScanner.scan(ACCOUNT)` o escritura inmediata en el índice). |
| **Sin G:** | `reference=index` + `RENAMED_PENDING_MOVE` → `Mover renombradas pendientes…` al volver `G:`. |
| **Almacén** | `destination=staging` → `staged_accounts` → `Pendiente de volcar a G:…` → `StagingService.dump`. |
| **Sincronizar** | `LibraryScanner` → hallazgos → *Aceptar/Ignorar*. |
| **Mover/renombrar carpetas, arrastrar** | `FsOperationService.plan_*` → `confirm_plan` (modal) → `execute` → `_after_fsops_change` (espejo lite, recarga del catálogo). |
| **Instancias** | `exchange`: `publish` (paquete + manifiesto en la compartida) → `pull`/`result_import` en el PC principal. |

---

## 6. Cómo añadir cosas (recetas)

**Una opción de menú / menú contextual:** crea el método en un *mixin* de `gui/` (o en el existente), regístralo en `gui/chrome/menubar.py` y/o en el menú contextual de `gui/catalog/panel.py`; añade las claves en **`gui/shared/locales/es.json` y `en.json`** (no en `gui/locales`); añade el mixin a la lista de `gui/shell/app.py`; documenta en `docs/manual-usuario.md`.
**Una operación de disco sobre la biblioteca:** añade un `plan_*` en `fsops.py` (con `Conflict`s) y, si necesita un tipo nuevo, en `fsops_plan.OpType` + `_disk`/`_apply_db`/`undo`; muéstralo con `gui/library/plan_dialog.confirm_plan`.
**Una tabla o columna:** parche aditivo en `db/gui_migrations.py` + test con una base antigua.
**Un ajuste:** `write_setting`/`_value` (`renaming/settings.py` o `gui/settings/dialog.py`), tolerando base v1.
**Ventanas:** cualquier `tk.Toplevel` se centra solo en el monitor de la ventana principal (`gui/shared/window_position.install_auto_centering`, instalado en `gui/shell/app.py`); no hace falta código por diálogo. Las ventanas sin borde (`overrideredirect`) no se mueven.
**Colores del catálogo:** `gui/catalog/colors.py` (*Eliminada* comparte el color de *Disabled*).
**Tareas largas en la GUI:** hilo con su propia conexión (`connect(settings.sqlite_gui_db_path)`), cola `queue.Queue` + `root.after` para el progreso; nunca tocar Tk desde el hilo.

---

## 7. Pruebas

- `python -m pytest -q` (≈530 pruebas, ~25 s). `tests/filesystem/test_file_watcher.py::test_watch_downloaded_files_returns_new_stable_files` es **intermitente** (tiempos): repetir antes de investigar.
- `tests/renaming/test_parity_sc2.py` carga `sc2` desde `D:\Archivos\Scripts\IG\ManualRenameFiles` y se **omite** si no está.
- Usar SQLite temporal (`init_gui_database(tmp)`), bibliotecas falsas en `tmp_path`, nada de Telegram real.
- Pruebas de GUI: instanciar `InstagramOrchestratorApp` con una copia de la base y parchear `messagebox`/`confirm_plan`.
- Versión: al subir de versión actualizar `src/ig_orchestrator/__init__.py`, `pyproject.toml` y los asserts de `tests/test_package_smoke.py`.

### Trampas conocidas (Windows)
- Los *heredocs* de Bash corrompen barras invertidas: escribir scripts con la herramienta de ficheros o usar `Edit`.
- Salida de consola cp1252: usar `PYTHONIOENCODING=utf-8` al imprimir Unicode.
- `catalog_accounts` solo admite una fila por `rel_path` (índice único).
- `parse_instagram_filename` (sc1) exige separador (`_`, `-` o espacio) tras el owner; `parse_media_name` (índice) es más permisivo: nombres como `…_5000(1).jpg` entran al índice pero no al escáner.

---

## 8. Limitaciones conocidas y pendiente

| Tema | Estado |
|---|---|
| PR `v3/integration` → `master` | Pendiente (tras validar). |
| «Eliminar carpeta vacía» | Hecho en v3.16 (`plan_delete_empty_folder`). |
| Probar con `G:` real | Renombrado sin `G:`, almacén/volcado, publicar/importar con inst1 y papelera **solo probados con copias/datos sintéticos**. |
| Fusión genérica carpeta↔carpeta | **Descartada** por riesgo (reasignar cuentas de grupos fusionados); solo existe la fusión de cuentas (feat 7). |
| Papelera | Hecho en v3.16: retención configurable (avisa, nunca borra sola) y «quitar también del catálogo». |
| Almacén | Solo estructura `by_target`; segundo renombrado de una cuenta nueva ya almacenada queda sin ruta hasta volcar. Indicador en la barra de estado hecho en v3.16. |
| Auditoría | `INDEX_STALE`/`INDEX_MISSING` hechos en v3.16. |
| Arrastrar y soltar | Probado por llamada directa al manejador, no con ratón. |
| `compareProcess` de sc2 | Aparcado (feat propio si se quiere). |

---

## 9. Dónde mirar cada cosa

| Pregunta | Documento |
|---|---|
| ¿Qué hace esta opción/menú/botón? ¿Qué abre? | `docs/manual-usuario.md` |
| ¿Cómo uso/pruebo el feat X? | `docs/tutorial-v3.md` |
| ¿Qué cambió y cuándo? ¿Qué se probó? | `CHANGELOG.md` |
| ¿Por qué se diseñó así / qué se decidió y qué no se hizo? | `tasks/done/v3/feat-*.md` (sección «Resultado de la implementación») y `docs/v3-status.md`, `docs/plan-v3-features.md` |
| ¿Cómo está organizado el código y la base? | este documento + `MODULE.md` de cada paquete + `docs/modularizacion_v2.md` |
| Reglas de trabajo y comandos | `CLAUDE.md`, `Agents.md` |
| Plan inicial del proyecto | `tasks/done/PLAN.md` (histórico) |
