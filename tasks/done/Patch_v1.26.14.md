# Patch v1.26.14 - Editor: checkboxes juntos y foco al final de URLs

## Objetivo

Mejorar la UX del editor: flags de cuenta agrupados y caret al final del
listado de URLs tras pegar o normalizar.

## Cambios

* `Stories` y `New account` comparten un frame horizontal (ya no en extremos
  de columnas).
* Checkboxes clasicos de Tk para que el click en el texto del label conmute.
* Tras `Pegar` y `Normalizar`: `mark_set(INSERT, END)`, `see(END)` y
  `focus_set` en el textarea de URLs.
* `Pegar/Agregar` sigue limpiando el editor tras el upsert (flujo de alta).

## Pruebas

* Unitarias de foco al final en pegar y normalizar.
* Suite GUI services + package smoke + suite completa.
