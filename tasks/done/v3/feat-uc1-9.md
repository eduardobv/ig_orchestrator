# feat-uc1-9 — Renombrado integrado (port de `sc2 newRename`)

| | |
|---|---|
| **Dificultad** | 9 / 12 |
| **Cubre** | UC1 (la parte de `sc2`), UC4 (renombrar desde cualquier carpeta), base de UC5 y UC6 |
| **Riesgo** | Alto: reimplementa el algoritmo que **renombra y mueve ficheros de la biblioteca**. Mitigado con paridad contra `sc2`, vista previa y motor *legacy* de reserva |
| **Dependencias** | `feat-uc1-3` (rutas/`ownerId` en `bdapp`). Recomendado: `feat-uc2-4` (movimiento seguro) |
| **Estimación** | 8–10 días |

## Objetivo

Ejecutar el renombrado **dentro de la app**, como módulo propio (`renaming/`), con el **mismo resultado** que `sc2 --newRename` pero:
sin subproceso, sin rutas fijas a `D:\Archivos\Scripts\...`, leyendo cuentas/rutas de `bdapp` (no de `accounts_lite`), devolviendo resultados estructurados,
y pudiendo trabajar sobre **cualquier carpeta de origen** (p. ej. directamente la carpeta de intercambio).

## Valor que entrega por sí solo

- Funciona igual en `pc1` e `inst1` sin copiar scripts ni depender de `D:\Archivos\Scripts\IG\ManualRenameFiles` (`gui/run/process_runner.py:12`).
- **Vista previa** («dry-run») del renombrado: tabla *fichero → nuevo nombre → fecha* por cuenta antes de tocar nada (hoy el diálogo «Mostrar comando» solo enseña la línea de comandos).
- Resultado fiable: contadores por cuenta y errores en BD en lugar de analizar `stdout` y «carpetas sobrantes».
- Las cuentas nuevas se registran **una sola vez** (en `bdapp`); se acaba la desincronización con `accounts_dir` (sc2 insertaba en lite por su cuenta).
- Modal **«¿Dónde están los ficheros a renombrar?»** (UC4): por defecto `WORKING_FOLDER`; también la carpeta de trabajo o de intercambio de **cualquier instancia registrada** (`instances`, `feat-uc4-2`) o una ruta libre. Se puede renombrar *in situ* en esa carpeta o **moverla antes al workplace de la instancia principal**.
- Autonomía total: el renombrado usa solo `bdapp` (catálogo + `media_index` de `feat-uc1-3`) y el código de la app; **no consulta ni `accounts_lite` ni `accounts_complete` ni ningún script**.

## Estado actual (evidencia)

- La app invoca `python <MANUAL_RENAME_SCRIPT> --newRename --startNowDate … [--new-account …] --no-duplicated --move-renamed` (`build_manual_rename_command`).
- `sc2` rechaza `--manualFolder` en `newRename` y lee `manualFolder`/`consultFoldersBD` de su `config.json` (`config.py:194`).
- Lo que `sc2` hace está descrito paso a paso en `v3-status.md` §4.3.
- `compareProcess` y `renameProcess` no se usan y **no se portan** (decisión en `v3-status.md` §6).

## Diseño

### Módulo nuevo (`src/ig_orchestrator/renaming/`)

```
models.py      # ConsultItem(media_id, taken_at, owner_id, ext, name), ManualFile, Block, RenameItem, RenameJob, AccountResult
consult.py     # ConsultProvider (Protocol)  →  DiskConsultProvider(folder)   [IndexConsultProvider llega en feat-uc5-10]
manual.py      # lectura de la carpeta de descarga: ^\d{10,}\.(jpg|jpeg|mp4)$, duplicados, agrupación por prefijo de 6 dígitos
timeline.py    # port de timeline_builder.py (propagación de user_id, bandas por encima del último consult, interpolación)
service.py     # RenameService.preview(job) / run(job, progress_cb, cancel_event) -> RenameResult
mover.py       # mover/fusionar carpeta procesada a su destino (usa library/fsops si existe; si no, lógica de sc2 portada)
MODULE.md
```

Puntos de diseño:

1. **Paridad primero.** El port conserva el algoritmo, incluido el **orden de llamadas a `random`**. El generador se inyecta (`rng: random.Random`), por defecto `random.Random()`,
   para poder fijar semilla en pruebas.
2. **Entradas.** `RenameJob(source_folder, start_now_date, new_accounts, no_duplicated, move_renamed, destination="LIBRARY")`.
3. **Resolución de cuenta** (sustituye a `AccountsDatabase.get_account` de sc2): por username (sin mayúsculas) en `catalog_accounts` → ruta = `LIBRARY + rel_path`. Si no existe y viene en `new_accounts`: se crea/actualiza el registro con
   `rel_path = <destination_path>/<username>`, `instagram_user_id`, `start_init_date` y se sigue con el algoritmo de cuenta nueva. Si no existe y no es nueva → omitida con motivo `NOT_REGISTERED` (igual que sc2).
   Mientras `compat.lite.enabled`, el espejo (de `feat-uc2-4`; o un `UPDATE/INSERT` mínimo si aún no existe) mantiene `accounts_lite` para el story inbox.
4. **`user_id`.** Se usa el de los vecinos `consult` (como sc2). *Mejora opcional (`renaming.use_catalog_owner_id`, por defecto ON):* cuando no hay vecino, usar `catalog_accounts.instagram_user_id` en lugar de `unknown`.
5. **Duplicados.** Mismo criterio que sc2 (mismo `media_id` en la misma subcarpeta → `{id}_duplicated.ext`, borrado si `no_duplicated`), con la protección de sc2 (solo nombres que contengan `_duplicated` y dentro del alcance de la ejecución).
   *Opción `renaming.dedupe_across_subfolders`* (por defecto OFF): detectar también entre raíz/`reels`/`story`.
6. **Movimiento** (`move_renamed`): mismas reglas de sc2 (`find_directory_merge_conflicts`, fusión sin sobrescribir, abortar la carpeta si hay conflicto) pero devolviendo el motivo estructurado.
7. **Resultado.** `AccountResult(username, status, renamed, duplicated, deleted_duplicates, moved, errors[])` guardado en tablas
   `rename_runs` / `rename_run_accounts` (resumen, no fila por fichero) para la pantalla de resultados y los informes.
8. **Motor de reserva.** `app_settings['renaming.engine'] = integrated | legacy_sc2`. En `legacy_sc2` el botón sigue lanzando el subproceso actual. Se elimina cuando la paridad haya sido validada en uso real.

### Esquema

```sql
CREATE TABLE IF NOT EXISTS rename_runs (
    id INTEGER PRIMARY KEY, batch_id INTEGER REFERENCES batches(id), queue_id INTEGER,
    engine TEXT NOT NULL, source_folder TEXT NOT NULL, start_now_date TEXT NOT NULL,
    options TEXT, status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE IF NOT EXISTS rename_run_accounts (
    id INTEGER PRIMARY KEY, rename_run_id INTEGER NOT NULL REFERENCES rename_runs(id) ON DELETE CASCADE,
    username TEXT NOT NULL, catalog_account_id INTEGER REFERENCES catalog_accounts(id),
    status TEXT NOT NULL,         -- RENAMED | SKIPPED_NOT_REGISTERED | SKIPPED_ERROR | MOVE_CONFLICT | NO_FILES
    renamed INTEGER DEFAULT 0, duplicated INTEGER DEFAULT 0, moved INTEGER DEFAULT 0, detail TEXT);
```

### UI

- **Renombrar** (`gui/run/rename.py`): abre una modal con *origen de ficheros* (por defecto `WORKING_FOLDER`; botón «Examinar…»; atajo «Carpeta de intercambio»), opciones (*Eliminar duplicados*, *Mover a la biblioteca*) y botón **Vista previa**.
- **Vista previa** (reemplaza «Mostrar comando de renombrado»): árbol cuenta → subcarpeta → ficheros con nombre nuevo y fecha asignada, avisos (`NOT_REGISTERED`, conflictos de movimiento) y totales. El aleatorio de minutos/segundos se **congela con la semilla de la vista previa** para que lo que se ve sea lo que se aplica.
- Barra de progreso y consola con el mismo formato de log; `Cancelar` entre cuentas (nunca a mitad de una cuenta).
- Tras terminar: pestaña **Resultado** (tabla `rename_run_accounts`) con filtro de problemas; la lógica de `decide_rename_completion` se mantiene pero alimentada con datos estructurados (carpetas sin mover = resultado `MOVE_CONFLICT`).
- Se mantiene la finalización de lote/cola (`finish_batch`, `finish_queue_after_rename`).

## Pruebas (este feat es sobre todo de pruebas)

1. **Paridad con `sc2`** (`tests/renaming/test_parity_sc2.py`): carga `ManualRenameFiles` por `importlib` desde su ruta (se omite si no existe) y, para un conjunto de fixtures
   (cuenta nueva, cuenta con bloques por encima del último consult, bloques intercalados, duplicados, subcarpetas `story/reels/highlights`, colisiones de nombre con `(n)`),
   ejecuta ambos motores con `random.seed(N)` y compara el conjunto *(nombre original → nombre final)* y los ficheros resultantes en disco.
2. **Propiedades** (`tests/renaming/test_timeline_properties.py`): las fechas asignadas son monótonas respecto al `media_id`, caen entre sus vecinos y los bloques por encima del último consult quedan ≤ `startNowDate`.
3. Unitarias de `manual.py` (regex, agrupación por prefijo), `consult.py`, `mover.py` (fusión sin sobrescribir, conflicto).
4. `tests/renaming/test_service.py`: cuenta no registrada, cuenta nueva (registro en BD), cancelación, `no_duplicated`, `move_renamed`.
5. `tests/gui/test_rename_dialog.py`: modal, vista previa, motor `legacy_sc2` sigue construyendo el comando actual.
6. **Prueba de aceptación real**: duplicar una carpeta de descargas y renombrarla con ambos motores sobre **copias** de dos cuentas reales; los nombres deben coincidir salvo la parte aleatoria (o coincidir 100 % con semilla).

## Criterios de aceptación

1. Con `renaming.engine = integrated`, el botón Renombrar completa un lote real con el mismo resultado que `sc2` (paridad con semilla en las fixtures; revisión manual en el caso real).
2. No queda ninguna referencia a `MANUAL_RENAME_SCRIPT` en el camino por defecto.
3. La vista previa y el resultado real coinciden.
4. Una cuenta nueva queda registrada en `bdapp` con `rel_path` y en `accounts_lite` (espejo) sin pasos manuales.
5. `inst1` puede renombrar sin tener `ManualRenameFiles` instalado.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (renombrado integrado, ajuste `renaming.engine`), `renaming/MODULE.md`, `gui/run/MODULE.md`, `docs/modularizacion_v2.md`, `tasks/done/`.
**Aviso a futuro:** cuando `legacy_sc2` se retire, actualizar `CLAUDE.md` (secciones POST_PROCESS) y quitar `POST_PROCESS_COMMAND`/`orchestration/post_processing.py` si ya no se usan.

## Decisiones abiertas

- Subcarpeta que existe en la descarga pero **no** en la biblioteca para una cuenta registrada (p. ej. primera `story`): `sc2` la deja sin renombrar (solo la procesa si `flagNew`). Propuesta: tratarla como timeline vacío con
  `start_init_date` de la cuenta, avisando en la vista previa. Requiere confirmación (comportamiento nuevo).
- Ampliar la lectura de `consult` a `.png/.mov/.wmv` (sc1 las indexa, sc2 no): en tus datos no hay ninguno (solo `jpg/jpeg/mp4`), así que se mantiene la paridad y se deja como ajuste futuro.

## Fuera de alcance

Renombrar sin G: (→ `feat-uc5-10`), almacén de procesadas (→ `feat-uc6-11`), `compareProcess`, borrar `sc2`.

## Resultado de la implementación (2026-10-12, v3.9.0)

- Implementado el port completo del algoritmo de `newRename` con paridad verificada contra `sc2` (misma semilla + mismo reloj = mismos nombres; 9 casos), vista previa congelada con semilla, motor seleccionable (`renaming.engine`), historial en `rename_runs`/`rename_run_accounts`, cancelación entre cuentas, origen elegible (carpeta propia, instancias registradas o ruta libre) y escritura inmediata de contadores/índice tras mover.
- **Motor por defecto: integrado**, con la vista previa **siempre** visible (se puede desactivar). El script externo sigue disponible como motor `legacy_sc2` hasta que se confirme su uso real.
- Cuentas «registradas» = con ruta en la biblioteca (`catalog_accounts.rel_path`); ya no se consulta `accounts_lite`. Una cuenta nueva que no se llega a mover **no recibe ruta** (queda pendiente; `feat-uc5-10` lo gestionará).
- **Decisión abierta resuelta:** una subcarpeta ausente en la biblioteca no se renombra (paridad); se avisa en la vista previa.
- **No implementado:** pestaña «Resultado» persistente (el resultado se muestra al terminar y queda en `rename_run_accounts`), comparar con `compareProcess`/`renameProcess` (no se portan), referencia desde el índice en vez de disco (→ `feat-uc5-10`).
- Sin probar con tu `G:` real. Primera prueba recomendada: copiar una cuenta pequeña de `10.TEMP` como biblioteca y una descarga de prueba.
