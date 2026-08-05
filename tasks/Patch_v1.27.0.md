# v1.27.0 - Lotes: export/import y ciclo POR RENOMBRAR

## Objetivo

Mover lotes entre instancias y poder renombrar o cerrar sin perder el lote al
marcarlo completado demasiado pronto.

## Estados

| Estado | Significado |
|--------|-------------|
| DRAFT | Guardado editable |
| IMPORTED / PROCESSING / PARTIAL / FAILED | Ejecucion de descarga |
| **AWAITING_RENAME** | Descargas cerradas (local u otra instancia); renombrar o finalizar |
| COMPLETED | Cerrado del todo; no aparece en pendientes |

## Acciones del dialogo

* Exportar / Importar (JSON)
* Ejecutado en otra instancia → `AWAITING_RENAME`
* Renombrar (carga el lote y lanza el script; al OK → COMPLETED)
* Finalizar sin renombrar → COMPLETED

## Pruebas

* Export/import roundtrip
* mark_executed_elsewhere
* Orchestrator COMPLETED summary → AWAITING_RENAME
