# Patch v1.26.11 - Distribucion vertical del GUI

## Objetivo

Reorganizar la zona de trabajo para dar mas espacio horizontal al editor y a
la tabla del lote, mantener las acciones principales siempre visibles y
agilizar la seleccion de cuentas del catalogo.

## Cambios

* El catalogo permanece a la izquierda. A su derecha, el `Editor` ocupa la
  parte superior y `Cuentas del lote actual` queda debajo, inmediatamente antes
  del texto de estado.
* Las acciones del editor forman una columna a la izquierda con este orden:
  `Agregar/Actualizar`, `Pegar/Agregar`, `Pegar`, separador, `Normalizar` y
  `Limpiar editor`.
* `URLs`, `Cuentas del lote actual` y el texto de estado muestran un scrollbar
  vertical permanente y visible.
* Un click izquierdo de seleccion en el catalogo copia el username al editor.
  El doble click conserva la apertura del perfil y el menu contextual mantiene
  sus acciones.
* El checkbox `Download stories` pasa a mostrarse como `Stories`.

## Persistencia

No hay cambios de esquema ni de datos. El patch modifica exclusivamente la
presentacion y los eventos del GUI.

## Pruebas

Se cubren el cargado del username seleccionado, la version del paquete y las
regresiones de los servicios de GUI.
