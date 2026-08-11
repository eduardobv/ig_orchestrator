# v1.28.2 - Patch GUI: pestaña Históricos y solo lectura

## Objetivo

Mostrar lotes `COMPLETED` en el modal **Lotes / ejecuciones** sin mezclar
botones de edición/ejecución, y permitir abrirlos solo para inspección.

## Detalle

### Modal con pestañas

* `ttk.Notebook`:
  * **Activos (N)** — comportamiento previo (`list_managed_batches`).
  * **Históricos (N)** — lazy load al seleccionar la pestaña.
* Históricos: solo `status = COMPLETED`.
* Acciones en históricos: **Abrir (solo lectura)**, **Exportar**, **Cerrar**.
* Sin Recuperar, Ejecutar, Renombrar, Finalizar, Borrar, etc.

### Modo solo lectura

* Cabecera: `HISTÓRICO · solo lectura · {nombre} · id=N · COMPLETED`.
* Deshabilita registrar/ejecutar/eliminar/renombrar y mutaciones del editor.
* Permite menú contextual de inspección (URLs, Abrir carpeta).
* **Nuevo lote** sale del modo histórico.

### Servicio

* `list_historical_batches(connection)` ordenado por `updated_at DESC`.
* `PendingBatchSummary.display_status` → `COMPLETADO` para cerrados.

## Archivos

* `src/ig_orchestrator/gui/batch_resume_service.py`
* `src/ig_orchestrator/gui/app.py`
* `tests/test_gui_services.py`
* Docs / CHANGELOG

## Pruebas

* `python -m pytest -q tests/test_gui_services.py -k historical`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`
