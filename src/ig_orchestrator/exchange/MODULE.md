# Módulo: `exchange`

Trae carpetas de cuenta que otra instancia dejó en una carpeta compartida hacia `WORKING_FOLDER`. Sin dependencias de Tk.

## Archivos

- `inbox_scan.py` — `scan_exchange(root, stable_seconds=)` → `ExchangeFolder` (ficheros, bytes, `newest_mtime`, `is_stable`); ignora `*.part`; `long_path()` para rutas largas.
- `pull.py` — `plan_pull(folders, dest_root, policy, keep_source=)` y `execute_pull(plan, progress=, cancel_event=)`.
  Por fichero: `COPY`, `SKIP_IDENTICAL` (mismo nombre y tamaño) o `COPY_SUFFIXED` (`_1`, `_2`). Copia a `*.part`, verifica tamaño, `os.replace`, borra origen si es «mover».
- `compare.py` — `compare_with_batch` (recibidas/faltantes/sobrantes, sin mayúsculas), `list_recent_batches`, `probe_path` (existe/escritura/espacio libre con timeout).

## Reglas

- Cancelar deja el origen intacto para lo no procesado y sin `.part` en destino; los `.part` huérfanos se limpian en el siguiente intento.
- Una carpeta «en uso» = algún fichero modificado hace menos de `DOWNLOAD_STABLE_SECONDS × 3`.
- El registro de instancias vive en `db/instances_repository.py` (tabla `instances`); UI en `gui/settings/instances_tab.py` y `gui/exchange/pull_dialog.py`.

## Tests

`tests/exchange/test_pull.py`, `tests/gui/test_pull_dialog.py`.
