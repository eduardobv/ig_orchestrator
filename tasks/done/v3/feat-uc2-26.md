# feat-uc2-26 · Estado de las cuentas de una carpeta (v4.13.0)

## Objetivo
Saber qué cuentas de una carpeta contenedora (p. ej. `09.DELETED`) siguen existiendo en Instagram y poder moverlas a otra carpeta.

## Resultado de la implementación
* Clic derecho en carpeta > *Comprobar estado de las cuentas…* abre una modal con tabla ordenable (usuario, estado ✔/✘/?/…, ruta), filtro y historial de análisis.
* `GET https://www.instagram.com/<cuenta>/` anónimo; `profile_id` en el HTML = existe. Espera configurable (`run.accountcheck.interval_seconds`, 30 s) y plazo (`run.accountcheck.timeout_seconds`).
* Se detiene solo en el primer 429 y a mano; se puede reanudar. El análisis (sin empezar, parcial, detenido, completo) se guarda en `account_check_runs`/`account_check_results`.
* Mover seleccionadas reutiliza `pick_folder` (sugerencias, búsqueda, nueva carpeta) y `plan_move_accounts` con vista previa.
* v4.14.1: doble clic en una fila abre la cuenta en el navegador.
* v4.13.1: clic derecho en la tabla > *Abrir en el navegador* / *Abrir en el explorador*.
* v4.13.2: *Mover no existentes*, contador de seleccionadas, columnas `MOVED`/ruta destino (movidas no seleccionables ni movibles), *Catálogo > Revisar análisis de estado…*, y corrección del cuelgue al mover muchas cuentas (planificar/ejecutar en hilo, aviso de progreso, vista previa hija de la modal).
* Tests: `tests/account_status/test_account_status.py`.

## No hecho
* No se probó un 429 real ni un movimiento real desde la modal sobre `G:`.
* Sin columnas extra (la tabla admite añadirlas); sin exportación del análisis; sin cambio automático del estado de la cuenta según el resultado (solo lo hace el movimiento a carpetas `-Deleted`/`-Inactive`, ya existente).
* Una página de login o un cambio de HTML de Instagram daría ✘ falsos: conviene revisar antes de mover en masa.
