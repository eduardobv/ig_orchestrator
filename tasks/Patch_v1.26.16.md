# Patch v1.26.16 - Media not found 1 reintento y Detener proceso

## Objetivo

Evitar reintentar hasta 6 veces URLs con `Media not found or unavailable`, y
alinear el lenguaje de la GUI con la detencion reanudable del lote.

## Cambios

* `MEDIA_NOT_FOUND_OR_UNAVAILABLE` usa tope propio `max_retries=1` (un
  reintento tras el fallo inicial); el resto de errores reintentables sigue
  con `MAX_RETRIES` global.
* Boton y mensajes: `Detener proceso` / detencion solicitada / lote detenido
  (misma semantica: `PARTIAL` y trabajo conservado en SQLite).

## Pruebas

* Unitarias de politica de reintentos.
* Suite completa.
