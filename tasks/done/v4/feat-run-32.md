# feat-run-32 · Completar por http y Ver URLs pendientes (v4.21.0)

## Objetivo
Cuando el usuario sabe que el bot está caído, poder descargar por HTTP todo lo que falta de una cuenta con un clic, y ver todo lo que falta.

## Resultado de la implementación
* Menú de la cuenta: **Completar por http…** (modal con todas / primeras N y espera en segundos, solo para esa ejecución) y **Ver URLs pendientes…** (tipo `pending` = no `COMPLETED`).
* Reutiliza `run_manual_http_download` con `interval_seconds` y `allow_busy`; avance en la barra de estado y consola.
* Decisión mía: con el lote parado también se descargan URLs en `SENT_TO_BOT`/`WAITING_DOWNLOAD`; con una espera elegida se ignoran variación y franja nocturna.

## No se hizo / límites
* No se bloquea iniciar una ejecución mientras corre un *Completar por http*.
* Sin prueba contra Instagram real ni con un lote grande.
