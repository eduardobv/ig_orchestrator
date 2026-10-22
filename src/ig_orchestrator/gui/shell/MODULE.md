# Módulo: gui/shell

## Propósito
Composition root: `launch_gui` e `InstagramOrchestratorApp` (estado de sesión + layout).

## Archivos
- `app.py` — `__init__`, `_build_widgets`, `_restore_open_queue`

## Estado que posee
`connection`, `settings`, `accounts`, `saved_batch_id`, `active_batch_id`,
`active_queue_id`, `process_runner`, `runtime_progress`, StringVars, widgets,
`_editor_bound_username`.

## Habla con
Mixins de catalog/editor/batch_accounts/chrome/run/batches/settings.
Servicios GUI (sin Tk). SQLite. ProcessRunner → CLI.

## Tests
`tests/gui/` (instancian `InstagramOrchestratorApp`).

## Cómo cambiar esto
Solo añadir un atributo de estado nuevo aquí. La lógica de un panel va en su mixin.

## v4.0 (feat-gui-26)
- `app.py`: botonera con Ejecutar/Pausar en la misma celda, botón Pull y Renombrar manual oculto.
