# T2.D4 — Repositorios y adaptadores GUI v2

## Objetivo

El motor sigue usando `Account`, `UrlJob` e `InputBatch`. En un SQLite
`user_version = 100` los repositorios existentes despachan a implementaciones
que leen `catalog_*` / `batch_*`.

## Hecho

* `LookupCache` para códigos ↔ ids.
* `GuiCatalogRepository` compatible con `AccountHistoryRepository`.
* Adaptadores de lote, cuenta, URL, run y download.
* Vistas `input_batches`, `accounts`, `url_jobs`, `runs`, colas, para que el
  SQL de la GUI (incluido Lotes) no cambie de comportamiento.

## Fuera de alcance

* Rediseño del diálogo Lotes.
