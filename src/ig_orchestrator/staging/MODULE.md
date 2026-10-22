# Módulo: `staging`

Almacén local de cuentas renombradas y volcado a la biblioteca. Sin Tk.

- `service.py` — `StagingService(conn)`:
  - `staging_root()` / `staging_path(rel)` (`app_settings['staging.root']`).
  - `record(...)` (lo llama el renombrador al dejar una cuenta en el almacén) → `staged_accounts`.
  - `plan(ids=None)` → `DumpItem` por cuenta: `NUEVA` / `FUSIONAR` / `CONFLICTO` / `FALTA`, ficheros, bytes.
  - `dump(ids=None, progress=, cancel_event=)` → `DumpResult` (registrado en `dump_runs`). Requiere la biblioteca disponible.
  - `merge_verified` / `move_file_verified`: entre unidades copia → comprueba tamaño → `os.replace` → borra el origen; nunca sobrescribe.
  - `summary()`, `forget_dumped()`.

Reglas: el destino se recalcula desde `catalog_accounts.rel_path` en el momento del volcado; un conflicto no se toca (estado `CONFLICT`); un volcado interrumpido (`DUMPING`) se reanuda con otra llamada.
No incluido: indicador permanente en la barra de estado, `staging.layout = flat`, borrado desde el panel de lo almacenado.

Tests: `tests/staging/test_staging.py`.
