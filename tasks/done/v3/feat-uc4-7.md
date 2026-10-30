# feat-uc4-7 · inst_sync: replicar el código en otra instancia (v4.18.0)

## Objetivo
Dejar de copiar `src` a mano a `inst1` y no olvidar pasos (dependencias, SQL, ajustes).

## Resultado de la implementación
* `inst_sync/sync.py` + `sincronizar.bat`: espejo de `src`, `tools`, `inst_sync`, `pyproject.toml`, `requirements.txt` desde la ruta de `origen.txt`; copia lo cambiado, borra lo eliminado, copia de seguridad de `src` (3), `pip install -r requirements.txt` si cambió o falta `cryptg`, `sql/*.sql` una vez (con copia de la base), migraciones al abrir la base, y muestra las entradas nuevas de `CAMBIOS.md`.
* Protegido: `.env`, `data`, `logs`, `reports`, `config`, `.venv`, `*.session*`, `origen.txt`, `estado.json`, `bkp`, `sincronizar.bat`.
* `--simular`, `--si`. Tests: `tests/inst_sync/test_inst_sync_script.py`.

## Decisiones / no hecho
* Se ejecuta **desde la instancia** (tira del PC principal) para usar su Python y su `.venv`.
* No hay modal en la GUI: la lista de pasos manuales vive en `CAMBIOS.md`.
* El lanzador `.bat` no se sobrescribe (no se cambia un `.bat` en ejecución).
* No detecta si hay un batch en marcha: pregunta.
* No probado en `inst1` real ni con `pip` por red.
