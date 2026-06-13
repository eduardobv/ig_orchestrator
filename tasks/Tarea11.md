# Tarea 11 - Politica de reintentos por ronda

Version objetivo: `v1.11.0`

## Objetivo

Calcular cuando reintentar una URL fallida y soportar una cola FIFO de reintentos al final de la pasada principal.

## Archivo

```text
src/ig_orchestrator/orchestration/retry_policy.py
```

## Inputs

```text
retries
max_retries
base_seconds
max_seconds
non_retryable
```

## Reglas

```text
0 retries => esperar 90 segundos
1 retry => esperar 180 segundos
2 retries => esperar 360 segundos
3 retries => esperar 720 segundos
4 retries => esperar 900 segundos
>= max_retries => FAILED_FINAL
non_retryable => FAILED_FINAL sin retry
```

## Criterios de aceptacion

* No dormir dentro de la politica.
* La politica solo calcula.
* Exponer decision clara: reintentar, fallo final o no reintentar.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios de backoff.
* Tests de error no reintentable.
* Tests de max retries.
