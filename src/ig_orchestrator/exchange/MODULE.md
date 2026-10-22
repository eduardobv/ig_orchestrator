# Módulo: `exchange`

Trae carpetas de cuenta que otra instancia dejó en una carpeta compartida hacia `WORKING_FOLDER`. Sin dependencias de Tk.

## Archivos

- `inbox_scan.py` — `scan_exchange(root, stable_seconds=)` → `ExchangeFolder` (ficheros, bytes, `newest_mtime`, `is_stable`); ignora `*.part`; `long_path()` para rutas largas.
- `pull.py` — `plan_pull(folders, dest_root, policy, keep_source=)` y `execute_pull(plan, progress=, cancel_event=)`.
  Por fichero: `COPY`, `SKIP_IDENTICAL` (mismo nombre y tamaño) o `COPY_SUFFIXED` (`_1`, `_2`). Copia a `*.part`, verifica tamaño, `os.replace`, borra origen si es «mover».
- `compare.py` — `compare_with_batch` (recibidas/faltantes/sobrantes, sin mayúsculas), `list_recent_batches`, `probe_path` (existe/escritura/espacio libre con timeout).

## Paquetes (feat 6)

- `manifest.py` — formato `ig_orchestrator.batch_result` `format_version "1"`, `min_reader_version "3.6.0"`. `build_manifest` (lotes, cuentas, URLs con estado/error real, ficheros con tamaño), `write_manifest` (tmp + `os.replace`, **último** en escribirse), `read_package`/`scan_packages` (`problem` explica por qué no es importable: incompleto, versión…).
- `publish.py` — `publish_batches(conn, batch_ids, working, exchange_root, instance=, mode=MOVE|COPY)`: copia verificada a `<paquete>.partial`, manifiesto, **renombra** la carpeta, y solo entonces (MOVE) borra el origen. Registra `exchange_publications`. `unpublished_batches` evita publicar dos veces. Ajustes: `exchange.auto_publish`, `exchange.publish_mode` (la auto-publicación exige instancia local `WORKER`).
- `result_import.py` — `import_package`: valida versión, verifica tamaños de `files[]`, copia a `WORKING` con `plan_pull/execute_pull`, crea o completa el lote (adjunta si existe como DRAFT/IMPORTED; si existe terminado crea `<lote>_<instancia>`), resuelve cuentas por `instagram_user_id` y luego username, crea `batch_urls` con los estados reales y **un** `batch_runs` («Imported from …»). Idempotente por `package_id` (`exchange_imports`, `imported.json`).

## Reglas

- Cancelar deja el origen intacto para lo no procesado y sin `.part` en destino; los `.part` huérfanos se limpian en el siguiente intento.
- Una carpeta «en uso» = algún fichero modificado hace menos de `DOWNLOAD_STABLE_SECONDS × 3`.
- El registro de instancias vive en `db/instances_repository.py` (tabla `instances`); UI en `gui/settings/instances_tab.py` y `gui/exchange/pull_dialog.py`.

## Tests

`tests/exchange/test_pull.py`, `tests/gui/test_pull_dialog.py`.
