# T2 GUI — editor: botones, pegar Username y menú contextual

## Hecho

* `Agregar/Actualizar` a la altura de Username (posición que tenía
  `Pegar/Agregar`).
* `Pegar/Agregar`, `Pegar`, `Normalizar` y `Limpiar editor` apilados a la
  altura de URLs.
* Icono compacto `clipboard_black.png` a la derecha del combobox Username:
  pega la primera línea no vacía del portapapeles.
* ❌ junto a ese icono, mismo `width=3` que en catálogo y en cuentas del
  lote: limpia solo Username.
* Click derecho (y Shift+F10) en Lote, buscador del catálogo, Username,
  URLs y buscador del lote: Cortar / Copiar / Pegar / Eliminar /
  Seleccionar todo, con i18n. Se usa menú propio (no el nativo de Windows)
  para que sv-ttk y `tk.Text` se comporten igual y el idioma coincida.

## Fuera de alcance

* Diálogo Lotes / ejecuciones.
* Cambiar el orden de procesamiento del lote.
