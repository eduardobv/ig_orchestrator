# feat-run-37 · Stories de 1-2 items y Reiniciar lote (v4.11.0)

## Objetivo
1. Corregir la atribución de respuestas del bot en stories: con 1-2 items el bot envía miniaturas y luego los adjuntos; el fin de espera por silencio cortaba antes y el adjunto se asignaba a la URL siguiente.
2. Añadir *Reiniciar desde cero* para un lote ya iniciado.

## Resultado de la implementación
* `bot_conversation_service.py`: en `STORY` solo cuentan las miniaturas sin nombre; con 1-2 se espera a los adjuntos (`story_attachment_wait_seconds`, 20 s) y se descartan las miniaturas; ignora mensajes con `reply_to` a otro mensaje nuestro.
* `gui/batches/restart.py` + `Lote > Reiniciar desde cero…`: URLs y cuentas a PENDING, lote a IMPORTED, registros de descarga eliminados de la base, archivos del disco intactos; luego ejecuta.
* Tests: `tests/telegram/test_completion.py` (4 nuevos), `tests/gui/test_restart_batch.py`.

## No hecho
* No se ha probado con el bot real ni con la GUI abierta.
* Un adjunto que llegue después de agotar la espera (20 s) aún podría cruzarse con la URL siguiente; `reply_to` solo ayuda si el bot responde como respuesta.
* No hay entrada de *Reiniciar* en el clic derecho del modal de lotes (solo menú Lote, sobre el lote activo).

## Ampliación v4.12.0 (feat-run-38)
Botón y clic derecho **Reiniciar…** en el modal de lotes (activos e históricos), con advertencia de pérdida de estado y de descargas.
