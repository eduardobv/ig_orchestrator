# feat-uc2-18 — Pausar cuentas de un lote (v3.18.0)

## Objetivo
Apartar de un lote una o varias cuentas **que aún no han empezado** (p. ej. una con muchísimas URLs) para que el lote termine sin ellas y quede listo para renombrar; las cuentas apartadas pasan a un lote GUARDADO (DRAFT) con el nombre original + sufijo.

## Qué se hizo
- `gui/batches/pause.py`: `pause_accounts_to_new_batch` mueve `batch_accounts` (y sus `batch_urls`, `duplicate_urls`) al lote `<nombre>_PAUSA` (DRAFT; se amplía si ya existe como borrador, `_PAUSA2`… si está ocupado). Todo o nada, una transacción `BEGIN IMMEDIATE`, `UPDATE` condicionado a PENDING.
- Condiciones: cuenta `PENDING` con todas las URLs `PENDING`; lote IMPORTED/PROCESSING/PARTIAL; no se puede vaciar el lote.
- `BatchOrchestrator`: omite cuentas cuyo `batch_id` ya no es el del lote → permite pausar con el lote en ejecución; el resumen se calcula sin ellas (lote → `AWAITING_RENAME`).
- GUI: clic derecho en la tabla de cuentas → «Pausar (mover a lote guardado)…» (multiselección).
- 5 pruebas en `tests/gui/test_pause_accounts.py`, incluida la pausa a mitad de ejecución con el orquestador real y un procesador falso.

## Qué no
- No hay estado «PAUSED» de cuenta ni reanudación en el mismo lote: la vuelta es ejecutar el lote guardado.
- Solo esquema GUI (v2); en la base v1/CLI no está disponible.
- Si el lote está inactivo (no ejecutándose) y al pausar no queda trabajo, no se marca solo como terminado: se hace con el flujo habitual (Ejecutar/«Marcar ejecutado»).

## Resultado de la implementación
Hecho; suite completa 578 passed. Sin probar con Telegram real ni con la GUI abierta (la lógica de menú/refresco solo se verificó por importación).
