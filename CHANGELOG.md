# Changelog

## v3.15.0 - feat-uc2-15: el estado también sigue a las carpetas -Inactive

Fecha: 2026-10-14 · Rama: `v3/integration` (feat incremental de v3)

### Creado
* `tasks/done/v3/feat-uc2-15.md`; pruebas nuevas en `tests/library/test_status_follows_folder.py`.

### Modificado
* `library/account_lifecycle.py`: `location_kind` (deleted / inactive / normal), `_transition` (tabla de reglas), `sync_with_location` y `preview_status_changes` con **origen** y destino; nuevo tipo `INACTIVATE` en `account_lifecycle` (también deshecho por `restore_after_undo`).
* `gui/library/fsops_actions.py` (texto «Inactiva» en la vista previa), locales.
* Documentación: manual, tutorial (Feat 14/15), arquitectura, plan, README, `MODULE.md`; versión 3.15.0.

### Comportamiento
* Mover a `…-Inactive` → **Inactiva**; mover de `-Deleted`/`-Inactive` a una carpeta normal → estado anterior (o Activa). De `-Deleted` a `-Inactive` (y al revés) cambia directamente. Una cuenta Inactiva a mano que se mueve entre carpetas normales no cambia.

### Pruebas ejecutadas
`python -m pytest`: 559 passed (1 omitido).

## v3.14.0 - feat-uc2-14: estado según carpeta, color único de eliminadas y ventanas centradas

Fecha: 2026-10-14 · Rama: `v3/integration` (feat incremental de v3)

### Creado

* `gui/shared/window_position.py` (`install_auto_centering`, `center_on_monitor`, `centered_position`, `monitor_rect`).
* `tasks/done/v3/feat-uc2-14.md`; `tests/library/test_status_follows_folder.py`; `tests/gui/test_window_position.py`.

### Modificado

* `gui/catalog/colors.py`: *Eliminada* usa el color de *Disabled*.
* `library/account_lifecycle.py`: `sync_with_location`, `preview_status_changes`, `affected_accounts` (el estado sigue a la carpeta `-Deleted`); `library/fsops.py` (`_accounts_under` devuelve el estado).
* `gui/library/fsops_actions.py` (vista previa con los cambios de estado y sincronización tras mover), `gui/library/fsops_history_dialog.py` (tras deshacer), `gui/shared/helpers.py`, `gui/shell/app.py`, locales.
* Documentación: manual, tutorial (Feat 14), arquitectura, plan, README, `MODULE.md`; versión 3.14.0.

### Pruebas ejecutadas

`python -m pytest`: 556 passed. Prueba con la app real: todas las ventanas abiertas quedan centradas en el monitor (±1 px). **No probado con `G:` real.**

## v3.13.0 - feat-uc2-13: mover cuentas con sugerencias, búsqueda, nueva carpeta y selección múltiple

Fecha: 2026-10-14 · Rama: `v3/integration` (feat incremental de v3)

### Creado

* `library/folder_suggestions.py`: `suggest_destinations` (hasta 3 sugerencias inversas `X ↔ X-Deleted/X-Inactive`, carpeta de eliminadas, dónde estaba antes; crea la hermana si falta) y `find_folder_matches`.
* `tasks/done/v3/feat-uc2-13.md`; `tests/library/test_folder_suggestions.py`.

### Modificado

* `gui/library/folder_picker.py`: `pick_folder(..., account_ids=)` con **Sugerencias**, **Buscar carpeta** (salta en el árbol; Enter/flechas), **Nueva carpeta aquí…** (crea de inmediato, deshacible).
* `gui/catalog/panel.py`: el clic derecho conserva la selección múltiple; la entrada del menú pasa a «Mover las N cuentas a otra carpeta…».
* `gui/library/catalog_advanced.py` (pasa las cuentas al selector), locales, versión 3.13.0.
* Reglas permanentes en `CLAUDE.md`/`Agents.md`: cada petición cierra con documentación completa y versión incremental.
* Documentación: manual, tutorial (Feat 13), arquitectura, plan, README.

### Pruebas ejecutadas

`python -m pytest`: 541 passed. Prueba de GUI con copia de la base: selección múltiple conservada tras el clic derecho; selector con sugerencias y búsqueda. **No probado con `G:` real.**

## Docs (2026-10-14) - guía técnica para sesiones nuevas

* Nuevo `docs/arquitectura-v3.md` (estado, módulos, modelo de datos, ajustes, invariantes, recetas, pruebas, limitaciones) y `docs/README.md` (índice).
* `CLAUDE.md`: sección «Cómo trabajar en una sesión nueva» (consultar siempre la documentación antes de responder o cambiar), estado actualizado a v3.12.0 y estructura con `library/`, `renaming/`, `staging/`, `exchange/`. `Agents.md` con el mismo aviso. Sin cambios de código.

## Docs (2026-10-14) - manual de uso

* Nuevo `docs/manual-usuario.md`: cada menú, menú contextual y modal con lo que hace y a qué invoca; preguntas frecuentes (carpeta vacía, cambiar ownerId, eliminar cuenta/carpeta, añadir ficheros a mano). Sin cambios de código.

## v3.12.0 - feat-uc2-12: catálogo avanzado (ficha, multiselección, arrastrar, papelera)

Fecha: 2026-10-12 · Rama: `v3/integration`

### Creado

* `library/account_card.py` + `gui/library/catalog_advanced.py`: **Ficha de la cuenta** (id de Instagram, fecha del primer post, favorita, notas; solo lectura: carpeta, estado de disco, contadores, nombres anteriores, últimos lotes y operaciones) con validaciones (id numérico, avisa si otro registro tiene el mismo id o si difiere del id mayoritario de los ficheros; fecha válida y no futura). Columna `catalog_accounts.notes`.
* **Selección múltiple** en el árbol del catálogo y **Mover cuentas seleccionadas** como un único plan (`FsOperationService.plan_move_accounts`): las que no se pueden mover se omiten con una nota y todas forman un solo grupo deshacible.
* **Arrastrar y soltar** cuentas (o una carpeta) sobre una carpeta del árbol: abre la vista previa del plan, nunca ejecuta directamente.
* **Abrir carpeta** y **Copiar ruta** en el menú contextual.
* `library/trash.py` + tabla `trash_items`: **papelera** (`LIBRARY\.trash\<fecha>__<usuario>`, mismo volumen, instantánea), **restaurar** (si el sitio original está libre), **vaciar** con confirmación escribiendo `ELIMINAR`. Bloqueos: lote en ejecución, datos pendientes en el almacén, biblioteca no disponible. `.trash` se añade a las carpetas que el escáner no toma como cuentas.
* Tests: `tests/library/test_catalog_advanced.py`.

### Modificado

`library/fsops.py`, `library/rules.py`, `gui/catalog/panel.py` (selectmode extended, arrastre, menú), `gui/chrome/menubar.py` (Catálogo → Ficha / Papelera), `gui/shell/app.py`, locales, `README.md`, versión 3.12.0. `docs/feat-uc2-12.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

`python -m pytest`: 535 passed. Prueba de GUI con copia de la base: soltar 2 cuentas sobre una carpeta (plan de 2 pasos, movidas) y enviar otra a la papelera. **No probado con tu `G:` real.**

## v3.11.0 - feat-uc6-11: almacén de procesadas y volcado a G:

Fecha: 2026-10-12 · Rama: `v3/integration`

Renombrar y entregar a la biblioteca pasan a ser pasos separados: las carpetas renombradas pueden quedarse en un **almacén local** y se **vuelcan** a `G:` cuando quieras.

### Creado

* `src/ig_orchestrator/staging/` (`StagingService`: registro del almacén, plan de volcado, volcado verificado y reanudable, `MODULE.md`).
* Tablas `staged_accounts` y `dump_runs`.
* GUI: **Lote → Pendiente de volcar a G:…** (`gui/library/staging_panel.py`): cuentas, ficheros, tamaño, destino (Nueva / Fusionar / Conflicto), *Volcar seleccionadas*, *Volcar todo*.
* Ventana de Renombrar: selector **Destino de las procesadas** (Biblioteca / Almacén) y las opciones invalidan la vista previa si cambian.
* Ajustes → Catálogo: **carpeta del almacén** y **qué hacer tras renombrar** (preguntar / almacén / biblioteca).
* `mover.move_folder_to` / `preview_move_to` (destino explícito).
* Tests: `tests/staging/test_staging.py`.

### Comportamiento

* El almacén replica la estructura de la biblioteca (`categoría\grupo\carpeta`), así que el volcado es una fusión directa.
* Volcado: copia cada fichero, comprueba el tamaño y solo entonces lo borra del almacén; nunca sobrescribe (si un nombre ya existe, esa cuenta queda en *Conflicto*). Si se corta, se vuelve a lanzar y continúa sin duplicar.
* El destino se recalcula al volcar: si la cuenta se movió o renombró en el catálogo mientras esperaba, va a su sitio nuevo.
* Tras volcar: contadores e índice se refrescan, las cuentas nuevas reciben su ruta (y entran en `accounts_lite` si el espejo está activo).
* Se comprueba el espacio libre del almacén antes de mover.

### Modificado

`renaming/service.py`, `renaming/mover.py`, `renaming/settings.py`, `db/gui_migrations.py`, `gui/run/rename_preview_dialog.py`, `gui/settings/dialog.py`, `gui/chrome/menubar.py`, `gui/shell/app.py`, locales, `README.md`, `CLAUDE.md`, versión 3.11.0. `docs/feat-uc6-11.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

`python -m pytest`: 528 passed. Prueba de GUI con copia de la base: renombrar hacia el almacén y abrir el panel. **No probado con tu `G:` real.**

## v3.10.0 - feat-uc5-10: renombrar sin la unidad G: (índice en la app)

Fecha: 2026-10-12 · Rama: `v3/integration`

El renombrado puede usar el **índice de ficheros de la app** (`media_index`, por id de cuenta) en lugar de leer la biblioteca. Con `G:` desconectada, renombra en su sitio y deja la carpeta **pendiente de mover**.

### Creado

* `renaming/consult.py` - `IndexConsultProvider` (mismos datos que el proveedor de disco), `write_through` (los ficheros recién renombrados entran en el índice), `has_index`, `index_status`, `verify_index`.
* `gui/library/index_actions.py` - **Lote → Mover renombradas pendientes…** y **Catálogo → Verificar índice con el disco**.
* Columnas nuevas en `rename_run_accounts` (`manual_path`, `destination`, `account_id`, `spec`, `resolved`) para recordar lo pendiente.
* Tests: `tests/renaming/test_offline_index.py`.

### Comportamiento

* **Referencia automática:** si la carpeta de la cuenta es accesible se lee del disco (exacto); si no, del índice. Casilla **«Usar el índice de la app»** para forzar el índice.
* **Sin índice y sin disco:** la cuenta se omite con motivo `NO_INDEX`.
* **Biblioteca no disponible:** se renombra en la carpeta de descargas, estado `RENAMED_PENDING_MOVE`; las cuentas nuevas se registran al mover. «Mover renombradas pendientes» las mueve cuando vuelve `G:` y refresca contadores e índice.
* **Equivalencia comprobada:** con la misma semilla, índice y disco dan los mismos nombres.
* **Verificar índice:** lista altas/bajas respecto al disco y permite aceptar el disco (reindexa la cuenta).

### Modificado

`renaming/service.py`, `db/gui_migrations.py`, `gui/run/rename_preview_dialog.py`, `gui/chrome/menubar.py`, `gui/shell/app.py`, locales, `README.md`, versión 3.10.0. `docs/feat-uc5-10.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

`python -m pytest`: 520 passed. No probado con `G:` real desconectada físicamente.

## v3.9.0 - feat-uc1-9: renombrado integrado (port de `sc2 newRename`)

Fecha: 2026-10-12 · Rama: `v3/integration`

El renombrado se ejecuta **dentro de la app**, con el mismo resultado que `ManualRenameFiles --newRename`: sin subproceso, sin rutas fijas a `D:\Archivos\Scripts\...`, leyendo las cuentas de la base de datos de la app (no de `accounts_lite`) y con **vista previa** de lo que se va a hacer.

### Creado

* `src/ig_orchestrator/renaming/` - `files.py`, `timeline.py` (asignación de fechas, con el mismo orden de llamadas al azar que `sc2`), `planner.py` (recorrido de carpetas con `DryOps`/`RealOps`: la vista previa y la ejecución son el mismo código), `mover.py` (mover/fusionar a la biblioteca sin sobrescribir), `service.py` (`RenameService.preview/run`), `settings.py`, `MODULE.md`.
* Tablas `rename_runs` y `rename_run_accounts` (historial de cada renombrado).
* GUI: ventana **Renombrar descargas** (`gui/run/rename_preview_dialog.py`): «¿Dónde están los ficheros?» (tu carpeta de trabajo o las carpetas de las instancias registradas, o cualquier ruta), opciones, **Vista previa** (árbol cuenta → fichero → nombre nuevo y fecha) y **Otra semilla**; ejecución en segundo plano con resultado por cuenta (`gui/run/integrated_rename.py`).
* Ajustes: **motor de renombrado** (integrado / script externo `sc2`) y «mostrar siempre la vista previa» en `Ajustes → Procesamiento`; casilla **«Mantener actualizado accounts_lite»** (`compat.lite.enabled`) en `Ajustes → Catálogo`.
* `compat_lite.add_to_lite` (cuentas nuevas registradas también en lite mientras el espejo esté activo).
* Tests: `tests/renaming/` (paridad con `sc2`, servicio, ajustes).

### Comportamiento

* **Paridad con `sc2`:** con la misma semilla y el mismo reloj, ambos motores dejan exactamente los mismos nombres (9 casos: cuentas existentes y nuevas, bloques por debajo/entre/por encima de la biblioteca, duplicados, subcarpetas).
* **Cuentas** salen de la app: registrada = tiene ruta en la biblioteca. Una cuenta nueva (declarada en el lote) se **registra una sola vez en la app** (id de Instagram, fecha de inicio, ruta, carpeta) y, si está activo el espejo, también en `accounts_lite`.
* **Escritura inmediata:** tras mover una carpeta, se refrescan los contadores, la fecha del último contenido y el índice de ficheros de esa cuenta (sin esperar a «Sincronizar»).
* La vista previa usa una **semilla**; lo que ves es lo que se aplica. «Cancelar» durante la ejecución para antes de la siguiente cuenta.

### Modificado

* `gui/run/rename.py` (elige motor), `gui/run/controller.py`, `gui/settings/dialog.py`, `gui/shell/app.py`, `db/gui_migrations.py`, locales, `README.md`, versión 3.9.0.
* `docs/feat-uc1-9.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 511 passed. Prueba de la GUI con una copia de tu base: vista previa → ejecutar → ficheros renombrados y movidos a la carpeta de la cuenta, descargas vacías, historial guardado. **No probado con tu `G:` real.**

## v3.8.0 - feat-uc3-8: sincronización incremental disco ↔ app (sustituye a `sc1`)

Fecha: 2026-10-12 · Rama: `v3/integration`

Mantiene `bdapp` al día con el disco **leyendo lo mínimo**: una consulta de fecha de modificación por carpeta de cuenta y subcarpeta decide qué relistar. Solo a petición, nunca al arrancar, y **no escribe en el disco**.

### Creado

* `library/scanner.py` (`LibraryScanner.scan(scope, deep=…)`, `accept_finding`, `ignore_finding`, `list_findings`), `library/rules.py` (reglas de `sc1` ahora configurables en `app_settings`), `library/scan_cli.py`, `filenames.parse_instagram_filename` (mismo parser que `sc1`).
* Tablas `scan_runs`, `scan_findings`; columnas `catalog_accounts.dir_mtime_{root,story,reels,highlights}` y `scan_state`.
* Comando `python -m ig_orchestrator scan [--scope all|category|account] [--path REL] [--account USER] [--deep]`.
* GUI: `Catálogo → Sincronizar con el disco` (**Rápida**, **Verificar categoría**, **Verificar cuenta**, **Verificación completa…**, **Hallazgos…**), clic derecho en cuenta/carpeta, ventana de **hallazgos** (Aceptar / Ignorar).
* Tests: `tests/library/test_scanner.py` (14) y `tests/gui/test_scan_actions.py`.

### Cómo funciona

* **Primera vez tras importar:** se toma la importación como base (solo se anota la fecha de cada carpeta) y se relistan únicamente las cuentas sin id de Instagram. Las siguientes sincronizaciones relistan solo las carpetas cuya fecha cambió.
* **Detecta (sin aplicar solo):** carpeta nueva, carpeta movida/renombrada (misma cuenta o mismo id), carpeta ausente (se marca `disk_state = MISSING`, **no se borra nada**), id de Instagram distinto, username repetido.
* **Mantiene:** contadores de posts/reels/story/highlights, fecha del último contenido, id de Instagram (solo rellena vacíos) y el índice de ficheros de las carpetas que cambiaron.
* Si hubo errores de lectura no se marca ninguna cuenta como ausente. Con `G:` desconectada no se puede sincronizar.
* **Paridad con `sc1`:** la verificación completa produce los mismos id, contadores, último contenido y filas de índice que `generatedirmap.py --complete` sobre un árbol de prueba.

### Modificado

* `db/gui_migrations.py`, `cli/main.py`, `gui/chrome/menubar.py`, `gui/catalog/panel.py`, `gui/library/fsops_actions.py`, `gui/shell/app.py`, locales, `README.md`, versión 3.8.0.
* `docs/feat-uc3-8.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 484 passed (1 omitido: prueba de Tk). Sobre una **copia** de tu base y tu `G:` real (solo lectura): 1 169 cuentas revisadas en ~0,5 s, 4 676 consultas de carpeta, 0 hallazgos, dos veces seguidas.

## v3.7.0 - feat-problem1-7: cuenta renombrada en Instagram (renombrar o fusionar)

Fecha: 2026-10-12 · Rama: `v3/integration`

Cuando una cuenta cambia de username se resuelve **desde la app, en un gesto**: carpeta en disco, base de datos, `accounts_lite` y GUI, con historial de nombres. El renombrado simple conserva **la misma fila (mismo id)**.

### Creado

* `library/account_rename.py` (`AccountRenameService`: `plan_rename`, `execute`, `undo_blocker`, `restore_after_undo`, `resolve_alias`), `library/merge.py` (fusión de carpetas sin perder ficheros: idénticos, duplicados por `media_id`, conflictos de tamaño, deshacer), `library/owner_groups.py` (grupos de cuentas con el mismo id de Instagram y su clasificación).
* Tablas `account_usernames` (historial de nombres, relleno con el nombre vigente de las 1 169 cuentas), `owner_dup_ignored`; columnas `fs_operations.payload` y `account_lifecycle.payload`; operaciones `MERGE_DIR` / `UNMERGE_DIR` en el motor de disco (con recuperación y deshacer).
* GUI: **Cambió de username…** (clic derecho y menú Catálogo) con ventana de vista previa (renombrado o fusión, qué cuenta se conserva, resumen de ficheros), **Revisar ids repetidos…** (grupos con pista y «Resolver…» / «No es renombrado»), aviso en el editor «@old ahora es @new».
* Story inbox: `MOVED_VIA_ALIAS` cuando el fichero lleva un nombre antiguo (solo si es inequívoco).
* Tests: `test_account_rename.py` (15), `test_owner_groups.py`, `test_story_inbox_alias.py`, `test_catalog_refresh_after_rename.py`.

### Modificado

* Al terminar, la GUI se refresca sin reiniciar: lista, árbol, editor y tabla del lote abierto.
* `fsops.py`, `fsops_plan.py`, `db/gui_migrations.py`, `filesystem/story_inbox.py`, `gui/stories/dialog.py`, `gui/library/fsops_history_dialog.py`, `gui/editor/panel.py`, `gui/catalog/panel.py`, `gui/chrome/menubar.py`, `gui/shell/app.py`, locales, `README.md`, versión 3.7.0.
* `docs/feat-problem1-7.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 469 passed. Prueba con una copia de tu base de datos: tus 2 grupos de id repetido restantes se clasifican (1 «renombrado probable», 1 «revisión manual») y se resolvió el probable (`dianaseyx` → `exkeysi`, conservando la carpeta activa). **No probado contra `G:` real.**

## v3.6.0 - feat-uc4-6: publicación automática desde la instancia 24/7 + importación fiel

Fecha: 2026-10-12 · Rama: `v3/integration`

La instancia `WORKER` entrega sola lo que descarga en un **paquete** atómico (carpetas + `manifest.json` con el resultado real de cada URL) y la principal lo **importa fielmente**: estados reales de las URLs y datos de renombrado, sin «Ejecutado en otra instancia».

### Creado

* `exchange/manifest.py` (formato `ig_orchestrator.batch_result` v1: `build_manifest`, `write_manifest`, `read_package`, `scan_packages`, validación de versión), `exchange/publish.py` (`publish_batches`, `unpublished_batches`, ajustes de publicación, limpieza de `.partial`), `exchange/result_import.py` (`import_package`).
* Tablas `exchange_publications` y `exchange_imports`.
* GUI: `Lote → Publicar descargas…` (`gui/exchange/publish_dialog.py`), publicación **automática** al terminar un lote o una cola (si la instancia local es `WORKER` y está activada), sección de publicación en `Ajustes → Instancias`, filas «Paquete» en **Traer descargas** con el botón **Importar paquetes**.
* Tests: `tests/exchange/test_publish_import.py` (15) y `test_publish_settings.py`.

### Modificado

* `exchange/inbox_scan.py` ya no ofrece paquetes ni `*.partial` como carpetas sueltas.
* El aviso de **Ejecutado en otra instancia** explica que descarta los resultados reales y remite a *Importar paquetes*.
* `gui/run/controller.py` (disparo de la publicación), `gui/chrome/menubar.py`, `gui/shell/app.py`, `gui/settings/instances_tab.py`, `gui/batches/dialog.py`, `db/gui_migrations.py`, locales, `README.md`, versión 3.6.0.
* `docs/feat-uc4-6.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 442 passed. Prueba con una copia de tu base de datos: publicar el lote 121 (3 cuentas con carpeta) y, en una segunda copia, importarlo (7 URLs `COMPLETED`, ficheros traídos, segunda importación sin cambios). **No probado con dos máquinas reales.**

## v3.5.2 - Corrección: cuentas «Sin ruta» fantasma y ruta antigua en el editor

Fecha: 2026-10-12 · Rama: `v3/integration`

**Causa:** el catálogo mezclaba `config/batch.json` (y las copias de `config/bkp`) con la base de datos. Una cuenta oculta de la lista (eliminada/archivada) o que ya no estaba en la base reaparecía desde el JSON como una fila «Sin ruta» y sin id. Además el editor conservaba los valores (id y carpeta) de antes de mover la cuenta.

* La base de datos es la fuente de verdad: `batch.json` solo se usa para arrancar un catálogo vacío (ya no resucita cuentas, p. ej. `vinskawy`).
* Las cuentas **eliminadas** se muestran en la **vista de árbol** dentro de su carpeta (p. ej. `Adrianna-Eves-Deleted`), en lila; en la vista de lista siguen ocultas (se ven con `Mostrar biblioteca completa`).
* Tras cualquier operación de disco, el editor vuelve a leer el id y la carpeta de la cuenta que tiene cargada; el check *Update* y el seleccionar una cuenta usan `find_entry` (también para cuentas ocultas) en lugar de dejar el valor antiguo.
* Tests: `tests/gui/test_catalog_ghost_entries.py` (reproduce el caso de `adrieves19` y `vinskawy`).

## v3.5.1 - Marcar como eliminada: destino editable

Fecha: 2026-10-12 · Rama: `v3/integration`

* Al marcar una cuenta como eliminada se abre una ventana con **De → A** y el motivo. El destino se **sugiere**: la carpeta `<Modelo>-Deleted` (o `-Delete`) hermana de la carpeta de la modelo si existe; si no, la carpeta de eliminadas (`09.DELETED`).
* Se puede **cambiar el destino** (una o varias filas): elegir otra carpeta del catálogo o **crear una carpeta nueva** desde el selector (`Nueva carpeta aquí…`); se crea y se mueve la cuenta en el mismo gesto (vista previa, historial y deshacer como siempre). Botones: *Usar carpeta de eliminadas*, *Restablecer sugerido*, casilla *sufijo _2*.
* Una cuenta que ya está en una carpeta `-Deleted`/`-Inactive` o en la de eliminadas solo cambia de estado.
* `AccountLifecycleService.suggest_destination` y `plan_mark_deleted(..., dest_overrides=)`; `FsOperationService.ensure_folder_rows` registra en el catálogo carpetas que existen en disco pero no tenían fila (el destino puede ser una carpeta creada en el Explorador).
* Tests: `tests/library/test_lifecycle_destinations.py`, `tests/gui/test_delete_destination.py`.

## v3.5.0 - feat-problem1-5: cuenta eliminada en Instagram

Fecha: 2026-10-12 · Rama: `v3/integration`

Una sola acción para marcar una cuenta como eliminada: cambia su estado a `DELETED` y mueve su carpeta a `09.DELETED`, con vista previa, deshacer y restaurar.

### Creado

* `library/account_lifecycle.py` (`AccountLifecycleService`: `plan_mark_deleted`, `execute_mark_deleted`, `plan_restore`, `execute_restore`, `restore_after_undo`, `find_unlabeled_deleted`, `label_deleted`, `suggest_deleted`).
* Estado `DELETED` (id 6), columnas `catalog_accounts.deleted_at` y `previous_rel_path`, tabla `account_lifecycle` (estado y favorito anteriores, para deshacer/restaurar).
* GUI (`gui/library/lifecycle_actions.py`): **Marcar como eliminada…**, **Marcar varias como eliminadas…** (pegar usernames), **Restaurar cuenta eliminada…**, **Sugerir eliminadas…**, **Etiquetar 09.DELETED…**; confirmación al añadir al editor una cuenta eliminada.
* Ajustes → Catálogo: carpeta de eliminadas (`library.deleted_folder_rel`) y conservar grupo (`library.deleted_keep_group`).
* Tests: `tests/library/test_account_lifecycle.py` (11).

### Modificado

* El menú «Delete» pasa a llamarse **Ocultar** (sigue siendo `DISABLED`); `DELETED` se oculta del catálogo como `ARCHIVED` (visible con `Ver → Mostrar biblioteca completa`, color lila).
* El Deshacer de `Catálogo → Operaciones de disco…` también restaura estado y favorito.
* `models/account_history.py`, `db/gui_migrations.py`, `db/v2/catalog/repository.py`, `gui/catalog/{colors,service,panel}.py`, `gui/chrome/menubar.py`, `gui/editor/panel.py`, `gui/settings/dialog.py`, `gui/library/{plan_dialog,fsops_history_dialog}.py`, locales, `README.md`, versión 3.5.0.
* `docs/feat-problem1-5.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 412 passed. Prueba de humo de la GUI con una copia de tu BD y biblioteca temporal: marcar, ocultar, restaurar, etiquetar. **No probado contra `G:` real.**

## v3.4.1 - Organizar stories sin accounts_lite

Fecha: 2026-10-12 · Rama: `v3/integration`

* `Organizar stories` ya **no depende de `accounts_lite`**: se quitó el campo de la base antigua del diálogo y la carpeta de cada cuenta se resuelve solo desde `bdapp` (`rel_path` + raíz `LIBRARY`; si una cuenta no tiene `rel_path`, su carpeta de catálogo + username).
* `save_story_inbox_settings` guarda solo la carpeta de stories (el ajuste `stories.accounts_db_path` se conserva porque lo usan la auditoría y la importación como valor por defecto).
* `filesystem/story_inbox.py` conserva el parámetro `accounts_db` solo por compatibilidad (respaldo opcional, no usado por la GUI).
* Tests: resolución desde `bdapp` con y sin `rel_path`.

## v3.4.0 - feat-uc2-4: operaciones de disco desde el catálogo

Fecha: 2026-10-12 · Rama: `v3/integration`

Primera vez que la app **modifica la biblioteca**: crear, renombrar y mover carpetas y cuentas desde el árbol del catálogo, con vista previa, diario y deshacer. Disco y `bdapp` cambian juntos.

### Creado

* `library/fsops.py` (`FsOperationService`: `plan_mkdir`, `plan_rename_folder`, `plan_move_folder`, `plan_move_account`, `execute`, `recover`, `undo`, `history`), `library/fsops_plan.py` (`Plan`, `Step`, `Conflict`, `validate_name`), `library/compat_lite.py` (espejo `bdapp → accounts_lite`).
* Tabla `fs_operations` (diario: `PLANNED → DISK_DONE → COMMITTED`, `undo_of`).
* GUI: menú contextual del árbol (carpetas: **Nueva carpeta…**, **Renombrar carpeta…**, **Mover a…**; cuentas: **Mover a otra carpeta…**), `gui/library/{plan_dialog,folder_picker,fsops_history_dialog,fsops_actions}.py`, `Catálogo → Operaciones de disco…` (historial + Deshacer).
* El árbol muestra las carpetas vacías (p. ej. recién creadas).
* Recuperación automática al abrir la app (completa o descarta operaciones interrumpidas) y reconciliación del espejo de lite.
* Tests: `tests/library/test_fsops.py` (18), `tests/gui/test_catalog_actions.py`.

### Reglas de seguridad

Nunca sobrescribe (conflicto `DEST_EXISTS`); nunca sale de la raíz `LIBRARY`; no mueve una carpeta dentro de sí misma; bloquea cuentas de un lote en ejecución (`PROCESSING`); desactivado si `G:` no está disponible; una sola operación a la vez; renombrado solo de mayúsculas en dos pasos (NTFS).

### Modificado

* `db/gui_migrations.py`, `gui/catalog/{panel,service,tree}.py`, `gui/chrome/menubar.py`, `gui/shell/app.py`, locales, `README.md`, versión 3.4.0.
* `docs/feat-uc2-4.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 400 passed. Prueba de humo de la GUI con una copia de tu BD y una biblioteca temporal: nueva carpeta, mover cuenta, historial. **No se probó contra `G:` real.**

## v3.3.1 - Informe de simulación claro (feat 3)

* El informe empieza con un **veredicto** (Correcto / Se puede importar con avisos / No importar) y explica que la importación es segura.
* Secciones **SOBRAN** (carpetas de `accounts_complete` que ya no están en lite) y **FALTAN** (en lite pero no en complete), con listas; incidencias con ejemplos.
* Las carpetas que solo están en `accounts_complete` (y no en lite) **ya no se importan**: lite manda sobre qué carpetas existen. Evita crear cuentas fantasma.
* Botón **Guardar informe completo…** y opción CLI `--report`.
* Tutorial: `--update` no borra carpetas obsoletas; `--complete` limpia.

## v3.3.0 - feat-uc1-3: catálogo completo en bdapp + índice de ficheros

Fecha: 2026-10-11 · Rama: `v3/integration`

`bdapp` pasa a conocer toda la biblioteca (rutas, contadores, fecha del último contenido) y el índice de ficheros que usará el renombrado. **Estrategia A (aditiva):** no se reconstruye el catálogo; se amplía. No escribe en `accounts_*` ni en disco.

### Creado

* `library/import_bdsc1.py` (`import_from_bdsc1`, informe, simulación, idempotente), `library/paths.py`, `library/filenames.py`, `library/import_cli.py`.
* Comando `python -m ig_orchestrator import-bdsc1 [--lite] [--complete] [--root] [--dry-run] [--no-media]`.
* `gui/library/import_dialog.py` - `Catálogo → Importar desde bdsc1…` (Simular / Importar, copia de seguridad automática).
* Esquema (aditivo en `_patch_gui_schema`): `catalog_accounts` (`rel_path`, contadores, `last_media_at`, `last_scan_at`, `disk_state`, `legacy_lite_id`), `catalog_folders` (`rel_path`, `kind`), tablas `media_index` (solo `account_id`, `kind`, `media_id`, `taken_at`, `owner_id`, `ext`, `suffix`), `media_index_state`, `library_import_issues`, raíz `LIBRARY` en `path_roots`, estado `ARCHIVED`.
* Copia de seguridad automática antes de la migración (`data/bkp/orchestrator_gui_pre_v3_*.sqlite`) y antes de cada importación real (`..._pre_import_*`).
* Tests: `tests/library/test_import_bdsc1.py` y ampliaciones en `tests/db/test_gui_database.py` y `tests/filesystem/test_story_inbox.py`.

### Modificado

* Story inbox resuelve la carpeta desde `bdapp` (con respaldo a `accounts_dir`); la base antigua pasa a ser opcional.
* Las cuentas `ARCHIVED` no salen en el catálogo/editor por defecto (`Ver → Mostrar biblioteca completa`); al usarlas en el editor o en un lote pasan a `ENABLED`.
* `models/account_history.py`, `db/v2/catalog/repository.py`, `db/account_history_repository.py`, `gui/catalog/{service,colors,panel}.py`, `gui/chrome/menubar.py`, `gui/shell/app.py`, `input/gui_batch_creation.py`, `gui/stories/dialog.py`, locales, `README.md`, versión 3.3.0.
* `docs/feat-uc1-3.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 374 passed. Importación real sobre una **copia** de tus datos (14 s): 924 cuentas `ARCHIVED` creadas, 331 actualizadas, 107 carpetas, 908 560 ficheros indexados; las 334 cuentas previas conservan estado; segunda ejecución: 0 cambios. La BD pasa de 8,8 a 64 MB.

## v3.2.2 - Traer descargas: «Comparar con lote» dentro de la tabla

Fecha: 2026-10-11 · Rama: `v3/integration`

* `gui/exchange/pull_dialog.py`: al elegir un lote la tabla añade la columna **En el lote** y muestra como filas en gris las cuentas del lote que aún no están en la carpeta compartida (antes solo había un texto con listas largas bajo la tabla, que ahora es un resumen con contadores).
* `docs/tutorial-v3.md`: explica qué ve y qué no ve la app (cada instancia tiene su BD; solo se mira la carpeta compartida) y el significado de cada estado.

## v3.2.1 - Tutorial v3 y etiquetas de Instancias

Fecha: 2026-10-11 · Rama: `v3/integration`

* Creado `docs/tutorial-v3.md`: guía feat a feat (feats 1 y 2) con campos, botones, ejemplos con rutas reales y pruebas. Regla nueva en el plan: cada feat añade su sección.
* Formulario de **Ajustes → Instancias**: etiquetas más claras (ruta «desde ESTE PC» vs «en ELLA misma») y texto de ayuda.
* `CLAUDE.md` referencia el tutorial.

## v3.2.0 - feat-uc4-2: Registro de instancias y «Traer descargas…»

Fecha: 2026-10-11 · Rama: `v3/integration`

Elimina el paso manual de copiar de la carpeta compartida de otra instancia a la carpeta de trabajo. No toca la biblioteca ni `accounts_lite`.

### Creado

* Tabla `instances` (se crea con `CREATE TABLE IF NOT EXISTS` en `_patch_gui_schema`) y `db/instances_repository.py` (`Instance`, `InstanceRepository`; solo una instancia local).
* `src/ig_orchestrator/exchange/` - `inbox_scan.py` (carpetas, tamaño, estabilidad por `mtime`, prefijo extendido de Windows), `pull.py` (plan + copia verificada con `.part`, política `merge_skip_identical`/`abort`, cancelación, espacio libre), `compare.py` (comparar con lote, sondeo de ruta con timeout), `MODULE.md`.
* `gui/settings/instances_tab.py` - pestaña **Ajustes → Instancias** (alta/edición/baja y «Probar»; guarda al instante).
* `gui/exchange/pull_dialog.py` - **Lote → Traer descargas…** (también botón en el diálogo de lotes): origen por instancia o ruta libre, estados Lista/En uso/Ya existe/Vacía, comparar con lote, progreso, cancelar, oferta de «Ejecutado en otra instancia».
* Aviso al pulsar **Renombrar** si la carpeta de trabajo está vacía y hay carpetas estables en el intercambio de una instancia.
* Tests: `tests/exchange/test_pull.py`, `tests/gui/test_pull_dialog.py`.

### Modificado

* `db/gui_migrations.py`, `db/__init__.py`, `gui/shell/app.py`, `gui/chrome/menubar.py`, `gui/batches/dialog.py`, `gui/run/rename.py`, `gui/settings/dialog.py`, `gui/shared/locales/{es,en}.json`, `README.md`, versión 3.2.0.
* `docs/feat-uc4-2.md` movido a `tasks/done/v3/`.

### Pruebas ejecutadas

* `python -m pytest`: 361 passed. Prueba de humo real de la GUI con una copia de la BD: escaneo automático, «Traer todas las listas» (movió el fichero y limpió la carpeta de origen), pestaña de ajustes.

## v3.1.0 - feat-uc3-1: Auditoría de biblioteca (solo lectura)

Fecha: 2026-10-11 · Rama: `v3/integration`

Informe de discrepancias entre `bdapp`, `accounts_lite`, `accounts_complete` y el disco. No escribe en ninguna BD ni en disco.

### Creado

* `src/ig_orchestrator/library/` - `audit.py` (`run_audit`), `audit_report.py` (`Finding`, `AuditReport`, Markdown/CSV), `audit_cli.py`, `MODULE.md`.
* `src/ig_orchestrator/gui/library/audit_dialog.py` - Diálogo `Catálogo > Auditar biblioteca…` (hilo aparte, filtro por código, exportar MD/CSV, abrir en Explorer).
* Comando CLI `python -m ig_orchestrator audit-library [--lite] [--complete] [--md] [--csv] [--no-disk]`.
* Tests: `tests/library/test_audit.py`, `tests/gui/test_audit_dialog.py`.

### Modificado

* `cli/main.py`, `gui/chrome/menubar.py`, `gui/shell/app.py`, `gui/locales/{es,en}.json`, `README.md`, versión a 3.1.0.
* `docs/feat-uc3-1.md` movido a `tasks/done/v3/` (con los resultados medidos).

### Correcciones (v3.1.1)

* Textos de la auditoría movidos a `gui/shared/locales/{es,en}.json` (los de `gui/locales` no se cargan): el menú y el diálogo mostraban las claves.
* Rutas del diálogo siempre con separadores de Windows (`native_path_text`), también las leídas del ajuste y las del selector de archivos.

### Pruebas ejecutadas

* `python -m pytest`: 344 passed (342 antes de la corrección). Auditoría real (0,4 s): PATH_MISSING 15, OWNER_DUP 69, OWNER_MISMATCH 4, FOLDER_MISMATCH 1, ONLY_IN_APP 5, ONLY_IN_LITE 902, COMPLETE_STALE 394, LAST_MODIFIED_MIXED 1; `mtime` de las BD sin cambios.

## v3 (planificación) - Análisis y plan de mejoras

Fecha: 2026-10-11 · Rama: `v3/integration`

Solo documentación: no cambia código ni la versión de la app (sigue en v2.2.0).

### Creado

* `docs/v3-status.md` - Estado actual de la app, `sc1` (GenerateDirMap), `sc2` (ManualRenameFiles), las bases de datos (`bdapp`, `accounts_lite`, `accounts_complete`) y los procesos manuales, con mediciones reales.
* `docs/feat-uc3-1.md`, `feat-uc4-2.md`, `feat-uc1-3.md`, `feat-uc2-4.md`, `feat-problem1-5.md`, `feat-uc4-6.md`, `feat-problem1-7.md`, `feat-uc3-8.md`, `feat-uc1-9.md`, `feat-uc5-10.md`, `feat-uc6-11.md`, `feat-uc2-12.md` - Una propuesta independiente por mejora (sufijo = dificultad 1–12).
* `docs/plan-v3-features.md` - Orden de ejecución, dependencias, puntos de decisión y retirada gradual de los scripts.

### Modificado

* `CLAUDE.md` - Referencias a los nuevos documentos.
* Revisión 2026-10-11 (decisiones del usuario): `accounts_complete` como fuente principal e índice de renombrado importado en el feat 3, BD única reestructurable, registro de instancias (feat 2), estado final explícito. Afecta a `v3-status.md`, `plan-v3-features.md` y `feat-uc1-3/uc4-2/uc4-6/uc3-8/uc1-9/uc5-10`.

### Pruebas ejecutadas

* No aplica (sin cambios de código). Los datos citados se midieron en solo lectura sobre `orchestrator_gui.sqlite`, `accounts_lite.sqlite` y `accounts_complete.sqlite`.

## v2.2.0 - GUI UX Improvements (En desarrollo)

Fecha: 2026-10-06

### Estado
✅ **100% COMPLETADO** - Listo para testing manual y merge.

### Cambios implementados:

### Creado

* `generate_stories_icon.py` - Script para generar icono stories.png (24x24, círculo con marca)
* `src/ig_orchestrator/gui/shared/static/icons/stories.png` - Icono para botón Stories en toolbar

### Modificado

* `src/ig_orchestrator/gui/chrome/menubar.py`:
  - Eliminada entrada duplicada "Organize stories…"

* `src/ig_orchestrator/gui/editor/panel.py`:
  - Agregados botones paste/clear para Owner Id, First Post Date, Path
  - Implementados handlers: _paste_owner_id, _clear_owner_id, _paste_start_init_date, _clear_start_init_date, _paste_destination_path, _clear_destination_path
  - Aplicado bind_edit_context_menu a los 3 campos nuevos
  - Ajustados anchos: Owner Id (18), First Post Date (14), Path (40)
  - Corregido layout: url_actions frame usa rowspan=2 para posición constante

* `src/ig_orchestrator/gui/batch_accounts/panel.py`:
  - Agregado botón paste en filtro de búsqueda de cuentas
  - Limitado ancho del filtro a 30 caracteres
  - Implementado handler _paste_batch_filter

* `src/ig_orchestrator/gui/shared/log_window.py`:
  - Agregados filtros por nivel (Warning, Error)
  - Implementada colorización de logs (warning:#b58900, error:red)
  - Agregados botones en barra inferior: Clear, Warning, Error, Close
  - Aplicado bind_escape_close para cerrar con Escape
  - Implementado renderizado dinámico del buffer según filtro

* `src/ig_orchestrator/gui/shared/helpers.py`:
  - Agregada función `bind_escape_close(window, on_close=None)` para cerrar modales con Esc
  - Agregada función `classify_log_level(line)` para detectar WARNING/ERROR en logs

* `src/ig_orchestrator/gui/shared/icons.py`:
  - Registrado icono "stories" en _ICON_FILES

* `src/ig_orchestrator/gui/shell/app.py`:
  - Agregado botón stories_button en toolbar (columna 8, después de rename_manual)
  - Ajustadas columnas de batch_name_entry y date (8→9→10→11)

* `src/ig_orchestrator/gui/editor/panel.py` (Bugs arreglados):
  - **Bug #1**: Botón "Save / update batch" no se habilitaba con 2+ cuentas. Agregada llamada a `_update_batch_context()` en `_upsert_account()` para recalcular estado de botones tras agregar cuentas.
  - **Bug #2**: Al marcar "Update", los campos "Paste first post date" y "Clear date" se ocultaban pero dejaban espacio vacío. Ahora el campo Path se reposiciona de row 2 a row 1 cuando está en modo Update, eliminando el espacio hueco y manteniendo el layout compacto.
  - Actualizada columnconfigure para weight=1 en columna 11

* `src/ig_orchestrator/gui/batches/dialog.py`:
  - Importado bind_escape_close
  - Aplicado bind_escape_close a diálogo de lotes

* `src/ig_orchestrator/gui/settings/dialog.py`:
  - Importado bind_escape_close
  - Aplicado bind_escape_close a diálogo de configuración con callback _on_cancel

* `src/ig_orchestrator/gui/shared/locales/es.json`:
  - Nuevas claves i18n: label.owner_id, label.first_post_date, label.path, label.catalog_frame
  - Nuevas claves tooltips: tooltip.paste_owner_id, tooltip.clear_owner_id, tooltip.paste_first_post_date, tooltip.clear_first_post_date, tooltip.paste_path, tooltip.clear_path, tooltip.paste_batch_filter
  - Nuevas claves log: log.warning, log.error, log.close

* `src/ig_orchestrator/gui/shared/locales/en.json`:
  - Nuevas claves i18n equivalentes en inglés

### Tests ejecutados

* `tests/gui/test_v2_2_helpers.py` - 11 tests para:
  - `classify_log_level()`: WARNING, ERROR, CRITICAL, NORMAL, INFO
  - `compute_toolbar_state()`: history mode, running batch, account count, rename ready, stories always enabled
  - Todos los tests pasando ✅

* Suite completa: `python -m pytest tests/gui/ -q`
  - 147 tests passing
  - Incluye test update para el nuevo layout (url_actions rowspan=2)

### Notas de implementación

* Función `compute_toolbar_state()` en `shared/helpers.py` es pura y fully testable
* Integración en `chrome/toolbar.py` y `chrome/statusbar.py` lista para implementar cuando se requiera
* Log filtering y colores completamente funcionales en `shared/log_window.py`
* Todos los modales cierran con Escape
* Editor con paste/clear en los 3 nuevos campos
* Toolbar con botón Stories siempre habilitado

### Próximos pasos

- Manual testing: `python -m ig_orchestrator gui`
- Merge PR a master
- Tag v2.2.0

- Rama: v2/gui-ux-v2.2
- Los cambios del editor y log_window mejoran la UX sin cambiar APIs
- El icono stories.png fue generado con Python + zlib (PNG manual)

## v2.1.6 - Stories Inbox Modal Restaurado

Fecha: 2026-10-04

### Creado

* `src/ig_orchestrator/filesystem/story_inbox.py` - Lógica de movimiento de archivos de stories:
  - Función `username_from_story_filename()` - Extrae username del nombre de archivo
  - Función `list_inbox_media()` - Lista archivos de media en la carpeta inbox
  - Función `organize_story_inbox()` - Mueve archivos identificando por username
  - Función `summarize_results()` - Cuenta archivos movidos y errores
  - Clases: `StoryInboxStatus`, `StoryInboxResult`, `StoryInboxError`

* `src/ig_orchestrator/gui/stories/` - Módulo GUI para Stories Inbox:
  - `dialog.py` - `StoriesInboxMixin` con métodos para abrir modal y ejecutar
  - `settings.py` - Funciones para cargar/guardar rutas en `app_settings`
  - `__init__.py` - Exporta mixin
  - `MODULE.md` - Documentación del módulo

* Tests:
  - `tests/gui/test_stories_dialog.py` - Tests de configuración
  - `tests/filesystem/test_story_inbox.py` - Tests de movimiento de archivos

### Modificado

* `src/ig_orchestrator/gui/chrome/menubar.py`:
  - Agregado comando `menu.batch.pause` (pausar/reanudar en menú)
  - Agregado comando `menu.batch.stories` (organizar stories en menú)
  - Separator antes y después de "Organizar Stories"

* `src/ig_orchestrator/gui/shell/app.py`:
  - Agregada importación de `StoriesInboxMixin`
  - Agregado `StoriesInboxMixin` en herencia de clase `InstagramOrchestratorApp`

* `src/ig_orchestrator/gui/shared/locales/es.json`:
  - Nuevas claves: `menu.batch.pause`, `menu.batch.stories`
  - Nuevas claves stories.* (15 strings) para UI y mensajes

* `src/ig_orchestrator/gui/shared/locales/en.json`:
  - Nuevas claves: `menu.batch.pause`, `menu.batch.stories`
  - Nuevas claves stories.* (15 strings) para UI y mensajes

### Pruebas ejecutadas

* `python -m py_compile` en story_inbox.py, dialog.py, settings.py (todo OK)
* `pytest tests/filesystem/test_story_inbox.py` - Todos los tests pasan:
  - username_from_story_filename()
  - organize_story_inbox() moves files correctly
  - organize_story_inbox() reports missing username and path
  - organize_story_inbox() does not overwrite
  - organize_story_inbox() requires paths
  - organize_story_inbox() requires accounts_dir table
* `pytest tests/gui/test_stories_dialog.py` - Test de settings pass

### Comportamiento

1. Menú **Batch** ahora tiene:
   - Execute
   - Stop
   - Pause (toggle pause/resume)
   - ---
   - Organize Stories (nuevo)
   - ---
   - Rename
   - Manual Rename

2. Click en "Organize Stories" abre modal con:
   - Campo para ruta inbox (con Browse)
   - Campo para ruta BD de cuentas (con Browse)
   - Área de log para resultados
   - Botones: Save (guarda rutas), Run (ejecuta), Close

3. Flujo de uso:
   - Usuario configura rutas (se guardan en app_settings)
   - Click Run ejecuta `organize_story_inbox()`
   - Cada archivo se mueve de `inbox_path` a `{account_path}/story/`
   - Username se extrae del nombre de archivo (formato: `{username}-...`)
   - Log muestra resultado: MOVED, USERNAME_NOT_FOUND, DESTINATION_EXISTS, etc.

## v2.1.5 - Nombre de Batch por Defecto con Timestamp

Fecha: 2026-10-03

### Creado

* Nueva función `_generate_default_batch_name()` en helpers.py:
  - Genera nombre de batch con timestamp actual
  - Formato: `descargas_YYYY_MM_DD_HH_MM_SS`
  - Garantiza nombre único para cada invocación (precisión a segundo)

### Modificado

* `src/ig_orchestrator/gui/shared/helpers.py`:
  - Agregada función `_generate_default_batch_name()` 
  - Exportada en `__all__`

* `src/ig_orchestrator/gui/shell/app.py`:
  - Línea 243-245: Inicialización de `batch_name_var` cambió de usar último batch ejecutado a generar nombre por defecto con timestamp
  - Agregada importación de `_generate_default_batch_name`

* `src/ig_orchestrator/gui/run/controller.py`:
  - Método `_start_new_batch()` línea 138: cambió a usar `_generate_default_batch_name()` en lugar de `_suggest_batch_name()`
  - Agregada importación de `_generate_default_batch_name`

### Pruebas ejecutadas

* `python -m py_compile` en helpers.py, app.py, controller.py (todo OK)
* Test unitario de `_generate_default_batch_name()`:
  - Verifica formato correcto: descargas_YYYY_MM_DD_HH_MM_SS
  - Verifica nombres diferentes en invocaciones separadas (1 segundo)
  - Todos los tests pasaron

### Comportamiento

1. Al iniciar la app: nombre es `descargas_YYYY_MM_DD_HH_MM_SS` (timestamp actual)
2. Cada vez que se abre la app: se genera nuevo nombre con timestamp diferente
3. Click en "New Batch": genera nuevo nombre con timestamp actual
4. Usuario puede editar nombre manualmente si lo desea
5. Nombre se persiste en SQLite cuando se ejecuta batch

## v2.1.4 - Botón Pause/Resume en Ventana Principal

Fecha: 2026-10-03

### Creado

* Botón Pause/Resume en toolbar junto a botones Run/Stop
  - Ícono pause.png (dos barras verticales) para estado pausa
  - Usa play icon para estado resume
  - Botón deshabilitado cuando no hay batch en ejecución
  - Botón habilitado solo cuando hay un batch ejecutándose
  - Muestra "Pause" (ícono ⏸) cuando batch está ejecutándose
  - Muestra "Resume" (ícono ▶) cuando batch está pausado
  - Tooltip dinámico que cambia con el estado

* Funcionalidad de toggle pause/resume:
  - Click en botón pausa el batch actual sin cerrarlo
  - Click nuevamente reanuda desde donde se pausó
  - Estado sincronizado entre ventana principal y "Batches / runs"
  - Logs muestran "Cola pausada" / "Cola reanudada"

### Modificado

* `src/ig_orchestrator/gui/shared/icons.py`:
  - Agregado "pause": "pause.png" a `_ICON_FILES`

* `src/ig_orchestrator/gui/shell/app.py`:
  - `_build_widgets()`: agregado botón `pause_button` entre execute y cancel
  - Actualización de grid positions para reflejar nueva columna
  - `_restore_open_queue()`: sincroniza estado pause button si queue está pausada

* `src/ig_orchestrator/gui/run/controller.py`:
  - `_toggle_pause_resume()`: método que detecta estado actual y alterna entre pause/resume
  - `_pause_batch()`: pausa la cola actual y actualiza UI
  - `_resume_batch()`: reanuda la cola pausada y actualiza UI

* `src/ig_orchestrator/gui/chrome/statusbar.py`:
  - `_set_process_running()`: habilita/deshabilita pause button según estado de ejecución

* `src/ig_orchestrator/gui/static/icons/pause.png`: nuevo ícono pause (32x32)

* `src/ig_orchestrator/gui/shared/locales/es.json` y `en.json`:
  - Nuevas claves: `tooltip.pause`, `tooltip.resume`, `warning`, `error`

### Pruebas ejecutadas

* `python -m py_compile` en archivos modificados (todo OK)
* Verificación manual (GUI):
  - Crear batch con 10+ URLs
  - Click en "Run" → comienza ejecución
  - Esperar a que descargue 2-3 URLs
  - Click en botón Pause → verifica que tooltip cambió a "Resume"
  - Verifica que logs muestran "Cola pausada"
  - Click en botón Resume → verifica que tooltip cambió a "Pause"
  - Verifica que logs muestran "Cola reanudada"
  - Verificar que descargas continúan desde donde se pausaron

## v2.1.3 - Copiar URLs al Portapapeles en Panel de Errores

Fecha: 2026-10-03

### Creado

* Funcionalidad de copia de URLs en modal de "URLs completadas/reintentos/fallidas":
  - Botón "Copiar" en frame de acciones para copiar URL seleccionada
  - Botón "Copiar todas" para copiar todas las URLs (una por línea)
  - Context menu (click derecho) en URLs con opciones "Copiar", "Abrir en Chrome" y "Copiar todas"
  - Atajo Ctrl+C para copiar URL seleccionada
  - Notificación visual temporal "¡Copiado!" en verde al copiar

### Modificado

* `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`:
  - `_open_account_problem_urls()`: agregadas funciones `copy_to_clipboard()`, `_show_copied_notification()`,
    `copy_selected_url()`, `copy_all_urls()`, `show_context_menu()`, `on_ctrl_c()`
  - Frame de acciones: nuevos botones "Copiar" y "Copiar todas"
  - Tree binding: `<Button-3>` para context menu, `<Control-c>` para Ctrl+C
* `src/ig_orchestrator/gui/shared/locales/es.json` y `en.json`: nuevas claves
  `problem_urls.copy`, `problem_urls.open_chrome`, `problem_urls.copy_all`,
  `problem_urls.copied`, `problem_urls.copy_failed`

### Pruebas ejecutadas

* `python -m pytest -q` (suite completa)
* Verificación manual en GUI: 
  - Crear batch con URLs que generen errores
  - Abrir modal de URLs fallidas/reintentos
  - Click en botón "Copiar" → verifica portapapeles
  - Click derecho en URL → verifica context menu
  - Ctrl+C en URL seleccionada → verifica copia
  - Botón "Copiar todas" → verifica copia de todas

## v2.1.2 - Settings Modal con Pestañas

Fecha: 2026-10-03

### Creado

* `SettingsDialogWithTabs` clase para refactorizar modal de settings con interfaz por tabs.
* 5 pestañas: General (idioma), Interfaz (posición ventana), Procesamiento (stories first, limpiar ficheros), 
  Catálogo (colores) y Notificaciones (avisos Telegram, test, errores).
* Botones "Guardar" y "Cancelar" en lugar de guardado automático.
* Nuevas claves de i18n: `settings.save`, `settings.cancel`, `settings.tabs.*`.

### Modificado

* `src/ig_orchestrator/gui/settings/dialog.py`: refactorización completa de `_open_settings()` en
  `SettingsDialogWithTabs`, mixin `SettingsDialogMixin` ahora usa la nueva clase.
* `src/ig_orchestrator/gui/shared/locales/es.json` y `en.json`: nuevas claves de traducción para
  botones y nombres de tabs.
* Comportamiento: cambios se aplican solo al presionar "Guardar"; "Cancelar" descarta cambios.
* Idioma: al cambiar, la app se reinicia automáticamente (comportamiento previo conservado).

### Pruebas ejecutadas

* `python -m pytest -q tests/gui/` (suite de GUI)
* `python -m pytest -q` (suite completa)
* Verificación manual en GUI con `python -m ig_orchestrator gui`

## v2.1.1 - Posicionamiento Configurable de Ventanas

Fecha: 2026-10-03

### Creado

* Función `center_modal_on_parent()` en `gui/shared/helpers.py` para centrar modales en pantalla o ventana padre
* Configuración de posición de ventana principal: izquierda, centro, derecha

### Modificado

* `src/ig_orchestrator/gui/shared/helpers.py`:
  - Modificada `_half_screen_geometry()` para aceptar parámetro `position`
  - Agregada función `center_modal_on_parent()` para centrar diálogos modales
  - Cálculo de geometría por posición: left (x=0), center (x=screen_width//2), right (x=screen_width-width)

* `src/ig_orchestrator/gui/shell/app.py`:
  - Lee posición de ventana desde `app_settings` (SQLite) al iniciar
  - Pasa posición a `_half_screen_geometry()`

* `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`:
  - Agregada llamada a `center_modal_on_parent()` antes de mostrar modal de URLs problemáticas

* `src/ig_orchestrator/gui/batches/dialog.py`:
  - Agregada llamada a `center_modal_on_parent()` antes de mostrar modal de lotes

* `src/ig_orchestrator/gui/shared/locales/{en,es}.json`:
  - Nuevas claves i18n:
    - `settings.window_position` — Título de configuración
    - `settings.window_position_left` — Opción izquierda
    - `settings.window_position_center` — Opción centro
    - `settings.window_position_right` — Opción derecha
    - `settings.save_window_position` — Botón guardar

* `src/ig_orchestrator/gui/settings/dialog.py`:
  - Agregado control de selección de posición de ventana en pestaña "Interface"

### Pruebas ejecutadas

* `python -m pytest -q` (suite completa)
* `python -m compileall -q src tests`

## v2.1.0 - GUI v2.1 Editor Flags, Priority, Catalog Paste, Rename Tones y Stories Inbox

Fecha: 2026-09-13

Rama: `v2/gui-ux-stories`. Plan: `tasks/done/Tarea_v2_1_GUI_ux.md`.

### Creado

* `tasks/done/Tarea_v2_1_GUI_ux.md`
* `src/ig_orchestrator/gui/draft/priority.py`
* `src/ig_orchestrator/filesystem/story_inbox.py`
* `src/ig_orchestrator/gui/stories/` (`dialog.py`, `settings.py`, `MODULE.md`)
* `tests/gui/test_priority.py`, `tests/gui/test_stories_dialog.py`,
  `tests/filesystem/test_story_inbox.py`

### Modificado

* Editor: Stories / New account / Update se resetean cuando cambia la
  identidad del username (normalizado: strip, quitar `@`, casefold).
  Catálogo, pegar Username, combobox y limpiar Username disparan el
  reset. Cargar una fila del lote hidrata los checks de esa cuenta.
* `normalize_username` público en `gui/draft/service.py`.
* Editor: check **Priority** al lado de Update. Rank 1 exclusivo: la
  cuenta queda primera en el lote y cualquier otra con el mismo rank
  pierde la prioridad. `AccountDraft.priority` y columna
  `batch_accounts.priority` (default 0) dejan sitio a ranks 2, 3…
  Columna **Prio** en la tabla. El sort legado (solo-stories, menos
  URLs) se aplica solo a las cuentas sin rank.
* Catálogo: botón pegar (icono portapapeles) a la izquierda del ❌.
  Pegar (botón, menú, Ctrl+V) selecciona el username si existe y lo
  escribe en el editor.
* Barra de estado: `tk.Button` con colores de rename — azul mientras
  corre, verde éxito, amarillo incompleto (leftovers), rojo error.
* Botón **Stories** (toolbar, a la derecha de Renombrar manual) y menú
  `Lote → Organizar stories…`: modal con Ruta Stories y Ruta BD
  (recordadas en `app_settings`). Mueve media `{username}-…` a
  `{accounts_dir.path}\story`. Errores por fichero: username ausente,
  no está en la BD, path vacío, carpeta inexistente, destino ocupado.

### Pruebas ejecutadas

* `python -m pytest -q tests/gui/test_editor.py tests/gui/test_catalog.py`
* `python -m pytest -q tests/gui/test_priority.py tests/gui/test_batch_accounts.py`
* `python -m pytest -q tests/gui/test_catalog.py tests/gui/test_rename.py`
* `python -m pytest -q tests/filesystem/test_story_inbox.py tests/gui/test_stories_dialog.py`
* `python -m pytest -q` → 321 passed

## v2.0.0 - GUI, sqlite v2 y aviso Telegram

Fecha: 2026-09-11

### Creado

* `docs/modularizacion_v2.md` y `tasks/Tarea_v2_modularize.md`.
* Paquetes GUI: `gui/shell`, `chrome`, `catalog`, `editor`,
  `batch_accounts`, `run`, `batches`, `queue`, `settings`, `draft`,
  `shared` (cada uno con `MODULE.md`).
* Persistencia v2 partida: `db/v2/adapters/`, `db/v2/catalog/`,
  `db/v1/schema.sql`, `db/v2/schema.sql`.
* Tests agrupados en `tests/gui`, `db`, `orchestration`, `telegram`,
  `input`, `filesystem`, `reports`.
* `src/ig_orchestrator/cli/main.py` (entry CLI; `main.py` es shim).
* `src/ig_orchestrator/orchestration/processing_policy.py` (alcance
  stories/resto, orden de barridas, setting `processing.stories_first`).
* `tasks/Tarea_v2_stories_first.md`.
* `tests/test_processing_policy.py`.
* `src/ig_orchestrator/db/schema_v2.sql` con diccionarios de estados/tipos,
  `bot_errors`, `path_roots`, catálogo, lotes, URLs y ficheros relativos.
* `src/ig_orchestrator/db/gui_migrations.py` (`user_version = 100`).
* `src/ig_orchestrator/db/catalog_importer.py` (solo catálogo, ids conservados).
* `src/ig_orchestrator/db/gui_catalog_repository.py`, `gui_adapters.py`,
  `lookups.py`, `schema_mode.py`, `compat_views_v2.sql`.
* `src/ig_orchestrator/input/gui_batch_creation.py` (inserts en una transacción).
* `tests/test_gui_database.py`, `tests/test_catalog_importer.py`,
  `tests/test_gui_repositories.py`, `tests/test_gui_theme.py`,
  `tests/test_log_window.py`.
* `tasks/Tarea_v2_D1.md` … `Tarea_v2_D6.md`.
* `tasks/Tarea_v2_0_0_release.md` (PR a `master` + tag `v2.0.0`, pendiente
  de validación).
* `tasks/Tarea_v2_GUI_batch_ux.md`.
* `tasks/Tarea_v2_GUI_editor_clipboard.md`.
* `src/ig_orchestrator/gui/text_edit.py`.
* `src/ig_orchestrator/gui/static/icons/clipboard_black.png`.
* `tests/test_text_edit.py`.
* Copia local `data/old/orchestrator.v1.31.0.sqlite` (no se commitea).

### Modificado

* Modularización sin cambio de comportamiento: `gui/app.py` (~3900 líneas)
  pasa a mixins por panel; servicios GUI y `gui_adapters.py` se trocean;
  rutas viejas quedan como shims de reexport.
* Pegar/Agregar no fallaba por `NameError` en el mixin del editor
  (`batch_username_matches_filter` no se importaba). El mixin de
  renombrado importa `MANUAL_RENAME_SCRIPT` y `NewAccountRenameParameters`.
* Procesamiento de lote en dos barridas cuando `processing.stories_first`
  está activo (default): primero todos los jobs `STORY` del lote (cuentas
  solo-stories y después mixtas), cuentas mixtas → `INCOMPLETE`, segunda
  barrida para reels/posts/highlights. Un check en Configuración restaura
  el modo legado (cuenta entera y siguiente).
* Estado de cuenta `INCOMPLETE` (lookup GUI id 6) y reanudable.
* `AccountOrchestrator.process_account(..., scope=)` limita jobs y reintentos.
* Dentro de una cuenta, cualquier URL `STORY` (generada o de entrada) va
  antes que el resto.
* Ventana de log: cerrar la oculta (`withdraw`) en vez de destruir el
  `Text`; `append` ignora widgets ya destruidos. Evita
  `TclError: invalid command name ".!toplevel...!text"` al pulsar
  Renombrar después de cerrar el log.
* Tema GUI: `option_add("*Font")` usa `{Segoe UI} 10`. Sin llaves Tk
  interpretaba `UI` como tamaño y `tk.Menu` fallaba al abrir `ejecutar_gui.bat`.
* `connect()` usa WAL + `synchronous=NORMAL`.
* Setting opcional `SQLITE_GUI_DB_PATH` (default `data\orchestrator_gui.sqlite`).
* Repositorios v1 despachan a adaptadores v2 si `user_version >= 100`.
* `create_batch` / `save_batch_draft` en esquema GUI usan `executemany`.
* La GUI arranca contra `orchestrator_gui.sqlite`, importa el catálogo v1
  en solo lectura y lanza `run_continue` con `SQLITE_DB_PATH` apuntando al
  fichero GUI. El diálogo Lotes no se rediseña (vistas de compatibilidad).
* GUI: menú, i18n es/en, tema claro, toolbar de iconos, Start date de solo
  lectura, sin Dry-run, editor compacto, barra de estado + log en ventana,
  Renombrar/Detener en la toolbar. Configuración: idioma (reinicia) y vaciar
  ficheros descargados. `finish_batch` limpia `downloaded_files` si retention
  es `on_complete`.
* Catálogo lista/árbol (`G:\4K Stogram\…` + username hoja). Colores
  configurables con paleta. Orden A↔Z visual en cuentas del lote y URLs.
* Aviso Telegram a `me` u otro chat al terminar un lote y si un error del
  bot está marcado; plantilla y destino en Configuración.
* `.env.example` y `Agents.md` documentan el fichero GUI y el rollback a
  `v1.31.0`.
* Catálogo en árbol: al buscar un username, esa cuenta queda seleccionada
  (y visible) entre los peers de carpeta. Tras Agregar/Actualizar, el
  Username del editor se limpia también en vista árbol; la selección
  programática del árbol no recarga el editor.
* Cuentas del lote: buscador por username, contador `Cuentas: N` (y
  `visible / total` si hay filtro), columna Stories con ✅/❌, y al agregar
  se hace `focus`+`see` de la fila nueva sin seleccionarla (el editor no
  se rellena).
* Editor: `Agregar/Actualizar` a la altura de Username; `Pegar/Agregar`,
  `Pegar`, `Normalizar` y `Limpiar editor` apilados a la altura de URLs.
  Junto al combobox Username: icono compacto `clipboard_black.png` (pega
  el portapapeles) y ❌ (limpia solo Username), mismo tamaño que el
  buscador del catálogo y el de cuentas del lote.
* Click derecho en Lote, buscador del catálogo, Username, URLs y buscador
  del lote: menú Cortar / Copiar / Pegar / Eliminar / Seleccionar todo
  (i18n). No se usa el menú nativo de Windows para que sv-ttk y `tk.Text`
  se comporten igual y el idioma coincida con la GUI.
* Cola zombi: una secuencia `AWAITING_RENAME` sin lotes activos (todos
  `REMOVED`/`SKIPPED`) se cancela al abrirla y ya no secuestra el botón
  **Renombrar** de un lote suelto. Causa del error
  «No hay lotes para armar el comando de renombrado» con
  `descargas_2026_08_31_amber` (el lote en sí estaba correcto).
* Renombrar un lote desde Lotes usa ese lote, no la cola abierta.
* Un lote independiente solo avanza la cola si es el ítem `RUNNING`.
* **Quitar de cola** funciona con ítems `PENDING` y `COMPLETED` (no con
  `RUNNING`). Si la secuencia queda vacía, pasa a `CANCELLED`.
* `Finalizar sin renombrar`, `Ejecutado en otra instancia` y `Borrar lote`
  desenganchan el lote de la secuencia abierta. El ítem desaparece; si no
  queda nadie, la cola se cierra.
* Guardar lote muestra el error de nombre duplicado / `IntegrityError`
  en vez de un traceback.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_text_edit.py tests/test_gui_theme.py tests/test_i18n.py tests/test_gui_services.py`
* `python -m pytest -q tests/test_log_window.py tests/test_gui_theme.py`
* `python -m pytest -q tests/test_catalog_tree.py tests/test_notify_service.py tests/test_i18n.py tests/test_gui_services.py`
* `python -m pytest -q tests/test_gui_services.py -k "catalog_focus or filter_batch or stories_cell"`
* `python -m pytest -q tests/test_i18n.py`
* `python -m pytest -q tests/test_gui_services.py -k "queue or rename or elsewhere or detach or zombie or reactivat"`
* `python -m pytest -q`
* Modularización v2: `python -m pytest -q` → 294 passed
* `python -m pytest -q tests/gui/test_editor.py tests/gui/test_rename.py`
* Release v2.0.0: `python -m pytest -q` → 296 passed

## v1.31.0 - GUI: cola de lotes y rename combinado

Fecha: 2026-08-15

### Creado

* `tasks/Tarea_GUI_03.md`.
* `src/ig_orchestrator/gui/batch_queue_service.py`.
* Tablas `batch_run_queues` y `batch_run_queue_items`.

### Modificado

* Modal **Lotes / ejecuciones** deja de ser modal; pestaña Activos con
  selección múltiple y panel **Cola de ejecución**.
* Se pueden encadenar 2+ lotes, reordenar, quitar pendientes en caliente y
  renombrar juntos (parámetros unidos, `--move-renamed`).
* La cola persiste en SQLite para ejecutar en una instancia y renombrar en otra.
* Versión `1.31.0`.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "queue or rename or catalog"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.30.0 - GUI: catálogo, historial de un día

Fecha: 2026-08-15

### Creado

* `list_usernames_active_on_date` en `account_catalog_service.py`.

### Modificado

* Cuentas agregadas a un lote o descargadas hoy se pintan en amarillo claro
  (`#fff59d`) al iniciar la app y en cada refresh del catálogo.
* Prioridad de color: disabled > lote actual > hoy > inactivo > favorito.
* Dry-run no cuenta como descarga.
* Versión `1.30.0`.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "catalog or today or active_on_date"`

## v1.29.0 - GUI: Renombrar activo si quedan carpetas

Fecha: 2026-08-15

### Creado

* `src/ig_orchestrator/gui/rename_folder_status.py`.

### Modificado

* Tras Renombrar se inspecciona `WORKING_FOLDER`. Si quedan subcarpetas, el
  lote no pasa a `COMPLETED` y el botón sigue activo. La llamada conserva
  `--move-renamed`.
* `__version__` alineado con `pyproject.toml`.
* Versión `1.29.0`.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "unmoved or decide_rename or move-renamed or move_renamed"`

## v1.28.2 - Patch - GUI: pestaña Históricos y solo lectura

Fecha: 2026-08-11

### Creado

* `tasks/Patch_v1.28.2.md`.
* `list_historical_batches` para lotes `COMPLETED`.
* Modo `history_readonly` en la GUI principal.

### Modificado

* Modal **Lotes / ejecuciones** con pestañas **Activos** e **Históricos**
  (carga lazy del histórico).
* Abrir histórico: inspección de cuentas/URLs/carpetas sin editar ni ejecutar.
* Docs alineados; versión `1.28.2`.

### Resumen

Los lotes cerrados ya no desaparecen del alcance operativo: se consultan en
Históricos y se abren en solo lectura.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k historical`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.28.1 - Patch - GUI: checkbox Update y catálogo ownerId/path

Fecha: 2026-08-11

### Creado

* `tasks/Patch_v1.28.1.md`.
* `AccountDraft.is_catalog_update` y validación `validate_catalog_update_details`.
* `AccountHistoryRepository.update_identity_and_path` (id+path sin tocar field2).
* `save_catalog_metadata_to_history` unifica New account y Update.

### Modificado

* Editor: checkbox **Update** junto a New account (mutuamente excluyentes).
* Registrar/export/import persisten `ownerId`+`path` sin `is_new_account`.
* Estado de preparación en tabla: `Catálogo` para cuentas Update.
* Docs alineados; versión `1.28.1`.

### Resumen

Cuentas ya presentes en la BBDD maestra se pueden registrar en el orquestador
con id y ruta sin pasar por el renombrador como cuenta nueva, y la metadata
sobrevive export/import y el ciclo multi-instancia.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "catalog_update or rename_parameters or export_import"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.28.0 - Patch - GUI: Abrir carpeta y Ver URLs completadas

Fecha: 2026-08-11

### Creado

* `tasks/Patch_v1.28.0.md` documenta el menú contextual ampliado.
* `resolve_account_download_folder` en `batch_resume_service.py`.
* `list_account_problem_urls(..., kind="completed")` para jobs `COMPLETED`.

### Modificado

* Menú contextual de `Cuentas del lote actual`:
  * **Ver URLs completadas…** (habilitado si hay jobs completados).
  * **Abrir carpeta** (habilitado si la cuenta está `COMPLETED`).
* Doble click en una cuenta Completada abre el listado de URLs completadas.
* Docs alineados (`README.md`, `PLAN.md`, `tasks/task-gui.md`).
* Versión `1.28.0`.

### Resumen

Durante un lote en ejecución, una cuenta ya terminada permite inspeccionar sus
URLs completadas y abrir su carpeta de descarga en el explorador.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "problem_urls or download_folder"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.27.2 - Patch - Catálogo: cuenta exacta primero en el grupo de carpeta

Fecha: 2026-08-08

### Creado

* `tasks/Patch_v1.27.2.md` documenta el ajuste de orden del buscador.

### Modificado

* `filter_catalog_entries`: en match exacto con carpeta, la cuenta buscada
  aparece **primera** y el resto de peers de `field1` después (orden original).
* Docs alineados (`README.md`, `PLAN.md`, `tasks/task-gui.md`).
* Versión `1.27.2`.

### Resumen

Al buscar un username exacto en el catálogo, ya no hay que localizarlo a ojo
entre las hermanas de carpeta: queda siempre al inicio del listado filtrado.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k catalog_filter`
* `python -m pytest -q tests/test_package_smoke.py`

## v1.27.1 - Patch - GUI: carpeta en catálogo, URLs de lote, fallos y renombrado manual

Fecha: 2026-08-08

### Creado

* `tasks/Patch_v1.27.1.md` documenta los cuatro cambios de GUI.
* `filter_catalog_entries` en `account_catalog_service.py` (match exacto + peers de carpeta).
* `list_account_problem_urls` / `AccountProblemUrl` en `batch_resume_service.py`.
* `format_manual_rename_command_preview` y `format_command_for_shell` en `process_runner.py`.

### Modificado

* Buscador del catálogo: si el texto coincide exactamente con un username y
  tiene `field1`/`destination_path`, muestra todas las cuentas de esa carpeta.
* Diálogo `Lotes guardados y ejecuciones pendientes`: columna **URLs** con el
  total de `url_jobs` de origen `INPUT_URL` del lote.
* `PendingBatchSummary.url_count` en listados de lotes gestionados y pendientes.
* Durante/tras la ejecución, doble click o menú contextual en cuentas
  `Reintento` / `Fallida` abre una modal no bloqueante con las URLs afectadas;
  doble click en una fila abre Chrome.
* Botón **Renombrar Manual** (siempre habilitado) muestra el comando completo
  del script de renombrado con parámetros y permite copiarlo sin ejecutarlo.
* Tests de GUI actualizados.
* Versión `1.27.1`.

### Resumen

La GUI facilita localizar grupos de carpeta en el catálogo, ver el tamaño del
lote en URLs, inspeccionar fallos/reintentos en vivo y copiar el comando de
renombrado para ejecución manual.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`
* `python -m compileall -q src tests`

## v1.27.0 - Lotes: export/import y ciclo POR RENOMBRAR

Fecha: 2026-08-05

### Creado

* `src/ig_orchestrator/gui/batch_transfer_service.py` exporta e importa lotes
  en JSON portable (`ig_orchestrator.batch_export`).
* `tasks/Patch_v1.27.0.md` documenta el estado `AWAITING_RENAME`, el dialogo
  ampliado y el flujo multi-instancia.

### Modificado

* `InputBatchStatus` incorpora `AWAITING_RENAME` (descargas cerradas; falta
  renombrar o finalizar).
* El batch orchestrator, al completar todas las cuentas, deja el lote en
  `AWAITING_RENAME` en vez de `COMPLETED`.
* `batch_resume_service`: listados incluyen POR RENOMBRAR; `mark_batch_executed_elsewhere`,
  `is_batch_ready_for_rename` y finalizacion manual alineados al nuevo ciclo.
* Dialogo `Lotes / ejecuciones`: Exportar, Importar, Ejecutado en otra
  instancia, Renombrar, Finalizar sin renombrar.
* Tras renombrar con exito el lote pasa a `COMPLETED`.
* Tests de GUI, transfer y orchestrator actualizados.
* Version `1.27.0`.

### Resumen

Se puede llevar un lote a otra maquina (export/import), marcarlo como
ejecutado en otra instancia y, en cualquier caso, renombrar o cerrar el lote
sin perderlo en un limbo `COMPLETED` prematuro.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_batch_orchestrator.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.16 - Patch - Media not found 1 reintento y Detener proceso

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.16.md` documenta el tope de reintentos de
  `Media not found or unavailable` y el renombrado del boton de detencion.

### Modificado

* `src/ig_orchestrator/orchestration/retry_policy.py` limita ese error a
  **1 reintento** via `resolve_max_retries_for_error` /
  `last_error_type` en `calculate_retry_decision`.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` pasa
  `job.last_error_type` a la decision de reintento.
* `src/ig_orchestrator/gui/app.py` cambia el label a `Detener proceso` y alinea
  mensajes de detencion/interrupcion.
* `tests/test_retry_policy.py` cubre el tope de un reintento y que otros
  errores no se capan.
* `Agents.md`, `README.md` y `tasks/task-gui.md` documentan el comportamiento.
* Version actualizada a `1.26.16`.

### Resumen

`Media not found or unavailable` deja de consumir todo el presupuesto de
`MAX_RETRIES`, y la GUI habla de detener el proceso para reanudar despues.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_retry_policy.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.15 - Patch - Lote actual: orden Username y Guardar seleccion

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.15.md` documenta el orden por username, la seleccion
  multiple y el boton `Guardar selección`.

### Modificado

* `src/ig_orchestrator/gui/app.py` permite ordenar la tabla por `Username`
  (A-Z / Z-A), usa `selectmode=extended` y anade `Guardar selección` para
  persistir solo las filas elegidas como DRAFT, dejando el resto en mesa de
  trabajo sin ID de lote.
* `tests/test_gui_services.py` cubre helpers de orden y el guardado de
  seleccion con resto en memoria.
* `README.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.15`.

### Resumen

Desde la mesa de trabajo se puede reordenar el lote por nombre y partir
varias cuentas en lotes distintos sin vaciar a mano las que se quieren dejar
para despues.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.14 - Patch - Editor: checkboxes juntos y foco al final de URLs

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.14.md` documenta el layout de flags del editor y el caret
  al final tras pegar o normalizar URLs.

### Modificado

* `src/ig_orchestrator/gui/app.py` agrupa `Stories` y `New account` en un frame
  horizontal con checkboxes Tk (label clicable) y mueve el foco al final del
  textarea tras `Pegar` y `Normalizar`.
* `tests/test_gui_services.py` cubre el foco al final al pegar y normalizar.
* `README.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.14`.

### Resumen

Los flags del editor dejan de separarse en extremos y el listado de URLs
mantiene el caret al final al pegar o normalizar, sin tener que scrollear a
mano.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.13 - Patch - Catalogo: highlight en lote, Activar, foco y filtro

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.13.md` documenta el highlight temporal, `Activar`, la
  preservacion de foco y el boton de limpiar busqueda.

### Modificado

* `src/ig_orchestrator/gui/app.py` resalta en amarillo las cuentas del lote
  actual, anade `Activar` y el boton `❌` del filtro, y conserva seleccion y
  scroll al repintar el catalogo.
* `src/ig_orchestrator/gui/account_catalog_service.py` expone `enable` para
  reactivar cuentas `DISABLED` o `INACTIVE`.
* `tests/test_gui_services.py` cubre colores con `in_batch` y la reactivacion.
* `README.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.13`.

### Resumen

Al armar un lote se ve de un vistazo que cuentas ya estan en la tabla, se puede
reactivar un Delete, el catalogo no salta al usar el menu contextual y el
filtro se limpia con un boton compacto.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.12 - Patch - Estados, favoritos y agrupacion del catalogo

Fecha: 2026-08-01

### Creado

* `tasks/Patch_v1.26.12.md` documenta los nuevos estados visuales, el orden por
  ruta y la reactivacion automatica.

### Modificado

* `account_history` incorpora `is_favorite` y el estado `INACTIVE` mediante una
  migracion compatible con bases existentes.
* El repositorio y el servicio de catalogo persisten favoritos e inactividad,
  muestran tambien las bajas logicas y ordenan las cuentas por categoria,
  `field1` y username.
* El menu contextual del GUI permite marcar una cuenta inactiva, agregar o
  quitar el tag favorito y mantiene `Delete` como baja logica.
* El orquestador reactiva cuentas inactivas cuando realmente empiezan a
  procesarse, sin hacerlo en dry-run.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.12`.

### Resumen

El catalogo diferencia visualmente las cuentas prioritarias, pausadas y dadas
de baja, conserva la clasificacion en SQLite y agrupa las cuentas activas por
su ruta historica.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_batch_orchestrator.py tests\test_db_repositories.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.11 - Patch - Distribucion vertical del GUI

Fecha: 2026-07-26

### Creado

* `tasks/Patch_v1.26.11.md` documenta la nueva distribucion, el orden de las
  acciones, los scrollbars y la seleccion simple del catalogo.

### Modificado

* `src/ig_orchestrator/gui/app.py` mantiene el catalogo a la izquierda, apila
  el editor y el lote en la zona derecha, mueve todas las acciones del editor a
  una columna izquierda, agrega scroll visible a URLs y cambia el texto del
  checkbox a `Stories`.
* La seleccion simple del catalogo carga el username en el editor; el doble
  click conserva la apertura de Instagram.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen la nueva interfaz.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la version a `1.26.11`.

### Resumen

La zona de trabajo aprovecha todo el ancho derecho para editar arriba y revisar
el lote abajo, con acciones alineadas y scrollbars visibles en las tres areas
solicitadas.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`
  (`56 passed`).
* `python -m pytest -q` (`196 passed`).
* `python -m compileall -q src tests`.
* Construccion temporal de la ventana Tkinter: orden de acciones correcto,
  etiqueta `Stories`, tres scrollbars visibles y paneles horizontal/vertical.
* `git diff --check`.

## v1.26.10 - Patch - Flujo de alta y dimensiones del GUI

Fecha: 2026-07-24

### Creado

* `tasks/Patch_v1.26.10.md` documenta la deseleccion del editor, el pegado
  rapido, los anchos adaptativos y el sonido de finalizacion.

### Modificado

* `src/ig_orchestrator/gui/app.py` agrega `Pegar/Agregar`, deselecciona la
  cuenta al limpiar, reordena y dimensiona las columnas, adapta el catalogo al
  username mas largo y reproduce el aviso sonoro al terminar un lote.
* `tests/test_gui_services.py` cubre el nuevo comportamiento y los calculos de
  presentacion.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el flujo actualizado.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la version a `1.26.10`.

### Resumen

El editor permite volver de forma explicita al modo de alta, incorpora una
accion de pegar y guardar, aprovecha mejor el ancho de la ventana y avisa
audiblemente cuando termina el procesamiento.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py tests/test_package_smoke.py`
  (`55 passed`).
* `python -m pytest -q` (`195 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.9 - Patch - Contexto de lote nuevo y lote registrado

Fecha: 2026-07-23

### Creado

* `tasks/Patch_v1.26.9.md` documenta los contextos del editor y la transición
  segura a un lote nuevo.

### Modificado

* `src/ig_orchestrator/gui/app.py` muestra el contexto actual, diferencia
  `Registrar lote nuevo` de `Actualizar lote`, agrega `Nuevo lote`, reemplaza
  `Limpiar lote` por `Eliminar todo` y bloquea la edición de lotes ya iniciados.
* `src/ig_orchestrator/gui/batch_draft_service.py` y
  `src/ig_orchestrator/gui/batch_resume_service.py` permiten persistir y
  recuperar un `DRAFT` registrado sin cuentas, manteniendo bloqueada su
  ejecución hasta que vuelva a contener al menos una.
* `tests/test_gui_services.py` cubre las etiquetas de contexto, el reinicio de
  IDs y estado al crear un lote nuevo y el aviso con nombre e ID antes de
  eliminar todas las cuentas de un lote registrado.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el flujo actualizado.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la versión a `1.26.9`.

### Resumen

Preparar un segundo lote ya no puede reutilizar silenciosamente el ID de un
borrador recuperado: `Nuevo lote` crea un contexto limpio y el estado visible
indica en todo momento si el siguiente guardado crea o actualiza.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py` (`46 passed`).
* `python -m compileall -q src tests`.
* `python -m pytest -q` (`191 passed`).
* `git diff --check`.

## v1.26.8 - Patch - Doble click del catálogo

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.8.md` documenta el ajuste del evento.

### Modificado

* `src/ig_orchestrator/gui/app.py` carga el username seleccionado y sus datos
  de catálogo en el editor antes de abrir Instagram con doble click.
* `tests/test_gui_services.py` agrega la prueba de regresión de las dos acciones.
* `README.md` y `tasks/task-gui.md` aclaran el comportamiento.
* Version actualizada a `1.26.8`.

### Pruebas ejecutadas

* `pytest -q tests/test_gui_services.py tests/test_package_smoke.py`
  (`46 passed`).
* `pytest -q` (`186 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.7 - Patch - Maestro de lotes y cierre manual

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.7.md` documenta el alcance, los estados y la compatibilidad
  de persistencia del patch.

### Modificado

* `src/ig_orchestrator/models/input_batch.py` incorpora el estado `DRAFT` para
  distinguir lotes guardados de ejecuciones.
* `src/ig_orchestrator/input/batch_creation_service.py`,
  `src/ig_orchestrator/input/__init__.py` y
  `src/ig_orchestrator/gui/batch_draft_service.py` permiten crear y actualizar
  borradores conservando el batch id y bloquean cualquier edición tras la
  primera ejecución.
* `src/ig_orchestrator/gui/batch_resume_service.py` agrega el maestro conjunto,
  activación y borrado seguro de drafts, finalización manual de cuentas y la
  política que habilita el renombrador al cerrar todas las cuentas.
* `src/ig_orchestrator/gui/app.py` abre el catálogo con doble click, reemplaza
  el selector de pendientes por `Lotes / ejecuciones`, expone las acciones de
  borrador y agrega `Completar` al menú contextual de cuentas.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` diferencia la
  ausencia total de respuesta como `NO_BOT_RESPONSE`, evita una segunda espera
  redundante y deja que la política existente finalice la URL al agotar
  reintentos sin bloquear el lote.
* `tests/test_gui_services.py` y `tests/test_bot_conversation_service.py`
  cubren los nuevos estados, acciones y el silencio del bot.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el nuevo flujo.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la versión a `1.26.7`.

### Pruebas ejecutadas

* `pytest -q tests/test_gui_services.py tests/test_bot_conversation_service.py tests/test_account_orchestrator.py`
  (`59 passed`).
* `pytest -q` (`185 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.6 - Patch - Estado de Treeview durante la ejecucion

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.6.md` documenta el error y la correccion.

### Modificado

* `src/ig_orchestrator/gui/app.py` deja de pasar la opcion Tcl inexistente
  `-state` a `ttk.Treeview` y usa la API `Widget.state()` para mantener
  seleccionable `Lote actual` durante la ejecucion.
* `tests/test_gui_services.py` agrega una prueba de regresion para el manejo de
  estados ttk.
* Version del paquete actualizada a `1.26.6`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q`
  (`42 passed`).
* `python -m pytest -q` (`182 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.5 - Patch - Control de cuentas y ajustes de GUI

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.5.md` documenta el alcance del patch.

### Modificado

* `src/ig_orchestrator/gui/app.py` ajusta la ventana a media pantalla, compacta
  `Lote actual`, agrega scrollbars, conserva la seleccion durante el refresco,
  muestra el orden persistido al ejecutar y oculta los botones de reordenado.
* El catalogo incorpora click derecho `Abrir` / `Delete`; la baja usa
  `account_history.status = DISABLED` y no elimina datos.
* El campo `path` de `New account` es ahora un combobox editable con valores
  distintos de `account_history.field1`.
* La recuperacion y `Renombrar` releen desde SQLite la fecha global, el flag de
  cuenta nueva, `ownerId`, `startInitDate` y `path`, evitando depender del
  borrador en memoria despues de cancelar y reanudar.
* `Eliminar` permanece activo durante un lote para marcar una cuenta pendiente
  o en proceso como `FAILED` y sus jobs no terminales como `FAILED_FINAL`, con
  `MANUAL_ACCOUNT_REMOVAL`; los orquestadores respetan esa baja cooperativa.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el comportamiento.
  Version del paquete actualizada a `1.26.5`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_account_orchestrator.py
  tests/test_batch_orchestrator.py -q` (`52 passed`).
* `python -m pytest -q` (`181 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.4 - Patch - Recuperacion y seguimiento de batches desde GUI

Fecha: 2026-07-19

### Creado

* `src/ig_orchestrator/gui/batch_resume_service.py` consulta batches con trabajo
  reanudable, reconstruye el borrador completo, resume estados por cuenta y
  permite finalizar o marcar como interrumpido un lote.
* `tasks/Patch_v1.26.4.md` documenta el alcance del patch.

### Modificado

* `src/ig_orchestrator/gui/app.py` agrega el selector `Ejecuciones pendientes`,
  las acciones `Reanudar seleccionado` y `Dar por finalizado`, la recuperacion
  de `Lote actual` y estados por cuenta actualizados en color desde SQLite.
* `src/ig_orchestrator/gui/batch_draft_service.py`, `db/schema.sql` y
  `db/migrations.py` persisten de forma compatible la fecha global del lote y
  la asociacion de cuentas nuevas con sus parametros de renombrado.
* Al cancelar un proceso de batch desde la GUI, su estado queda `PARTIAL` sin
  alterar cuentas, URL jobs, errores ni archivos ya registrados.
* `tests/test_gui_services.py` cubre persistencia de metadatos, listado y
  reconstruccion de pendientes, progreso, cancelacion y finalizacion manual.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` documentan el flujo y las
  respuestas de persistencia. Version actualizada a `1.26.4`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_db_repositories.py
  tests/test_main_batch_modes.py tests/test_batch_orchestrator.py -q`
  (`42 passed`).
* `python -m pytest -q` (`174 passed`).

## v1.26.3 - Patch - Carpetas bajo demanda y limpieza de lote

Fecha: 2026-07-18

### Creado

* `src/ig_orchestrator/filesystem/batch_cleanup.py` implementa la limpieza
  conservadora posterior a cada lote real: temporales `telegram_media*` en la
  raiz de descargas y duplicados `*_1.mp4` verificados dentro de `reels/`.
* `tests/test_batch_cleanup.py` cubre temporales, alcance no recursivo y
  eliminacion de duplicados solo cuando existe el original.
* `tasks/Patch_v1.26.3.md` documenta el alcance y los criterios del patch.

### Modificado

* `src/ig_orchestrator/filesystem/folder_service.py` crea solo la carpeta raiz
  de la cuenta y deja de generar subcarpetas especulativas.
* `src/ig_orchestrator/filesystem/file_mover.py` crea `story/`, `reels/` o
  `highlights/` justo antes de mover el primer archivo destinado a ellas.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` ejecuta la limpieza
  al finalizar lotes reales, incluidos lotes parciales o con fallo de
  infraestructura, y la omite en dry-run.
* `src/ig_orchestrator/main.py` entrega al orquestador las rutas de descargas y
  trabajo necesarias para limitar la limpieza a las cuentas del lote.
* `src/ig_orchestrator/gui/app.py` agrega el boton `Clean` a la caja de estados
  para vaciar la consola sin alterar el proceso.
* `PLAN.md`, `README.md`, `tasks/Tarea8.md`, `tasks/Tarea17.md` y
  `tasks/task-gui.md` documentan las nuevas reglas.
* Tests de carpetas, movimiento, orquestadores y smoke adaptados al nuevo
  comportamiento. Version del paquete actualizada a `1.26.3`.

### Pruebas ejecutadas

* `python -m pytest tests/test_folder_service.py tests/test_file_mover.py
  tests/test_batch_cleanup.py tests/test_batch_orchestrator.py
  tests/test_package_smoke.py tests/test_gui_services.py -q` (`51 passed`).
* `python -m pytest -q` (`171 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.2 - Patch - Nuevas cuentas desde GUI y renombrador

Fecha: 2026-07-17

### Modificado

* `src/ig_orchestrator/gui/app.py` elimina el boton ambiguo `Agregar cuenta
  nueva` del catalogo y agrega el checkbox condicional `New account` al editor,
  con `ownerId`, `startInitDate` y `path` obligatorios. Las filas nuevas se
  incorporan al lote y al catalogo al pulsar `Agregar / Actualizar`.
* `src/ig_orchestrator/gui/batch_draft.py` y
  `src/ig_orchestrator/gui/batch_draft_service.py` modelan y validan los datos
  adicionales sin mezclarlos con la fecha de descarga de la cuenta.
* `src/ig_orchestrator/db/account_history_repository.py` y
  `src/ig_orchestrator/gui/account_catalog_service.py` conservan y exponen
  `ownerId`, `path` y `startInitDate` en el catalogo global.
* `src/ig_orchestrator/gui/process_runner.py` agrega un bloque repetible
  `--new-account USERNAME OWNER_ID START_INIT_DATE PATH` por cada cuenta nueva
  antes de `--no-duplicated --move-renamed`.
* `tests/test_gui_services.py` cubre campos obligatorios, persistencia del
  catalogo, filtrado de cuentas nuevas y comandos con multiples cuentas.
* `README.md` y `tasks/task-gui.md` documentan el nuevo flujo y el contrato del
  comando externo.
* Version actualizada a `1.26.2`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q`
  (`32 passed`).
* `python -m pytest -q` (`167 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.1 - Patch - Timestamp y renombrado manual desde GUI

Fecha: 2026-07-16

### Modificado

* `src/ig_orchestrator/gui/app.py` agrega fecha y hora local con milisegundos a
  cada linea de la consola de estado y situa el boton contextual `Renombrar`
  junto a las acciones de ejecucion. El boton solo se habilita al completar
  correctamente un lote real y transmite la salida del renombrador sin
  bloquear Tkinter.
* `src/ig_orchestrator/gui/process_runner.py` construye el comando para
  `ManualRenameFiles/main.py` con `--newRename`, la fecha global de la GUI,
  `--no-duplicated` y `--move-renamed`.
* `tests/test_gui_services.py` cubre el comando externo y el timestamp aplicado
  a todas las lineas.
* `tests/test_package_smoke.py` verifica la nueva version del paquete y del
  entrypoint.
* `README.md` y `tasks/task-gui.md` documentan el flujo, la ubicacion y las
  reglas de habilitacion del nuevo boton.
* Version actualizada a `1.26.1`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py -q` (`21 passed`).
* `python -m pytest -q` (`161 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.0 - Tarea GUI 2 - Ejecucion y progreso desde GUI

Fecha: 2026-07-15

### Modificado

* `src/ig_orchestrator/gui/account_catalog_service.py` ordena el catalogo
  alfabeticamente sin distinguir mayusculas y minusculas.
* `src/ig_orchestrator/gui/app.py` diferencia `Registrar lote` de `Ejecutar`,
  lanza el lote registrado sin bloquear Tkinter, transmite la salida al cuadro
  inferior y muestra progreso de cuentas e items.
* `src/ig_orchestrator/gui/process_runner.py` ejecuta `run_continue --batch-id`
  en un subproceso cancelable con salida sin buffer.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` ofrece progreso
  por item, incluyendo stories y reintentos sin incrementar el total.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` informa tambien el
  progreso de cuentas durante dry-run.
* `src/ig_orchestrator/main.py` activa el detalle por item solo para procesos
  nacidos desde GUI y permite dry-run de `run_continue` sin abrir Telegram.
* `tests/test_gui_services.py` y `tests/test_account_orchestrator.py` cubren el
  orden alfabetico, el comando del subproceso y el progreso por item.
* `README.md` documenta el registro, la ejecucion y los indicadores de progreso.
* Version actualizada a `1.26.0`.

### Pruebas ejecutadas

* `python -m pytest -q` (`159 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.25.5 - Patch - URLs equivalentes de publicaciones Instagram

Fecha: 2026-07-11

### Modificado

* `src/ig_orchestrator/gui/batch_draft_service.py` identifica publicaciones
  por su shortcode y considera duplicadas las variantes `/p/{shortcode}/` y
  `/reel/{shortcode}/`, conservando la primera URL pegada.
* `tests/test_gui_services.py` cubre la normalizacion y el contador de
  duplicados para ambas variantes de una misma publicacion.
* Version actualizada a `1.25.5`.

### Pruebas ejecutadas

* `python -m pytest -q` (`155 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.25.4 - Patch - Deduplicacion efectiva de URLs en GUI

Fecha: 2026-07-11

### Modificado

* `src/ig_orchestrator/gui/batch_draft_service.py` separa el parseo de URLs de
  su deduplicacion para que `Normalizar` y `Agregar / Actualizar` conserven
  solo la primera aparicion y el indicador pueda contar las repetidas.
* `tests/test_gui_services.py` corrige el caso de prueba con comillas y comas
  y verifica tanto el resultado normalizado como el contador de duplicados.
* Version actualizada a `1.25.4`.

### Pruebas ejecutadas

* `python -m pytest -q` (`153 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.25.3 - Patch - Lanzadores de Windows

Fecha: 2026-07-11

### Creado

* `ejecutar_gui.bat` abre la interfaz grafica desde la raiz del proyecto.
* `ejecutar_run_continue.bat` solicita un `batch_id`, valida que sea numerico
  y solo ejecuta `run_continue` cuando se ha introducido un valor.

### Resumen

Los dos lanzadores configuran `PYTHONPATH`, usan el entorno virtual local si
existe y funcionan aunque se invoquen desde otro directorio.

### Pruebas ejecutadas

* Inspeccion de comandos y validacion de los lanzadores sin ejecutar Telegram.

## v1.25.2 - Patch - Deduplicacion de URLs en GUI

Fecha: 2026-07-08

### Modificado

* `src/ig_orchestrator/gui/batch_draft_service.py` elimina URLs repetidas tras
  limpiar comillas y comas, conservando la primera aparicion.
* `tests/test_gui_services.py` cubre normalizacion y guardado con URLs
  duplicadas en formato limpio, con comillas y con coma final.
* Version actualizada a `1.25.2`.

### Resumen

Los botones `Normalizar` y `Agregar / Actualizar` usan la misma normalizacion,
por lo que las URLs duplicadas se eliminan antes de actualizar la caja o guardar
la cuenta en el lote.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q` (`18 passed`)
* `python -m compileall -q src tests`

## v1.25.1 - Patch - Ajustes GUI de lote

Fecha: 2026-07-07

### Modificado

* `src/ig_orchestrator/gui/app.py` inicializa `Batch name` desde el ultimo
  lote ejecutado en SQLite, rellena fechas de lote y cuenta con hoy, y mantiene
  la fecha de cuenta tras `Agregar / Actualizar`.
* `src/ig_orchestrator/gui/batch_draft_service.py` normaliza URLs pegadas con
  comillas, comas y coma final, compartiendo la misma logica entre el boton
  `Normalizar` y el guardado del lote.
* `tasks/task-gui.md` y `README.md` documentan el nuevo comportamiento.
* Version actualizada a `1.25.1`.

### Resumen

La GUI arranca con datos mas utiles para el flujo diario y acepta listados de
URLs copiados tanto como lista limpia por lineas como en formato con comillas y
comas.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q` (`16 passed`)
* `python -m compileall -q src tests`
* `python -m pytest -q` (`150 passed`)

## v1.25.0 - Tarea GUI 1 - Editor de lote y persistencia SQLite

Fecha: 2026-07-06

### Creado

* `src/ig_orchestrator/input/batch_creation_service.py` como servicio comun
  para crear lotes SQLite desde JSON o GUI.
* Paquete `src/ig_orchestrator/gui/` con borradores de lote, validacion,
  catalogo de cuentas, ventana Tkinter y placeholder de runner.
* `tests/test_gui_services.py` con cobertura de persistencia del borrador,
  catalogo desde `account_history`, catalogo desde `config/batch.json`,
  cuenta vacia invalida y batch duplicado.

### Modificado

* `src/ig_orchestrator/input/batch_importer.py` delega la persistencia en el
  servicio comun sin cambiar el contrato CLI existente.
* `src/ig_orchestrator/main.py` agrega `python -m ig_orchestrator gui`.
* `src/ig_orchestrator/input/__init__.py` expone los DTOs de creacion comun.
* Version actualizada a `1.25.0`.

### Resumen

La aplicacion puede abrir una GUI de escritorio con Tkinter para crear un lote,
seleccionar cuentas frecuentes desde SQLite o `config/batch.json`, editar filas
del borrador, validar URLs de Instagram y guardar el batch en SQLite sin tocar
`config/batch.json`. La ejecucion desde la ventana queda reservada para la
Tarea GUI 2.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_batch_importer.py tests/test_package_smoke.py tests/test_main_batch_modes.py -q` (`17 passed`)
* `python -m compileall -q src tests`
* `python -m pytest -q` (`144 passed`)
* `git diff --check` (solo avisos de normalizacion LF/CRLF)

## v1.24.5 - Patch - Post-proceso Manual Rename Files

Fecha: 2026-07-05

### Creado

* `src/ig_orchestrator/orchestration/post_processing.py` para ejecutar un
  comando externo opcional tras batch y reporte correctos.
* `D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat` como wrapper externo
  de automatizacion equivalente a `MRF.bat`, pero sin `pause`.
* `tests/test_post_processing.py` con pruebas de comando deshabilitado,
  configuracion incompleta, exito y fallo de `.cmd`.

### Modificado

* `src/ig_orchestrator/main.py` ejecuta el post-proceso solo despues de generar
  los reportes y solo si no hubo fallo de infraestructura en el batch.
* `src/ig_orchestrator/settings.py`, `.env.example` y `config/app.example.json`
  agregan `POST_PROCESS_ENABLED` y `POST_PROCESS_COMMAND`.
* `README.md` documenta que el wrapper recomendado es
  `D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat` y que `batch.json`
  no recibe parametros especificos del renombrador.
* Version actualizada a `1.24.5`.

### Pruebas ejecutadas

* `python -m pytest tests/test_settings.py tests/test_post_processing.py tests/test_package_smoke.py tests/test_main_batch_modes.py -q` (`14 passed`)
* `python -m pytest -q` (`139 passed`)
* `python -m compileall -q src tests`

## v1.24.4 - Patch - Prioridad de cuentas por stories y volumen

Fecha: 2026-06-24

### Modificado

* La importacion ordena las cuentas en memoria antes de persistirlas.
* Las cuentas con `download_stories = true` y sin URLs se insertan y procesan
  primero para anticiparse a la desaparicion de stories.
* Las cuentas restantes se ordenan de menor a mayor numero de URLs procesables;
  los empates conservan el orden original del JSON.
* No se agregaron campos, consultas de orden especiales ni migraciones SQLite.
* `README.md`, `PLAN.md`, `Agents.md` y `tasks/Tarea6.md` documentan el orden.
* Se agrego una prueba de importacion que verifica prioridad, orden estable y
  conteo de URLs deduplicadas.
* Version actualizada a `1.24.4`.

### Pruebas ejecutadas

* `python -m pytest tests/test_batch_importer.py tests/test_batch_json_parser.py tests/test_batch_orchestrator.py tests/test_main_batch_modes.py -q` (`19 passed`)
* `python -m pytest -q` (`134 passed`)
* `python -m compileall -q src tests`
* `git diff --check`

## v1.24.3 - Patch - Previews duplicados en posts de fotos

Fecha: 2026-06-24

### Modificado

* Las respuestas que contienen exclusivamente documentos de imagen con nombre
  original descartan los previews comprimidos sin nombre antes de persistirlos.
* Los previews siguen conservandose cuando son la unica media disponible.
* Las respuestas mixtas con video y fotos sin nombre mantienen todas las fotos,
  preservando el comportamiento requerido para stories.
* Se agrego una prueba de regresion basada en el caso real que generaba archivos
  `telegram_media_*` junto a los JPG numericos.
* Version actualizada a `1.24.3`.

### Pruebas ejecutadas

* `python -m pytest` (`133 passed`)
* `python -m compileall -q src tests`
* `git diff --check`

## v1.24.2 - Patch - Stories sin reintento y media mixta completa

Fecha: 2026-06-21

### Modificado

* El parser reconoce mediante expresion regular
  `Stories for {username} not found` como error definitivo
  `STORIES_NOT_FOUND`.
* Las respuestas mixtas de stories conservan simultaneamente documentos con
  nombre, videos y fotos sin nombre original.
* Las fotos de stories se renombran como
  `username-YYYYMMDD_HHMMSS.jpg`, usando sufijo numerico si coinciden.
* Se agregaron pruebas para el caso real de username dinamico y una respuesta
  de cinco stories formada por un video y cuatro fotos.
* Version actualizada a `1.24.2`.

### Pruebas ejecutadas

* `python -m pytest` (`132 passed`)
* `python -m compileall -q src tests`
* `git diff --check`

## v1.24.1 - Patch - Carpeta de logs unica por ejecucion

Fecha: 2026-06-21

### Modificado

* `main.py` fija un unico timestamp al inicio de `--run`, `run_continue` y
  `--dry-run`.
* `AccountOrchestratorConfig` transporta el inicio y la carpeta de logs de la
  ejecucion completa.
* Los logs de todas las cuentas, batches unidos y reintentos se escriben bajo
  una sola carpeta `logs/YYYYMMDD_HHMMSS`.
* Si un username se procesa mas de una vez en la misma ejecucion, se agrega
  contenido al mismo archivo en lugar de crear otra carpeta.
* `README.md` y `Agents.md` documentan la regla.

### Pruebas ejecutadas

* `python -m pytest`

## v1.24.0 - Tarea 24 - Lotes unicos, join e historico de cuentas

Fecha: 2026-06-21

### Creado

* `tasks/Tarea24.md`.
* `src/ig_orchestrator/models/account_history.py`.
* `src/ig_orchestrator/db/account_history_repository.py`.
* `src/ig_orchestrator/input/batch_file_service.py`.
* Tests de backup/limpieza, modos join, historico global, unicidad y progreso.

### Modificado

* Parser e importador para ignorar entradas vacias, rechazar `batch_name`
  repetidos y poblar `account_history`.
* Schema/migracion SQLite con `account_history` e indice unico para
  `input_batches.batch_name`.
* CLI para `--join-after-pending-batch-id` y
  `--join-before-pending-batch-id`.
* Orquestador de batch para mostrar avance por cuenta.
* `README.md`, `PLAN.md` y `Agents.md` con el nuevo contrato operativo.
* Version de paquete actualizada a `1.24.0`.

### Resumen

Cada lote tiene ahora una identidad unica. Un lote interrumpido se continua
desde SQLite y un lote nuevo puede encadenarse antes o despues de pendientes de
otro batch. La importacion real crea un backup, limpia el JSON reutilizable,
mantiene un historico global de usernames y muestra progreso compacto.

### Pruebas ejecutadas

* `python -m pytest` (`125 passed`)

## v1.21.5 - Patch - Resumen de reporte y duplicados persistidos

Fecha: 2026-06-17

### Creado

* Tabla `duplicate_url_jobs` para persistir URLs duplicadas detectadas durante la importacion.
* Tests para migracion/creacion de la tabla de duplicados en SQLite.
* Tests para importar duplicados de forma idempotente y reconstruirlos en reportes.

### Modificado

* `src/ig_orchestrator/db/schema.sql` para crear `duplicate_url_jobs` e indices relacionados con `batch_id`, `account_id`, `run_id` y `duplicate_of_url_job_id`.
* `src/ig_orchestrator/input/batch_json_parser.py` para conservar ocurrencias duplicadas ademas de las URLs unicas procesables.
* `src/ig_orchestrator/input/batch_importer.py` para guardar duplicados y enlazarlos al `url_job` original.
* `src/ig_orchestrator/db/url_job_repository.py` para asociar duplicados sin `run_id` a la ejecucion actual.
* `src/ig_orchestrator/reports/markdown_report_builder.py` para agregar resumen por username y tabla final de URLs duplicadas.
* `src/ig_orchestrator/reports/__init__.py` y `src/ig_orchestrator/input/__init__.py` para exponer los nuevos DTOs.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.5`.

### Resumen

El reporte de ejecucion incluye ahora un resumen superior por username con URLs
analizadas, URLs no procesadas, URLs duplicadas y archivos descargados. Las
URLs duplicadas quedan persistidas en SQLite y se muestran al final del reporte
en una tabla separada, de forma reconstruible aunque una ejecucion se corte y se
reanude.

### Pruebas ejecutadas

* `python -m pytest tests\test_markdown_report_builder.py tests\test_batch_importer.py tests\test_batch_json_parser.py tests\test_db_repositories.py tests\test_account_orchestrator.py tests\test_batch_orchestrator.py`

## v1.21.4 - Patch - Trazabilidad de run_id y reporte con id de job

Fecha: 2026-06-17

### Creado

* Tests para verificar que los `url_jobs` quedan asociados al run de cuenta y al run de batch.

### Modificado

* `src/ig_orchestrator/reports/markdown_report_builder.py` para agregar las columnas `N` e `Id Job` al reporte Markdown.
* `src/ig_orchestrator/db/url_job_repository.py` para asociar jobs sin `run_id` a una ejecucion.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` y `src/ig_orchestrator/orchestration/batch_orchestrator.py` para registrar `run_id` al iniciar una ejecucion sin sobrescribir jobs ya asociados.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.4`.

### Resumen

Los reportes de ejecucion incluyen ahora una correlacion secuencial `N` y el
identificador real de `url_jobs.id`. Al iniciar un run, los `url_jobs` que aun
no tienen `run_id` quedan vinculados a la ejecucion actual, preservando
asociaciones previas.

### Pruebas ejecutadas

* `python -m pytest tests\test_markdown_report_builder.py tests\test_account_orchestrator.py tests\test_batch_orchestrator.py tests\test_batch_importer.py tests\test_batch_json_parser.py`

## v1.21.3 - Patch - Modo run_continue y deduplicacion de descargas

Fecha: 2026-06-16

### Creado

* Test para localizar batches con trabajo reanudable desde SQLite.
* Test de `run_continue` sin importar JSON.
* Test para descartar descargas duplicadas exactas tipo `archivo.mp4` y `archivo_1.mp4`.

### Modificado

* `src/ig_orchestrator/main.py` para agregar el subcomando `run_continue`, que procesa batches existentes desde SQLite sin leer `batch.json`.
* `src/ig_orchestrator/db/batch_repository.py` para listar batches con cuentas y URLs en estados reanudables.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` para eliminar duplicados exactos antes de crear registros `download_files`.
* `.vscode/launch.json` para agregar `Ejecutar: run_continue` y `Depurar: run_continue`.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.3`.

### Resumen

El proceso puede reanudarse con `python -m ig_orchestrator run_continue`, leyendo
solo SQLite y procesando batches que tengan cuentas `PENDING`, `PROCESSING` o
`PARTIAL` con URLs en `PENDING`, `SENT_TO_BOT`, `WAITING_DOWNLOAD`,
`RETRY_PENDING` o `FAILED_TEMPORARY`. Las descargas duplicadas exactas con
sufijo numerico se filtran antes de persistir y mover archivos.

### Pruebas ejecutadas

* `python -m pytest tests\test_db_repositories.py tests\test_bot_conversation_service.py tests\test_package_smoke.py -q`
* `python -m json.tool .vscode\launch.json`
* `python -m pytest -q`

## v1.21.2 - Patch - Descarga directa de media de Telegram

Fecha: 2026-06-16

### Creado

* Tests para descarga directa desde mensajes del bot con documento y para previews sin nombre original.
* Tests para reanudar cuentas `PROCESSING` y URLs interrumpidas en `WAITING_DOWNLOAD`.

### Modificado

* `src/ig_orchestrator/telegram/telegram_client.py` para exponer `download_message_media` usando Telethon.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` para descargar media del bot directamente con Telethon, conservar documentos con nombre original y promover previews solo cuando no hay documentos finales.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` para reintentar URLs interrumpidas en `SENT_TO_BOT` o `WAITING_DOWNLOAD`.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` para reanudar cuentas `PROCESSING` o `PARTIAL`.
* `src/ig_orchestrator/reports/markdown_report_builder.py` para agregar la columna `Cantidad`.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y `tests/test_package_smoke.py` para actualizar la version a `1.21.2`.

### Resumen

La descarga ya no depende de tener Telegram Desktop abierto: Telethon descarga
directamente los media recibidos desde el bot. Los posts/reels con documentos
usan el nombre original enviado por el bot, mientras que las stories que solo
llegan como previews se guardan con nombre fallback por id de mensaje. Las
ejecuciones cortadas pueden retomarse procesando cuentas y URLs que quedaron a
medio camino.

### Pruebas ejecutadas

* `pytest tests\test_account_orchestrator.py tests\test_batch_orchestrator.py tests\test_bot_conversation_service.py tests\test_markdown_report_builder.py`
* `pytest`

## v1.21.1 - Ejecucion real con Telegram

Fecha: 2026-06-16

### Creado

* Test de smoke para el modo real usando servicio de Telegram simulado, archivo descargado falso, movimiento a carpeta de cuenta y reporte Markdown.

### Modificado

* `src/ig_orchestrator/main.py` para conectar el flujo real de `--input`: inicializa SQLite, importa JSON, arranca Telethon, procesa el batch con `BotConversationService`, mueve archivos con `UrlJobProcessor` y genera reporte Markdown.
* `.vscode/launch.json` para que `Ejecutar: ig_orchestrator` y `Depurar: ig_orchestrator` usen `config/batch.json --run` en lugar de `--dry-run`.
* `README.md` para documentar la ejecucion real, el modo `--run`, el uso de Telegram/Telethon y las salidas esperadas.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.1`.

### Resumen

La aplicacion ya puede lanzarse con datos reales desde CLI o VS Code usando `config/batch.json`: crea o reutiliza SQLite, importa el lote, conecta con Telegram mediante Telethon, envia cada URL al bot, detecta descargas, mueve archivos a las carpetas correspondientes de la cuenta, aplica reintentos y escribe reporte Markdown. El modo `--dry-run` queda como validacion sin efectos externos.

### Pruebas ejecutadas

* `python -m pytest -q`
* `python -m ig_orchestrator --input config\batch.json --dry-run`

## Documentacion README operativa

Fecha: 2026-06-16

### Modificado

* `README.md` para documentar configuracion, entorno, ejecucion por CLI y VS Code, flujo dry-run, flujo real previsto, SQLite, logs, descargas, reportes, errores, reintentos y responsabilidades por modulo.

### Resumen

El README ahora explica como preparar `.venv`, `.env`, `pyproject.toml`, batches JSON y sesiones Telethon, ademas de aclarar que el entrypoint actual soporta `--dry-run` y que la ejecucion real completa aun no esta cableada desde `main.py`.

### Pruebas ejecutadas

* `python -m ig_orchestrator --input config\batch.json --dry-run`
* `python -m pytest -q`

## v1.21.0 - Tarea 21 - Tests minimos obligatorios

Fecha: 2026-06-15

### Creado

* No se crearon modulos productivos nuevos; la suite obligatoria ya estaba cubierta por tests existentes.

### Modificado

* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.0`.
* `CHANGELOG.md` para documentar el cierre de la cobertura minima obligatoria.

### Resumen

Se verifico que la suite minima obligatoria cubre `settings`, `batch_json_parser`,
`batch_importer`, `url_classifier`, `retry_policy`, `bot_response_parser`,
`file_watcher`, `file_classifier`, `folder_service`, `file_mover`, repositorios
SQLite, `markdown_report_builder`, y los orquestadores de cuenta y lote en
modo dry-run. La suite usa mocks, SQLite temporal y filesystem temporal, sin
depender de Telegram real ni de rutas de produccion.

### Pruebas ejecutadas

* `pytest`

## v1.20.0 - Tarea 20 - Modo dry-run

Fecha: 2026-06-15

### Creado

* Tests de dry-run en `tests/test_account_orchestrator.py`, `tests/test_batch_orchestrator.py` y `tests/test_package_smoke.py`.

### Modificado

* `src/ig_orchestrator/orchestration/account_orchestrator.py` para simular el procesamiento de una cuenta sin invocar Telegram, sin mover archivos y sin crear carpetas por defecto.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` para simular el procesamiento de un lote y crear un run/resumen claro de dry-run.
* `src/ig_orchestrator/main.py` para aceptar `--input ... --dry-run`, inicializar SQLite, importar el JSON y procesar el lote en modo simulacion.
* `src/ig_orchestrator/orchestration/__init__.py`, `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para exponer la configuracion de dry-run y actualizar la version a `1.20.0`.

### Resumen

El flujo principal puede ejecutarse como `python -m ig_orchestrator --input config\batch.example.json --dry-run`.
El modo dry-run valida settings, rutas, JSON e importacion a SQLite, crea runs
simulados con resumen explicito y lista lo que habria procesado sin enviar
mensajes a Telegram, sin mover archivos y sin crear la estructura de carpetas
real por defecto.

### Pruebas ejecutadas

* `python -m pytest tests\test_account_orchestrator.py tests\test_batch_orchestrator.py tests\test_package_smoke.py -q`
* `python -m compileall -q src`
* `python -m pytest`

## v1.19.0 - Tarea 19 - Logs

Fecha: 2026-06-15

### Creado

* `src/ig_orchestrator/logging_config.py` con configuracion de `logs/app.log`, logs por ejecucion/cuenta en `logs/YYYYMMDD_HHMMSS/username.log`, contexto de ejecucion y redaccion basica de secretos.
* `tests/test_logging_config.py` con pruebas de escritura de logs globales, logs por cuenta/run y redaccion de valores sensibles.

### Modificado

* `src/ig_orchestrator/orchestration/account_orchestrator.py` para registrar inicio/cierre de cuenta, carpetas, URLs procesadas, decisiones de reintento y fallos de infraestructura.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` para registrar inicio/cierre de lote y cuentas procesadas.
* `src/ig_orchestrator/orchestration/url_job_processor.py` para registrar procesamiento de URL, correcciones de tipo, movimiento de archivos y errores de movimiento.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` para registrar mensaje enviado al bot, respuesta del bot, errores clasificados y archivos detectados.
* `src/ig_orchestrator/reports/markdown_report_builder.py` para registrar el reporte Markdown generado.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.19.0`.

### Resumen

La aplicacion genera un log global en `logs/app.log` para trazas generales,
warnings y errores, y un log por username dentro de la carpeta de ejecucion
`logs/YYYYMMDD_HHMMSS/username.log`. Los eventos principales de lote, cuenta,
URL, Telegram, archivos, errores, reintentos y reportes quedan trazados con
`run_id` y `account_username`, sin registrar claves sensibles ni valores
evidentes de secretos.

### Pruebas ejecutadas

* `python -m pytest tests\test_logging_config.py -q`
* `python -m compileall -q src`
* `python -m pytest`

## Planificacion - CLI opcional y renumeracion de tareas

Fecha: 2026-06-15

### Creado

* `tasks/Tarea_Post01.md` para conservar la CLI completa con Typer como tarea opcional posterior.

### Modificado

* `tasks/Tarea19.md` a `tasks/Tarea23.md` para compactar la secuencia principal tras sacar la CLI.
* `PLAN.md` para reemplazar la CLI obligatoria por ejecucion desde `.bat` llamando al punto de entrada principal con JSON.
* `Agents.md` para ajustar la convencion principal hasta `Tarea 23 => v1.23.0`.
* `requirements.txt` para retirar `typer` y `rich` del camino principal.

### Resumen

La CLI completa deja de bloquear `v1.0.1`. El flujo principal queda orientado a
ejecutar `python -m ig_orchestrator --input config\batch.example.json` desde un
`.bat`, inicializando SQLite, importando el JSON, procesando desde SQLite y
generando reportes.

### Pruebas ejecutadas

* `python -m pytest tests\test_package_smoke.py`

## v1.18.0 - Tarea 18 - Reporte Markdown

Fecha: 2026-06-15

### Creado

* `src/ig_orchestrator/reports/__init__.py` para exponer el builder de reportes.
* `src/ig_orchestrator/reports/markdown_report_builder.py` con construccion del reporte desde SQLite, render Markdown y escritura en disco.
* `tests/test_markdown_report_builder.py` con pruebas del render y de reconstruccion desde SQLite con URLs sin archivos y con multiples archivos.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.18.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.18.0`.
* `tests/test_package_smoke.py` para esperar la version `1.18.0`.
* `CHANGELOG.md` para documentar la tarea.

### Resumen

La aplicacion puede reconstruir un reporte Markdown desde SQLite para un run de
cuenta o batch, incluyendo fecha de ejecucion, tabla con username, tipo, URL,
ficheros, estado y directorio. Las URLs sin descargas muestran `0 files`, las
URLs con varios ficheros los agrupan en la misma celda y la ruta generada queda
persistida en `runs.report_path`.

### Pruebas ejecutadas

* `python -m pytest tests\test_markdown_report_builder.py`
* `python -m pytest`

## v1.17.0 - Tarea 17 - Orquestador de cuenta y lote

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/orchestration/account_orchestrator.py` con el flujo de cuenta: creacion de carpetas, procesamiento de stories generadas antes de URLs manuales, cola FIFO de reintentos y cierre de estado de cuenta/run.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` con el flujo de batch: carga del lote, procesamiento de cuentas pendientes y resumen final.
* `tests/test_account_orchestrator.py` con pruebas de orden de URLs, reintentos FIFO, cuenta parcial e infraestructura fallida.
* `tests/test_batch_orchestrator.py` con pruebas de procesamiento de cuentas pendientes y estado parcial de lote.

### Modificado

* `src/ig_orchestrator/orchestration/__init__.py` para exponer los orquestadores.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.17.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.17.0`.
* `tests/test_package_smoke.py` para esperar la version `1.17.0`.
* `CHANGELOG.md` para documentar la tarea.

### Resumen

La aplicacion puede coordinar una cuenta completa desde SQLite usando el
procesador de URL existente, crear las carpetas de trabajo, ejecutar primero
stories generadas, luego URLs manuales, enviar fallos temporales a una cola FIFO
de reintentos y marcar la cuenta como `COMPLETED`, `PARTIAL` o `FAILED`. El
orquestador de batch procesa solo cuentas pendientes y consolida el estado final
del lote sin ejecutar renombrador, limpiar duplicados ni mover a destino final.

### Pruebas ejecutadas

* `python -m pytest tests\test_account_orchestrator.py tests\test_batch_orchestrator.py`
* `python -m pytest`
* `python -m ig_orchestrator`

## v1.16.0 - Tarea 16 - Procesador de URL job

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/orchestration/url_job_processor.py` con la capa de aplicacion para procesar un `url_job_id`, delegar en Telegram, mover archivos descargados y persistir el resultado.
* `tests/test_url_job_processor.py` con pruebas usando conversacion falsa, SQLite temporal y movimiento real en carpetas temporales.

### Modificado

* `src/ig_orchestrator/db/download_repository.py` para actualizar metadatos completos de archivos movidos.
* `src/ig_orchestrator/db/url_job_repository.py` para corregir `publication_type` tras inspeccionar archivos descargados.
* `src/ig_orchestrator/orchestration/__init__.py` para exponer el procesador.
* `.vscode/launch.json` para agregar una tercera configuracion `Tests: pytest`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.16.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.16.0`.
* `tests/test_package_smoke.py` para esperar la version `1.16.0`.

### Resumen

La aplicacion puede procesar una URL por id desde SQLite: obtiene el job y la
cuenta, usa el servicio de conversacion con el bot, conserva errores
definitivos o temporales ya clasificados, mueve archivos descargados a la
estructura de cuenta, actualiza los `DownloadFile` con `working_path` y estado,
corrige reels con solo imagenes a `POST` y marca el job como `COMPLETED`.

### Pruebas ejecutadas

* `python -m pytest tests\test_url_job_processor.py tests\test_db_repositories.py`
* `python -m json.tool .vscode\launch.json`
* `python -m pytest`
* `python -m ig_orchestrator`

## v1.15.0 - Tarea 15 - Servicio de conversacion con bot

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/telegram/bot_conversation_service.py` con el flujo de conversacion para procesar una URL contra el bot de Telegram.
* `tests/test_bot_conversation_service.py` con pruebas usando mocks de Telegram y watcher, mas SQLite temporal para persistencia.

### Modificado

* `src/ig_orchestrator/db/url_job_repository.py` para guardar `sent_message_id`.
* `src/ig_orchestrator/telegram/__init__.py` para exponer el servicio de conversacion.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.15.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.15.0`.
* `tests/test_package_smoke.py` para esperar la version `1.15.0`.

### Resumen

La aplicacion puede procesar un `UrlJob` completo contra el bot: marcarlo como
enviado, enviar la URL, guardar el mensaje enviado, leer respuestas del bot,
clasificar errores reintentables y definitivos, activar el watcher si no hay
error, asociar archivos detectados en SQLite y terminar como `DOWNLOADED` o
`RETRY_PENDING` cuando no aparecen archivos. El servicio usa un lock asincrono
por instancia para evitar procesar dos URLs simultaneamente en `v1.0.1`.

### Pruebas ejecutadas

* `python -m pytest tests\test_bot_conversation_service.py`
* `python -m pytest tests\test_db_repositories.py`
* `python -m pytest`
* `python -m ig_orchestrator`

## v1.14.0 - Tarea 14 - Movimiento de archivos por tipo

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/file_mover.py` con movimiento de archivos descargados a carpetas de cuenta segun tipo de publicacion y medio.
* `tests/test_file_mover.py` con pruebas usando carpeta temporal para reels, posts, stories, highlights, sufijos seguros y reclasificacion de reels con solo imagenes.

### Modificado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer el movimiento de archivos y la resolucion de tipo final.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.14.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.14.0`.
* `tests/test_package_smoke.py` para esperar la version `1.14.0`.

### Resumen

La aplicacion puede mover archivos descargados a la estructura temporal de la
cuenta: reels a `reels`, stories a `story`, highlights a `highlights` y posts a
la raiz del usuario. El movimiento devuelve modelos `DownloadFile` actualizados
con `working_path`, estado clasificable para SQLite y tamano final. Si el
destino ya existe, se conserva el archivo previo y se usa un sufijo numerico
seguro. Los reels que descargan solo imagenes se resuelven como posts.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.13.0 - Tarea 13 - Clasificador de archivos

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/file_classifier.py` con clasificacion de archivos descargados por extension.
* `tests/test_file_classifier.py` con pruebas unitarias para imagenes, videos, extensiones en mayusculas y tipos desconocidos.

### Modificado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer el clasificador y los conjuntos de extensiones.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.13.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.13.0`.
* `tests/test_package_smoke.py` para esperar la version `1.13.0`.

### Resumen

La aplicacion puede clasificar archivos descargados como `IMAGE`, `VIDEO` o
`UNKNOWN` a partir de su extension, sin distinguir mayusculas/minusculas y sin
tocar el sistema de archivos real.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.12.0 - Tarea 12 - Watcher de descargas

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/file_watcher.py` con un watcher pasivo para detectar archivos nuevos o modificados tras un instante de inicio, ignorar temporales y directorios, y esperar estabilidad de tamano.
* `tests/test_file_watcher.py` con pruebas usando carpeta temporal para archivos nuevos, temporales, directorios, timeout y estabilizacion de tamano.

### Modificado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer `watch_downloaded_files`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.12.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.12.0`.
* `tests/test_package_smoke.py` para esperar la version `1.12.0`.

### Resumen

La aplicacion puede observar una carpeta de descargas y devolver solo archivos
creados o modificados despues de `start_time`, sin moverlos ni depender de
Telegram real. El watcher espera a que no haya cambios durante
`stable_seconds`, filtra extensiones temporales comunes y devuelve una lista de
`Path` ordenada.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.11.0 - Tarea 11 - Politica de reintentos por ronda

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/orchestration/__init__.py` para exponer la politica de reintentos.
* `src/ig_orchestrator/orchestration/retry_policy.py` con decisiones explicitas de retry, fallo final y no reintento, calculo de backoff y cola FIFO.
* `tests/test_retry_policy.py` con pruebas unitarias de backoff, errores no reintentables, max retries, cola FIFO y validaciones.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.11.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.11.0`.
* `tests/test_package_smoke.py` para esperar la version `1.11.0`.

### Resumen

La aplicacion puede calcular la siguiente accion para una URL fallida sin dormir
ni tocar Telegram: reintentar con backoff exponencial limitado, marcar fallo
final al agotar reintentos o por error no reintentable, y mantener una cola FIFO
para reintentos al final de la pasada principal.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.10.0 - Tarea 10 - Parser de respuestas del bot

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/telegram/bot_response_parser.py` con clasificacion de respuestas del bot, errores reintentables y no reintentables.
* `tests/test_bot_response_parser.py` con pruebas unitarias para cada error conocido, respuestas OK y respuestas vacias.

### Modificado

* `src/ig_orchestrator/telegram/__init__.py` para exponer el parser y sus enums.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.10.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.10.0`.
* `tests/test_package_smoke.py` para esperar la version `1.10.0`.

### Resumen

La aplicacion puede clasificar textos de respuesta del bot sin depender de
Telegram real. Los errores conocidos se detectan sin distinguir
mayusculas/minusculas, el mensaje original se conserva como `last_error` y el
tipo de error queda disponible en `last_error_type` para la futura politica de
reintentos y persistencia.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.9.0 - Tarea 9 - Cliente Telegram con Telethon

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/telegram/__init__.py` para exponer el wrapper de Telegram.
* `src/ig_orchestrator/telegram/telegram_client.py` con configuracion segura, arranque de Telethon, envio al bot y lectura de mensajes.
* `tests/test_telegram_client.py` con pruebas unitarias basadas en mocks sin conexion real a Telegram.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.9.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.9.0` y declarar Telethon como dependencia runtime.
* `tests/test_package_smoke.py` para esperar la version `1.9.0`.

### Resumen

La aplicacion cuenta con un wrapper asincrono para Telethon que crea el cliente
con la sesion configurada, reutiliza la instancia durante la ejecucion, permite
enviar mensajes al bot configurado, leer mensajes recientes y filtrar mensajes
nuevos posteriores a un timestamp. La configuracion oculta `api_hash` en su
representacion y los tests no dependen de Telegram real.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.8.0 - Tarea 8 - Servicio de carpetas

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer el servicio de carpetas.
* `src/ig_orchestrator/filesystem/folder_service.py` con `ensure_account_folders` y la estructura `AccountFolderPaths`.
* `tests/test_folder_service.py` con pruebas unitarias usando carpeta temporal.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.8.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.8.0`.
* `tests/test_package_smoke.py` para esperar la version `1.8.0`.

### Resumen

La aplicacion puede crear de forma idempotente la estructura temporal de una
cuenta dentro de la carpeta de trabajo: raiz del usuario, `story`, `reels` y
`highlights`. Si las carpetas ya existen, se conservan sus contenidos y solo se
crean las subcarpetas faltantes.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.7.0 - Tarea 7 - Clasificador de URLs

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/input/url_classifier.py` con clasificacion inicial de URLs de Instagram y error explicito para entradas invalidas.
* `tests/test_url_classifier.py` con pruebas unitarias para posts, reels, stories, highlights, URLs desconocidas de Instagram y URLs no Instagram.

### Modificado

* `src/ig_orchestrator/input/batch_importer.py` para usar el clasificador dedicado.
* `src/ig_orchestrator/input/__init__.py` para exponer `UrlClassifierError` y `classify_instagram_url`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.7.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.7.0`.
* `tests/test_package_smoke.py` para esperar la version `1.7.0`.

### Resumen

La clasificacion inicial de URLs queda aislada en un modulo testeable. Las URLs
de highlights, stories, reels y posts se clasifican segun las reglas de la
tarea, los posts sin `img_index` siguen entrando inicialmente como `REEL`, las
rutas desconocidas de Instagram se mantienen como `UNKNOWN` y las URLs fuera
del dominio de Instagram fallan con `UrlClassifierError`.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.6.0 - Tarea 6 - Importador JSON a SQLite

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/input/batch_importer.py` con importacion de JSON validado a `input_batches`, `accounts` y `url_jobs`.
* `tests/test_batch_importer.py` con pruebas de importacion, stories generadas, clasificacion inicial e idempotencia.

### Modificado

* `src/ig_orchestrator/input/__init__.py` para exponer el importador.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.6.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.6.0`.
* `tests/test_package_smoke.py` para esperar la version `1.6.0`.

### Resumen

La aplicacion puede importar un lote parseado o un JSON directamente a SQLite,
reutilizando el batch y las cuentas existentes al reimportar el mismo lote para
evitar duplicados razonables. Si `download_stories` es verdadero, se genera la
URL de stories y se guarda como `url_job` con `source = GENERATED_STORY`. Las
URLs manuales se guardan con `source = INPUT_URL` y clasificacion inicial de
stories, highlights, reels y posts. Cuando el importador recibe `Settings`,
persiste configuracion operativa no sensible en `app_config`.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.5.0 - Tarea 5 - Parser de JSON por lotes

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/input/__init__.py` para exponer el parser de lotes.
* `src/ig_orchestrator/input/batch_json_parser.py` con `parse_batch_json`, DTOs de lote parseado y errores de validacion claros.
* `tests/test_batch_json_parser.py` con pruebas unitarias del contrato de entrada JSON.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.5.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.5.0`.
* `tests/test_package_smoke.py` para esperar la version `1.5.0`.

### Resumen

La aplicacion puede leer un JSON de lotes, validar campos obligatorios,
heredar defaults por cuenta, limpiar espacios, deduplicar URLs dentro de la
misma cuenta, validar fechas `YYYY-MM-DD` y restringir URLs al dominio de
Instagram. Los errores incluyen contexto de cuenta y campo problematico.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `parse_batch_json("config/batch.example.json")`

## v1.4.0 - Tarea 4 - SQLite schema, migraciones y repositorios

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/db/schema.sql` con las tablas `app_config`, `input_batches`, `accounts`, `runs`, `url_jobs` y `download_files`.
* `src/ig_orchestrator/db/connection.py` para abrir conexiones SQLite con `row_factory` y claves foraneas activas.
* `src/ig_orchestrator/db/migrations.py` con inicializacion idempotente de la base de datos.
* `src/ig_orchestrator/db/config_repository.py` para persistir configuracion operativa.
* `src/ig_orchestrator/db/batch_repository.py` para crear, consultar y actualizar lotes.
* `src/ig_orchestrator/db/account_repository.py` para crear, consultar y actualizar cuentas.
* `src/ig_orchestrator/db/url_job_repository.py` para crear, consultar y actualizar trabajos de URL.
* `src/ig_orchestrator/db/download_repository.py` para crear, consultar y actualizar archivos descargados.
* `src/ig_orchestrator/db/run_repository.py` para crear y actualizar ejecuciones.
* `tests/test_db_repositories.py` con pruebas de integracion usando SQLite temporal.

### Modificado

* `src/ig_orchestrator/db/__init__.py` para exponer conexion, migraciones y repositorios.
* `src/ig_orchestrator/main.py` con un comando minimo `init-db`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.4.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.4.0`.
* `tests/test_package_smoke.py` para esperar la version `1.4.0`.

### Resumen

La aplicacion puede inicializar SQLite sin borrar datos existentes, crear las
tablas de persistencia definidas en el plan y operar sobre batches, cuentas,
URL jobs, archivos descargados, runs y configuracion mediante repositorios
testeables.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `python -m ig_orchestrator init-db --db-path <sqlite-temporal>`

## v1.3.0 - Tarea 3 - Modelos de dominio

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/models/account.py` con `Account` y `AccountStatus`.
* `src/ig_orchestrator/models/app_config.py` con `AppConfig` y `ConfigValueType`.
* `src/ig_orchestrator/models/input_batch.py` con `InputBatch` y `InputBatchStatus`.
* `src/ig_orchestrator/models/url_job.py` con `UrlJob`, `PublicationType`, `UrlSource` y `UrlJobStatus`.
* `src/ig_orchestrator/models/download_file.py` con `DownloadFile`, `MediaType` y `DownloadFileStatus`.
* `src/ig_orchestrator/models/run_summary.py` con `RunSummary` y `RunStatus`.
* `src/ig_orchestrator/models/__init__.py` para exponer los modelos de dominio.
* `tests/test_models.py` con pruebas unitarias de creacion y validaciones minimas.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.3.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.3.0`.
* `tests/test_package_smoke.py` para esperar la version `1.3.0`.

### Resumen

La aplicacion cuenta con modelos de dominio ligeros basados en `dataclasses`,
enums para estados y tipos definidos en el plan, y validaciones minimas para
identificadores, textos obligatorios, fechas, rutas, contadores y metadatos de
archivos.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.2.0 - Tarea 2 - Settings y configuracion

Fecha: 2026-06-13

### Creado

* `src/ig_orchestrator/settings.py` con `Settings`, `SettingsError` y `load_settings`.
* `tests/test_settings.py` con pruebas unitarias de carga, variables faltantes y variables reservadas opcionales.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.2.0`.
* `pyproject.toml` para actualizar la version y declarar dependencias runtime de configuracion.
* `tests/test_package_smoke.py` para esperar la version `1.2.0`.

### Resumen

La aplicacion puede cargar configuracion desde `.env` y variables de entorno,
validando campos obligatorios con mensajes claros, convirtiendo rutas a
`pathlib.Path` y manteniendo la configuracion futura de renombrado/movimiento
final como opcional.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.1.0 - Tarea 1 - Estructura base del proyecto

Fecha: 2026-06-13

### Creado

* `pyproject.toml` para empaquetar el proyecto con layout `src`.
* `.env.example` con las variables previstas para la serie `v1.x`.
* `src/ig_orchestrator/__init__.py`.
* `src/ig_orchestrator/__main__.py`.
* `src/ig_orchestrator/main.py`.
* `tests/test_package_smoke.py`.
* `data/.gitkeep`, `logs/.gitkeep` y `reports/.gitkeep`.
* `.vscode/launch.json` con configuraciones para depurar `ig_orchestrator` y ejecutar `pytest`.

### Modificado

* `README.md` con uso inicial.
* `requirements.txt` con dependencias base documentadas en el plan.
* `.gitignore` para proteger `.env`, sesiones de Telethon, SQLite y logs sin bloquear carpetas base.
* `tasks/Tarea1.md` para incluir `launch.json` en el alcance de la tarea.

### Resumen

El paquete se puede importar y ejecutar con `python -m ig_orchestrator`, mostrando
una salida minima sin implementar todavia logica de Telegram ni negocio. Tambien
queda disponible una configuracion compartida de VS Code para ejecutar y depurar
la aplicacion o los tests.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `python -m json.tool .vscode\launch.json`

## Planificacion - Versionado por tarea

Fecha: 2026-06-13

### Modificado

* `tasks/Tarea1.md` a `tasks/Tarea24.md`: cada tarea ahora apunta a su minor propio, de `v1.1.0` a `v1.24.0`.
* `PLAN.md`: agregada convencion de versionado minor por tarea y patch por correccion.
* `Agents.md`: agregada instruccion para responder con comandos sugeridos de commit y tag.
* `.github/copilot-instructions.md`: agregada convencion de versionado por tarea.

## v1.0.1 - Planificacion inicial

Fecha: 2026-06-13

### Creado

* `Agents.md` con instrucciones base para IA.
* `.github/copilot-instructions.md` con instrucciones resumidas para Copilot.
* `tasks/Tarea1.md` a `tasks/Tarea24.md`.
* `config/batch.example.json` como ejemplo de entrada por lotes.
* `config/app.example.json` como ejemplo de configuracion operativa persistible en SQLite.

### Modificado

* `PLAN.md` reestructurado para `v1.0.1`.

### Notas

`v1.0.1` queda centrada en descarga, SQLite, reintentos y reportes. Renombrado, duplicados del renombrador y movimiento final quedan documentados como backlog posterior.
