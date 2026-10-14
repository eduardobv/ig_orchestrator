# feat-uc2-13 — Mover cuentas: sugerencias, búsqueda, nueva carpeta y movimiento múltiple (v3.13.0)

Feat incremental de la serie v3 pedido tras probar «Mover a otra carpeta…» (catálogo, UC2).

## Problema

- Encontrar a mano la carpeta `Modelo-Deleted` en un árbol grande era lento.
- Al hacer clic derecho sobre una de varias cuentas seleccionadas se perdía la selección: solo se movía una.
- El selector de carpeta destino no permitía crear una carpeta nueva.

## Qué se hizo

- **Sugerencias inversas (hasta 3)** en el selector (`library/folder_suggestions.py`): desde `X-Model` → `X-Model-Deleted`, `X-Model-Inactive` y la carpeta de eliminadas; desde `X-Model-Deleted` → `X-Model`, `X-Model-Inactive` (y dónde estaba antes); desde `X-Model-Inactive` → `X-Model`, `X-Model-Deleted`. Si la hermana no existe se ofrece **crearla** (con confirmación). Un clic en una sugerencia la elige.
- **Búsqueda por nombre** dentro del selector: escribe y el árbol salta a la carpeta (expande y selecciona); Enter/flechas pasan a la siguiente coincidencia.
- **Nueva carpeta aquí…** en el mismo selector: crea la carpeta en el momento (operación de disco registrada, se puede deshacer) y la selecciona.
- **Mover varias cuentas:** el clic derecho conserva la selección múltiple y el menú dice «Mover las N cuentas a otra carpeta…»; un solo plan y un solo grupo deshacible.
- El árbol sigue mostrando todas las carpetas, también las archivadas.

## No incluido

- Sugerencias para mover **carpetas** (solo cuentas); aprender destinos usados con frecuencia; más de 3 sugerencias.

## Pruebas

`tests/library/test_folder_suggestions.py` (inversas, crear faltante, destino previo, multiselección, búsqueda) y comprobación manual con copia de la base: selección múltiple conservada tras clic derecho y selector con sugerencias y búsqueda.
