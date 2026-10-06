# Tarea 17 - Orquestador de cuenta y lote

Version objetivo: `v1.17.0`

## Objetivo

Coordinar todo el proceso para una cuenta y para un batch.

## Archivos

```text
src/ig_orchestrator/orchestration/account_orchestrator.py
src/ig_orchestrator/orchestration/batch_orchestrator.py
```

## Flujo de cuenta

1. Cargar cuenta desde SQLite.
2. Crear solo la carpeta raiz de la cuenta; las subcarpetas de contenido se
   crean al mover archivos reales.
3. Procesar primero URL de story generada si existe.
4. Procesar URLs manuales una por una.
5. Si una URL falla temporalmente, agregar a cola de reintento.
6. Al terminar la pasada principal, procesar cola FIFO de reintentos.
7. Marcar cuenta como `COMPLETED`, `PARTIAL` o `FAILED`.

## Flujo de batch

1. Cargar batch.
2. Procesar cuentas pendientes.
3. Crear un run de batch o runs por cuenta.
4. Generar resumen final.

## Criterios de aceptacion

* Si algunas URLs fallan definitivamente, marcar cuenta como `PARTIAL`.
* Si todas completan, marcar `COMPLETED`.
* Si falla infraestructura, marcar `FAILED`.
* No ejecutar renombrador.
* No limpiar duplicados del renombrador. Al finalizar un lote real si se
  eliminan copias de transferencia `*_1.mp4` dentro de `reels/` cuando existe
  el `.mp4` original, ademas de temporales `telegram_media*` que hayan quedado
  en la raiz de descargas de Telegram.
* No mover a destino final.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests de orquestador en dry-run/mocks.
