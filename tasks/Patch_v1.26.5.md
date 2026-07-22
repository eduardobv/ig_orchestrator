# Patch v1.26.5 - Control de cuentas y ajustes de GUI

## Objetivo

Completar la recuperacion de cuentas nuevas y hacer que la GUI permita operar
con seguridad sobre el catalogo y sobre un lote que ya esta en ejecucion.

## Alcance

* Releer desde SQLite la fecha global y los parametros de renombrado de todas
  las cuentas nuevas antes de ejecutar `Renombrar`.
* Mostrar `Lote actual` en el orden real de procesamiento al iniciar o reanudar.
* Mantener la seleccion durante los refrescos periodicos.
* Permitir marcar una cuenta pendiente o en proceso como fallida, dejando sus
  URLs no terminales en `FAILED_FINAL` con trazabilidad.
* Agregar al catalogo el menu contextual `Abrir` / `Delete`; `Delete` usa baja
  logica `DISABLED` y no elimina filas de SQLite.
* Convertir `path` de cuentas nuevas en un combobox editable alimentado por los
  valores distintos de `account_history.field1`.
* Ocultar los botones `Subir`, `Bajar` y `Duplicar` sin retirar sus metodos.
* Ajustar la ventana a la mitad izquierda de una pantalla 1920x1080, compactar
  columnas y agregar scrollbars finos a lote y estado.
* Incluir pruebas y documentacion de los cambios.
