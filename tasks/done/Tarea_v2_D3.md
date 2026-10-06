# T2.D3 — Importador de catálogo v1 → v2

## Objetivo

Copiar solo `account_history` al esquema GUI, conservando ids y partiendo
`field1` en `catalog_folders`.

## Hecho

* `split_destination_path`: `G:\4K Stogram\00.MODELS-A\Lidiia-Filippova` →
  raíz `G:\4K Stogram`, carpeta `00.MODELS-A`, carpeta cuenta
  `Lidiia-Filippova` (el username es la hoja, no se guarda como carpeta).
* `import_catalog_from_v1` es idempotente, no escribe en el SQLite v1 y no
  crea lotes ni URLs.

## Fuera de alcance

* Repositorios v2 / adaptadores (T2.D4).
* Diálogo Lotes / ejecuciones.
