# feat-uc2-19 — Mover cuentas a un nuevo lote GUARDADO (v3.19.0)

## Objetivo
Sacar cuentas del lote actual (también en ejecución) a un lote nuevo que queda GUARDADO (borrador), eligiendo el nombre o aceptando uno derivado del lote padre. Complementa la pausa del feat-uc2-18, que se mantiene.

## Qué se hizo
- `pause_accounts_to_new_batch(target_name=...)`: crea el borrador si el nombre está libre, amplía un borrador existente, rechaza nombre vacío, el del propio lote o el de un lote que no es borrador.
- `suggest_split_name`: `<padre>_PARTE2`, `_PARTE3`… (primer nombre libre).
- GUI: clic derecho → «Mover a nuevo lote guardado…» (diálogo con nombre sugerido). Mismo núcleo que Pausar (`_split_selected_accounts`).
- Prueba: sugerencia, creación, ampliación y rechazos.

## Qué no
- Mantiene la condición del feat 18: solo cuentas sin empezar (pendientes, sin URLs enviadas). Sacar una cuenta ya iniciada rompería su historial de descargas y no se hace.
- Solo esquema GUI.

## Resultado de la implementación
Hecho; suite completa 579 passed, 1 skipped. Sin probar con la GUI abierta ni con Telegram real.
