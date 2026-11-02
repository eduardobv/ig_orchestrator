# feat-gui-29 · Botón Cargar en el modal de lotes (v4.22.0)

## Objetivo
Cargar un lote PARTIAL (no editable) en la ventana principal sin ejecutarlo.

## Resultado de la implementación
* Botón **Cargar** a la izquierda de *Editar*; reutiliza `_load_persisted_draft` (igual que Ejecutar, sin `_start_batch`). POR RENOMBRAR queda listo para Renombrar.

## No se hizo
* No se bloquea la edición del lote cargado (igual que tras Run+Stop).
