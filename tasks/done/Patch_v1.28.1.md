# v1.28.1 - Patch GUI: checkbox Update y registro de catálogo

## Objetivo

Permitir registrar en el orquestador el `ownerId` y `path` de cuentas que ya
existen en la BBDD maestra, sin marcarlas como cuenta nueva del renombrador.

La información no debe perderse en el flujo:

`Registrar lote` → `Exportar` → `Ejecutado en otra instancia` → `Renombrar`

## Detalle

### Checkbox Update

* Junto a `New account` en el editor.
* Exclusión mutua con `New account`.
* Campos: `ownerId *` y `path *` (sin `startInitDate`).
* Frame: “Datos de catálogo (Update)”.

### Persistencia

* `AccountDraft.is_catalog_update`.
* Al Agregar/Actualizar y al Registrar/Importar:
  * `account_history.user_ig_id` + `field1` vía `update_identity_and_path`.
  * No pisa `field2` (startInitDate).
* En `accounts`: `is_new_account=0`, `rename_owner_id` y
  `rename_destination_path` rellenados; `rename_start_init_date` null.
* Carga: se infiere Update si hay metadata y no es new account.
* Export JSON incluye `is_catalog_update` (import también lo infiere por
  compatibilidad).
* Renombrador: solo `is_new_account` genera `--new-account`.

## Archivos principales

* `src/ig_orchestrator/gui/batch_draft.py`
* `src/ig_orchestrator/gui/batch_draft_service.py`
* `src/ig_orchestrator/gui/batch_resume_service.py`
* `src/ig_orchestrator/gui/batch_transfer_service.py`
* `src/ig_orchestrator/gui/app.py`
* `src/ig_orchestrator/db/account_history_repository.py`
* `tests/test_gui_services.py`
* Docs y CHANGELOG

## Pruebas

* `python -m pytest -q tests/test_gui_services.py -k "catalog_update or rename_parameters or export_import"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`
