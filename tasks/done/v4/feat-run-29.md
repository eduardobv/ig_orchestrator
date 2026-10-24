# feat-run-29 · Posts eliminados: no reintentar (v4.3.0)

## Objetivo
Ahorrar reintentos (y días en lotes grandes) en posts/reels que ya no existen.

## Resultado de la implementación
* Spike: el texto «Post no disponible» no está en el HTML (se pinta con JS), pero la página de error lleva `PolarisErrorRoot` + `httpErrorPage` y las buenas `og:title`.
* Tras `Media not found or unavailable`, comprobación anónima (`post_availability.py`); eliminado → `FAILED_FINAL` / `MEDIA_REMOVED`; existe o dudoso → hasta 3 reintentos.
* Ver `CHANGELOG.md` (v4.3.0).

## No se hizo / límites
* Un +18 se ve igual que un eliminado; decisión del usuario: el bot descarga +18, así que «Media not found» ahí se considera definitivo.
* Sin ajuste para desactivar la comprobación ni «canario» que detecte si Instagram empieza a devolver siempre la página de error.
* Stories y highlights no se comprueban.
