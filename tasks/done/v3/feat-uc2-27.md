# feat-uc2-27 · No volver a analizar cuentas analizadas recientemente (v4.14.0)

## Objetivo
Al analizar una carpeta (p. ej. `Deleted`) no repetir las consultas a Instagram de cuentas que otro análisis reciente ya respondió (por ejemplo las movidas allí tras analizarlas en otra carpeta).

## Resultado de la implementación
* `create_run(folder_id, reuse_hours)`: cada cuenta toma la respuesta conclusiva (`AVAILABLE`/`UNAVAILABLE`) más reciente de otro análisis si es más nueva que la ventana; guarda `source_run_id` y la fecha original. `UNKNOWN` nunca se reutiliza. Sin pendientes, el análisis nace completado.
* Ajuste `accountcheck.reuse_hours` en *Configuración > Catálogo* (48 h por defecto, 0 = desactivar).
* Modal: columna *Analizada* (con `(#origen)`), «reutilizadas N», aviso al crear y casilla *Re-analizar las ya analizadas en otros análisis* (fuerza solo las reutilizadas).
* Migración aditiva de la columna `source_run_id` y de un índice `(username, checked_at)`.
* Tests: `tests/account_status/test_reuse.py`.

## No hecho
* No se probó sobre las 54 cuentas reales ni abriendo la pestaña Catálogo de Configuración en la GUI.
* La ventana se mide desde la fecha de la respuesta original, no desde la fecha de creación del análisis nuevo.
* No se reutilizan respuestas de cuentas sin análisis previo ni se reanaliza automáticamente al caducar la ventana en un análisis ya creado.
