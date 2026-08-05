# Patch v1.26.13 - Catalogo: highlight en lote, Activar, foco y limpiar filtro

## Objetivo

Mejorar la UX del catalogo al armar lotes: ver que cuentas ya estan en el
borrador, reactivar cuentas desactivadas, no perder la posicion al usar el
menu contextual y limpiar el buscador con un boton.

## Cambios

* Cuentas presentes en "Cuentas del lote actual" se resaltan en amarillo
  temporal (`#f5c08c`), con prioridad por debajo de `DISABLED`.
* Menu contextual `Activar` devuelve cuentas `DISABLED`/`INACTIVE` a
  `ENABLED` via `AccountCatalogService.enable`.
* `_refresh_catalog` conserva username seleccionado y `yview` tras repintar.
* Boton pequeno `❌` junto al filtro limpia el texto de busqueda.
* Al agregar/quitar cuentas del lote se refresca el highlight del catalogo.

## Pruebas

* Unitarias de colores y `enable`.
* Suite GUI services + package smoke + suite completa.
