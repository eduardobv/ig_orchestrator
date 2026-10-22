# feat-uc2-21 — Gestión de lotes en la modal y retirada de las colas de la GUI (v3.21.0)

## Problema
Las colas confundían (no se podían editar ni cancelar bien) y los lotes guardados no se podían reorganizar: había que decidir de antemano cuántas cuentas llevaba cada uno.

## Qué se hizo
- Se eliminan de la GUI todas las opciones de cola (panel y botones de la modal, secuencia de ejecución, pausa de cola, restauración al arrancar, renombrado combinado, publicación por cola). El servicio `batch_queue_service` y las tablas siguen en la base (solo se retira la GUI).
- La modal «Lotes guardados y ejecuciones» muestra, al seleccionar un lote activo, la tabla **Cuentas del lote** (username, prio, URLs, stories, start date).
- Acciones nuevas: **Nuevo lote** (borrador vacío), **Cambiar nombre**, **Borrar lote** (vacío o con cuentas), **Mover cuentas a…** (a un GUARDADO existente o nuevo) y **Recuperar** (histórico, solo si nunca se inició).
- Botones: se quita *Traer descargas*; «Recuperar / Modificar» → **Editar**; «Reanudar / Ejecutar» → **Ejecutar** (traducidos es/en en `shared/locales`).
- La ventana principal se resincroniza si tenía abierto el lote afectado.
- Código: `gui/batches/manage.py`, `move_accounts_to_batch` en `gui/batches/pause.py`, `_sync_editor_with_batches`.

## Qué no
- Borrar solo vale para lotes GUARDADOS o nunca iniciados; un lote con ejecuciones se cierra con «Finalizar sin renombrar» (borrarlo perdería el historial de descargas).
- «Recuperar» solo para lotes del histórico sin ejecuciones ni progreso. Los ya ejecutados solo se abren en lectura.
- Mover exige destino GUARDADO; de un lote en ejecución solo salen cuentas sin empezar (y no puede quedar vacío).
- Si la ventana principal tiene cambios sin guardar del mismo lote que se modifica desde la modal, se recarga desde la base.
- Sin colas no hay renombrado combinado de varios lotes: se renombra lote a lote.
- No se borró el código del servicio de colas ni sus tests.

## Resultado de la implementación
Hecho. La modal se comprobó con Tk real (tabla de detalle y botones) en `tests/gui/test_batch_management.py`; los diálogos secundarios (nombre, destino) no se pulsaron a mano. Sin probar con Telegram real.
Suite completa: 589 passed.
