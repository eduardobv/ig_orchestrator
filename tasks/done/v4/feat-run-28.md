# feat-run-28 · Orden de ejecución del lote y 2 reintentos para stories (v4.2.0)

## Objetivo
Las stories caducan, así que van primero (por prioridad y luego por orden de alta); después posts/reels/highlights de forma incremental, de la cuenta con menos URLs a la que más.

## Resultado de la implementación
* Barrida 1 (stories): prioridad (rango) y luego orden del lote.
* Barrida 2: menos URLs pendientes → más reels → menos posts → cuenta no nueva → orden del lote.
* Stories: máximo 2 reintentos (`STORY_MAX_RETRIES`); un máximo configurado menor se respeta. Antes: el global (5).
* Ver `CHANGELOG.md` (v4.2.0).

## No se hizo
* La prioridad no influye en la segunda barrida (no se pidió).
* El «total» de la segunda barrida cuenta URLs **pendientes** (abiertas), no las ya completadas, para que un lote reanudado se ordene por lo que falta.
* No se probó con Telegram real.
