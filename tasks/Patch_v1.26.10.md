# Patch v1.26.10 - Flujo de alta y dimensiones del GUI

## Objetivo

Evitar que una cuenta seleccionada se reemplace accidentalmente al preparar
otra, agilizar el pegado y alta de URLs, y mejorar el aprovechamiento horizontal
de la ventana.

## Cambios

* `Limpiar editor` elimina también la selección visible de `Lote actual`, por lo
  que la siguiente acción agrega una cuenta nueva.
* `Pegar/Agregar`, situado encima de `Pegar`, copia el portapapeles al editor y
  ejecuta `Agregar / Actualizar`.
* La tabla usa el orden `Username`, `URLs`, `Estado`, `Stories`, `Start date`.
* `Username` y el panel del catálogo toman como referencia la cuenta más larga
  del catálogo. Las demás columnas se ajustan a sus máximos visibles:
  cuatro dígitos para URLs, `Completada 9999/9999` para Estado, el contenido
  sí/no de Stories y diez caracteres para Start date, conservando visibles los
  encabezados.
* Al terminar el subproceso de un lote se reproduce el sonido de finalización
  nativo de Windows; en otras plataformas se usa la campana de Tk.

## Persistencia

No hay cambios de esquema ni de datos. El patch modifica únicamente estado y
presentación del GUI.

## Pruebas

Se cubren el orden y muestras de ancho de las columnas, el ancho del catálogo,
la deselección al limpiar, el flujo combinado de pegar/agregar y el aviso sonoro.
