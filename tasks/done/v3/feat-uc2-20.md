# feat-uc2-20 — Buscar por Owner ID (v3.20.0)

## Objetivo
Localizar en el catálogo una cuenta a partir del Owner ID que muestra la página de Instagram, buscando entre todas las cuentas (visibles, archivadas y eliminadas).

## Qué se hizo
- Se reutiliza el cuadro de filtro del catálogo: si el texto es solo dígitos (≥5, con o sin comillas) se busca por Owner ID exacto.
- `AccountCatalogService.find_entries_by_owner_id` consulta todo `account_history` (incluye ARCHIVED y DELETED); el panel sustituye la lista filtrada por las coincidencias, abre/selecciona la carpeta en el árbol y avisa en la barra de estado.
- Al pegar con una única coincidencia, el editor se vincula a ese username; los dígitos nunca se convierten en username.
- Pruebas: `tests/gui/test_catalog_owner_search.py`.

## Qué no
- Sin coincidencia exacta no se muestra aviso ni se buscan IDs parciales (el texto se trata como filtro por username).
- Un username solo numérico de ≥5 dígitos se interpreta como Owner ID si coincide con alguno; si no coincide, se busca como username.
- No hay modal aparte.

## Resultado de la implementación
Hecho. Sin probar con la GUI abierta (el refresco de lista/árbol solo se verificó por importación; la lógica de búsqueda y de pegado tiene pruebas).

Suite completa: 583 passed.
