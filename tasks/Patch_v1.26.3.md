# Patch v1.26.3 - Carpetas bajo demanda y limpieza de lote

## Objetivo

Evitar subcarpetas vacias, retirar residuos seguros al terminar cada lote real
y permitir vaciar manualmente la consola de estado de la GUI.

## Alcance

* Crear solo la raiz de cada cuenta al comenzar.
* Crear `story/`, `reels/` y `highlights/` al mover el primer archivo real.
* Eliminar al cerrar un lote los `telegram_media*` que permanezcan como
  ficheros en la raiz de descargas de Telegram.
* Eliminar en cada `reels/` del lote un `*_1.mp4` solo si existe el `.mp4`
  homologo sin `_1`.
* No ejecutar limpieza en `dry-run`.
* Agregar el boton `Clean` a la caja de estados.
* Cubrir la logica con tests y actualizar documentacion y version.
