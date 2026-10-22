# feat-gui-27 · Ajustes de tamaño y textos de la GUI (v4.1.0)

## Objetivo
Cuatro retoques pedidos juntos: casillas «Deleted»/«Inactive» sin «Ver -», quitar la etiqueta «URLs» del editor, acortar el nombre del lote y estrechar el OwnerId.

## Resultado de la implementación
* Ver `CHANGELOG.md` (v4.1.0). Solo textos y anchos; sin cambios de lógica.
* Nombre del lote: 38 caracteres (10 más que los 28 originales; en v3.25 se había subido a 48). OwnerId: 16 (antes 20).

## No se hizo
* Se interpretó «eliminar el label de URLs y el textbox» como **solo la etiqueta**: el cuadro donde se pegan las URLs sigue siendo necesario.
