# feat-uc2-17 — Pausa y reanudación de lotes (v3.17.0)

## Problema
1. **Pausar** con un lote suelto mostraba «No hay cola en ejecución» (solo existía pausa de colas).
2. Tras **Detener**, **Ejecutar** intentaba registrar de nuevo el lote y fallaba con «Batch name … already exists»; solo reiniciar la app lo recuperaba.

## Qué se hizo
- Pausa de lote suelto: termina el proceso, el lote queda PARTIAL, el botón pasa a *Reanudar* y relanza `run_continue` del mismo lote.
- `_execute` reanuda el lote activo ya existente (no DRAFT/COMPLETED) sin volver a guardarlo.

## Qué no
- No hay suspensión real del proceso (la pausa es detener y continuar; SQLite conserva el avance).

## Resultado de la implementación
Hecho; 3 pruebas nuevas en `tests/gui/test_run.py`. Sin probar con Telegram real.
