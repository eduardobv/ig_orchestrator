# Patch v1.26.12 - Estados, favoritos y agrupacion del catalogo

## Objetivo

Permitir clasificar visualmente las cuentas del catalogo como favoritas,
inactivas o desactivadas, agrupar las cuentas activas por su ruta historica y
reactivar automaticamente las inactivas cuando participan en una ejecucion
real.

## Cambios

* El menu contextual incorpora `Inactivo`, `Favorito` y `Quitar favorito`.
* `Delete` conserva la baja logica, pero la cuenta permanece visible al final
  del catalogo.
* El catalogo presenta, en este orden, favoritas, activas con `field1`, activas
  sin ruta, inactivas y desactivadas. Las secciones con ruta se agrupan por
  `field1` y cada grupo ordena sus usernames alfabeticamente sin distinguir
  mayusculas.
* Las favoritas se muestran en verde, las inactivas en amarillo y las
  desactivadas en rojo.
* Una cuenta inactiva vuelve a `ENABLED` cuando comienza a procesarse dentro de
  un lote real. Los dry-run no cambian el catalogo.

## Persistencia

* `account_history.status` admite el nuevo valor `INACTIVE`.
* `account_history.is_favorite` guarda la marca independiente de favorito como
  entero booleano, con valor inicial `0`.
* La migracion agrega la columna de forma compatible y conserva todas las filas
  existentes.

## Pruebas

Se cubren la migracion, el orden completo del catalogo, los colores, el alta y
baja de favoritos y la reactivacion durante una ejecucion real sin afectar los
dry-run.
