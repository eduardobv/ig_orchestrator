# Tarea GUI 3: leftover rename, catálogo del día y cola de lotes

Serie de tres minors sobre la GUI de escritorio.

| Fase | Versión | Alcance |
|------|---------|---------|
| 1 | v1.29.0 | Tras Renombrar, el botón sigue activo si quedan carpetas por mover |
| 2 | v1.30.0 | Catálogo: cuentas agregadas o descargadas hoy en amarillo claro |
| 3 | v1.31.0 | Cola de lotes en secuencia + rename combinado (multi-instancia) |

## Fase 1 — v1.29.0

- La llamada al script **siempre** incluye `--move-renamed`.
- Tras el proceso se inspecciona `WORKING_FOLDER` (primer nivel, sin ocultos).
- Si quedan carpetas, el lote no pasa a `COMPLETED` y Renombrar permanece activo.
- Si no quedan y el exit code es 0, se cierra el lote como hasta ahora.

## Fase 2 — v1.30.0

- Al iniciar la app (y en cada refresh del catálogo) se calculan las cuentas
  tocadas **hoy** (fecha local): agregadas a un lote o con un `runs` real.
- Color `#fff59d`. Prioridad: disabled > lote actual > hoy > inactivo > favorito.
- Dry-run no cuenta como descarga.

## Fase 3 — v1.31.0

- Tablas `batch_run_queues` / `batch_run_queue_items` en SQLite.
- En Activos se pueden seleccionar varios lotes, ordenarlos y ejecutarlos
  uno tras otro. Los `PENDING` se pueden quitar mientras corre otro lote.
- Al terminar la cola (o al seleccionar varios POR RENOMBRAR) el renombrado
  une `--startNowDate` (el más reciente) y todos los `--new-account`.
- La cola persiste: una instancia puede ejecutar y otra, con la misma SQLite,
  renombrar.

## Fuera de alcance

- Ejecución en paralelo.
- Cambios al script `ManualRenameFiles`.
- UI web.
