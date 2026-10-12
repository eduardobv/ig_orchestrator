# Módulo: `renaming`

Renombrado integrado de descargas (port de `ManualRenameFiles --newRename`). Sin Tk.

## Archivos

- `files.py` — expresiones regulares y listados (`os.listdir`, mismo orden que `sc2`), `ConsultItem`, `group_manual_files_by_prefix`.
- `timeline.py` — asignación de fechas e id de propietario (`TimelineContext(rng, now, forced_user_id, flag_new)`). **El orden de llamadas al generador aleatorio es el de `sc2`**.
- `planner.py` — `process_folder_tree` (recursivo por subcarpetas), `DiskConsultProvider` (referencia = ficheros de la carpeta de la cuenta en la biblioteca), `DryOps` / `RealOps`.
- `mover.py` — `move_renamed_folder` / `preview_move`: destino = carpeta padre de la cuenta en la biblioteca + nombre de la carpeta descargada; fusión sin sobrescribir (un choque cancela esa cuenta).
- `service.py` — `RenameService(conn).preview(job, seed=, now=)` y `.run(preview)`; guarda `rename_runs` / `rename_run_accounts`; registra cuentas nuevas en la app (y en lite si el espejo está activo); refresca contadores con el escáner (`ACCOUNT`).
- `settings.py` — `renaming.engine` (`integrated` | `legacy_sc2`), `renaming.preview`, `compat.lite.enabled`.

## Reglas heredadas de `sc2`

- Ficheros descargados `^\d{10,}\.(jpg|jpeg|mp4)$`; si el id ya está en la carpeta de referencia **de la misma subcarpeta** → `{id}_duplicated.ext` (se borra con *Eliminar duplicados*, solo nombres con `_duplicated` dentro de la carpeta procesada).
- Grupos por los 6 primeros dígitos; fechas por interpolación entre vecinos de la biblioteca; por encima del último fichero, entre su fecha y `startNowDate`; nombre `{fecha} {id}_{owner}_manual.ext` (con `(n)` si choca).
- Cuenta nueva: fechas repartidas entre su fecha de inicio y `startNowDate`; el id de propietario viene del lote.
- Una subcarpeta que no existe en la biblioteca no se renombra (aviso) — igual que `sc2`.

## Tests

`tests/renaming/test_parity_sc2.py` (se omite si `sc2` no está instalado), `test_service.py`, `test_settings_and_gui.py`.
