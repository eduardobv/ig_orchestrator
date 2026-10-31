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

## Ajuste v4.18.1 · dos partes
* Motivo: la carpeta del código del PC principal no se comparte; la ruta de red conocida es la de la instancia. Además, con `origen.txt` apuntando a la propia instancia el script comparaba la carpeta consigo misma (0 ficheros).
* Parte 1 `empujar.bat` (`sync.py --empujar`, ruta en `destino.txt`): en el PC, copia/borra por red, copia de seguridad de `src`, imprime las entradas nuevas de `CAMBIOS.md`, guarda `version` en el `estado.json` de la instancia y avisa si hace falta la parte 2 (requirements distinto o SQL pendientes). Sin cambios dice «Instancia sincronizada con el PC». Se niega si destino y origen son la misma carpeta.
* Parte 2 `sincronizar.bat` (local): `pip` si cambió `requirements.txt` o falta `cryptg`, SQL una vez con copia de la base, migraciones. Sin origen.
* Los SQL **no** se ejecutan desde el PC: la base usa WAL y no es fiable por red. `sincronizar.bat` ahora también se copia (ya no se protege); `empujar.bat`, `destino.txt` y `origen.txt` sí quedan protegidos. `origen.txt` queda en desuso.
* Probado: tests (17) y simulación real `--empujar --simular` contra la ruta de red de INST1 (v4.16.0, 26 ficheros a copiar). No probada la copia real ni la parte 2 en INST1.
