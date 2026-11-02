# feat-run-34 · Tiempo estimado en Completar por http (v4.23.0)

## Objetivo
Decidir cuántas URLs descargar y qué espera usar viendo cuándo termina.

## Resultado de la implementación
* Etiqueta en vivo en la modal (`trace_add` + refresco cada 15 s): `N × espera = duración · hora de fin`.
* Funciones puras `estimate_http_duration` / `format_http_duration` en `http_fallback/manual.py`, con test.

## No se hizo / límites
* Solo cuenta la espera entre URLs; no el tiempo de cada petición.
