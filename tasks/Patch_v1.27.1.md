# v1.27.1 - Patch GUI: catálogo por carpeta, URLs de lote, fallos y renombrado manual

## Objetivo

Mejorar la operatividad de la GUI sin cambiar el motor de descarga:

1. Catálogo: match exacto de cuenta expande el grupo de la misma carpeta (`field1`).
2. Maestro de lotes: columna **URLs** con el total de URLs de entrada del lote.
3. Ejecución: inspeccionar URLs en reintento o fallidas por cuenta y abrirlas en Chrome.
4. **Renombrar Manual**: ver y copiar el comando del renombrador con todos los parámetros.

## Detalle

### 1. Catálogo / `filter_catalog_entries`

* Query vacía → todas las entradas.
* Username exacto (case-insensitive) con `destination_path` no vacío → todas las
  cuentas con el mismo path (trim + casefold).
* Exacto sin path → solo esa cuenta.
* Sin exacto → substring en username (comportamiento previo).

### 2. Columna URLs

* `PendingBatchSummary.url_count` = `COUNT(url_jobs)` con `source = 'INPUT_URL'`.
* No cuenta stories generadas (`GENERATED_STORY`), para que N cuentas × M URLs
  del editor coincida con el total mostrado.

### 3. Modal de problemas

* Estados de reintento: `SENT_TO_BOT`, `WAITING_DOWNLOAD`, `RETRY_PENDING`,
  `FAILED_TEMPORARY`.
* Fallidas: `FAILED_FINAL`.
* Apertura: doble click en fila o menú contextual.
* Diálogo no modal (sin `grab_set`); auto-refresh ~1s si el proceso corre.
* Doble click en URL → pestaña de Chrome.

### 4. Renombrar Manual

* Botón siempre habilitado junto a `Renombrar`.
* No ejecuta; muestra preview + línea shell (`list2cmdline`) y **Copiar comando**.
* Prefiere relectura SQLite del lote activo/guardado; si no hay, usa draft en pantalla.

## Archivos principales

* `src/ig_orchestrator/gui/account_catalog_service.py`
* `src/ig_orchestrator/gui/batch_resume_service.py`
* `src/ig_orchestrator/gui/process_runner.py`
* `src/ig_orchestrator/gui/app.py`
* `tests/test_gui_services.py`
* `README.md`, `PLAN.md`, `tasks/task-gui.md`, `CHANGELOG.md`

## Pruebas

* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`
* `python -m compileall -q src tests`
