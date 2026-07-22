# Patch v1.26.6 - Estado de Treeview durante la ejecucion

## Problema

Al reanudar o ejecutar un batch, la GUI intentaba habilitar `Lote actual` con
`Treeview.configure(state="normal")`. `ttk.Treeview` no expone la opcion Tcl
`-state`, por lo que Tkinter lanzaba `TclError` antes de iniciar el subproceso.

## Solucion

* Usar la API de estados ttk: `Treeview.state(("!disabled",))`.
* Mantener habilitados la seleccion del lote y el boton `Eliminar` mientras se
  procesa un batch.
* Agregar una prueba de regresion que verifica la API usada para habilitar y
  deshabilitar widgets ttk.
