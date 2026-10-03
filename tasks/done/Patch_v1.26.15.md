# Patch v1.26.15 - Lote actual: orden Username y Guardar seleccion

## Objetivo

Organizar mejor la mesa de trabajo del lote: ordenar por username y guardar
solo un subconjunto de cuentas como lote DRAFT.

## Cambios

* Click en encabezado `Username` alterna orden A-Z / Z-A (indicador ▲/▼).
* Treeview en `selectmode=extended` (Ctrl/Shift + click).
* Boton `Guardar selección`:
  - exige al menos una fila seleccionada;
  - si hay lote DRAFT en edicion, actualiza ese id con la seleccion;
  - si no, crea un DRAFT nuevo con el nombre actual;
  - elimina de la tabla las cuentas guardadas;
  - deja el resto como lote nuevo sin registrar (nuevo nombre sugerido).
* `Registrar lote` / `Actualizar lote` siguen guardando **todas** las cuentas.
* `Eliminar` elimina todas las filas seleccionadas.

## Pruebas

* Helpers de orden y heading.
* Guardado de seleccion con resto en memoria y SQLite.
* Suite GUI + completa.
