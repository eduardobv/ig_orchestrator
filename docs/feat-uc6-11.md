# feat-uc6-11 — Almacén de procesadas y «volcado» a G:

| | |
|---|---|
| **Dificultad** | 11 / 12 |
| **Cubre** | UC6 (completo) · proceso manual M7 |
| **Riesgo** | Medio-alto: pasa a haber **datos que existen solo en el almacén** hasta que se vuelcan; hay que garantizar que no se pierdan ni se dupliquen |
| **Dependencias** | `feat-uc5-10` (renombrar sin G:), `feat-uc1-9` y `feat-uc2-4` (movimiento seguro con diario) |
| **Estimación** | 6–8 días |

## Objetivo

Separar **renombrar** de **entregar a la biblioteca**:

1. Tras renombrar, las carpetas procesadas se dejan en un **almacén (`STAGING`)** que tú eliges (modal u opción).
2. Más adelante, con G: conectada, una opción de **volcado** traslada lo almacenado a su sitio en `G:\4K Stogram` (fusionando con lo existente, sin sobrescribir).

Así solo conectas G: para volcar.

## Valor que entrega por sí solo

- G: puede estar apagada durante semanas sin bloquear el trabajo diario.
- El almacén puede estar en un disco rápido y local; el volcado es una operación única, planificada y con vista previa.
- Visibilidad: panel «Pendiente de volcar» con cuentas, ficheros, MB y la ruta de destino ya calculada.
- Tolerante a cortes: el volcado se puede cancelar y reanudar (diario por cuenta).

## Estado actual (evidencia)

- `path_roots` ya contiene `FINAL_BASE` vacío: había intención de una raíz final separada, nunca implementada.
- `sc2 --move-renamed` mueve directamente a la biblioteca (`main.py:129`); no existe el concepto de almacén.
- La lógica de fusión sin sobrescribir ya existe (sc2 y `feat-uc1-9`) y el motor de operaciones con diario llega con `feat-uc2-4`.
- `feat-uc5-10` deja las carpetas renombradas en la carpeta de trabajo como «pendientes de mover»; este feat las generaliza.

## Diseño

### Raíz y ajustes

| Clave / `path_roots` | Significado | Defecto sugerido |
|---|---|---|
| `STAGING` | Almacén local de cuentas ya renombradas | `D:\Archivos\IG\Procesadas` (configurable; ver Q6 de `v3-status.md`) |
| `app_settings['staging.layout']` | `by_target` (réplica de la estructura de la biblioteca) · `flat` (`STAGING\<username>`) | `by_target` |
| `app_settings['staging.after_rename']` | `ASK` · `STAGING` · `LIBRARY` | `ASK` |

`by_target` replica `categoría\grupo\username` para que el volcado sea un `merge` directo y el árbol del almacén sea legible; `flat` es más simple pero necesita consultar `rel_path` del catálogo para saber el destino (se guarda igual).

### Modelo de datos

```sql
CREATE TABLE IF NOT EXISTS staged_accounts (
    id INTEGER PRIMARY KEY,
    catalog_account_id INTEGER NOT NULL REFERENCES catalog_accounts(id),
    staging_rel TEXT NOT NULL,           -- ruta dentro de STAGING
    target_rel  TEXT NOT NULL,           -- ruta destino en LIBRARY (rel_path de la cuenta)
    rename_run_id INTEGER REFERENCES rename_runs(id),
    files INTEGER, bytes INTEGER,
    status TEXT NOT NULL,                -- STAGED | DUMPING | DUMPED | CONFLICT | FAILED
    staged_at TEXT NOT NULL, dumped_at TEXT, error TEXT,
    UNIQUE(catalog_account_id, staging_rel));
CREATE TABLE IF NOT EXISTS dump_runs (
    id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
    accounts INTEGER DEFAULT 0, files INTEGER DEFAULT 0, bytes INTEGER DEFAULT 0, summary TEXT);
```

El `media_index.location` (de `feat-uc5-10`) pasa de `1` a `0` cuando la cuenta se vuelca. `target_rel` usa la ruta relativa de `catalog_accounts.rel_path`, de modo que **cambiar de letra de unidad** no afecta.

### Flujo A — «Renombrar → almacén»

1. En la modal de **Renombrar** (`feat-uc1-9`) aparece **Destino de las procesadas**: *Biblioteca (G:)* · *Almacén* · *Preguntar luego*. Por defecto sigue `staging.after_rename`.
2. Para destino *Almacén* el servicio, en lugar del `move_renamed` a la biblioteca, mueve cada carpeta renombrada a `STAGING\<layout>` (misma lógica de fusión que `feat-uc1-9`, aplicada contra el almacén),
   crea o actualiza `staged_accounts` y deja el índice con `location=1`.
3. El lote pasa a `COMPLETED` igual que hoy: **el lote no espera al volcado**.

### Flujo B — «Volcado» (`Lote → Volcar almacén a G:…`)

1. **Preparación** (sin efectos): comprueba que `LIBRARY` está online, calcula por cuenta `staging_rel → target_rel`, detecta:
   carpeta destino inexistente (se creará con la estructura del catálogo), fusión con carpeta existente, conflictos de ficheros, espacio libre.
2. **Vista previa** (`gui/library/plan_dialog.py`): tabla con cuentas, ficheros, MB, estado (`NUEVA` / `FUSIONAR` / `CONFLICTO`) y casillas para elegir **qué volcar** (todo / por cuenta / por categoría).
3. **Ejecución** por cuenta con el motor de `feat-uc2-4` (`MERGE_DIR`): copia verificada (tamaño) → confirma → elimina del almacén **solo** lo que ya está verificado en destino.
   Entre dos cuentas se puede cancelar; una cuenta a medias se reanuda por fichero.
4. **Después**: `staged_accounts.status = DUMPED`, `catalog_accounts` (`last_media_at`, contadores) actualizados con los datos del propio volcado (sin reescanear), `media_index.location = 0`, y el espejo `accounts_lite` actualizado para cuentas nuevas.
5. **Informe** de volcado (`dump_runs`) con resumen y problemas.

Ambos flujos usan el diario de operaciones: una caída entre «copiado» y «borrado del almacén» se resuelve en el siguiente arranque comparando origen y destino (nunca se borra nada sin comprobar que existe en destino con el mismo tamaño).

### UI

- Pestaña/diálogo **«Pendiente de volcar»** (`gui/library/staging_panel.py`): árbol del almacén con contadores y estado; acciones *Volcar seleccionadas*, *Volcar todo*, *Abrir carpeta*, *Quitar del almacén* (solo `DUMPED`).
- Indicador discreto en la barra de estado: `Almacén: 14 cuentas / 3,2 GB pendientes · G: desconectada`.
- Al detectar G: conectada (comprobación al abrir el panel, no por sondeo continuo) se ofrece «Hay N cuentas pendientes: ¿volcar ahora?».

## Casos borde

- **Más descargas de una cuenta ya almacenada**: nuevo renombrado sobre el mismo almacén → `merge` dentro del almacén; el índice ya refleja lo almacenado, por lo que las fechas son coherentes.
- **Cuenta renombrada o movida en el catálogo mientras está en el almacén** (`feat-problem1-7` / `feat-uc2-4`): `target_rel` se recalcula desde `catalog_accounts.rel_path` en el momento del volcado.
- **Cuenta marcada `DELETED`** con ficheros en el almacén: el volcado la lleva a su carpeta de eliminadas.
- **Conflicto de ficheros** en destino: no se sobrescribe; la cuenta pasa a `CONFLICT` y se muestra el detalle (misma regla que `sc2`: se aborta esa carpeta).
- **Disco del almacén lleno**: el renombrado con destino almacén comprueba el espacio previamente.
- **El usuario borra manualmente algo del almacén**: el panel hace un `scan` local (barato) al abrirse y marca la divergencia; el índice se corrige.
- **G: conectada con otra letra**: las filas usan `rel_path` y la raíz `LIBRARY` es editable (un cambio de letra es una edición, no una migración).

## Pruebas

- `tests/staging/test_stage_after_rename.py`: renombrado → almacén (`by_target` y `flat`), fusión dentro del almacén, índice `location=1`.
- `tests/staging/test_dump.py`: destino nuevo, fusión, conflicto, cancelación a mitad, reanudación, fallo entre copiar y borrar, espacio insuficiente.
- `tests/staging/test_dump_moves_index.py`: `location` 1→0, contadores del catálogo, espejo lite.
- `tests/gui/test_staging_panel.py`: estados y acciones.
- Prueba real: renombrar un lote hacia el almacén **sin G:**, conectar G:, volcar y ejecutar la auditoría de `feat-uc3-1` (0 discrepancias nuevas).

## Criterios de aceptación

1. Un lote completo se descarga, renombra y almacena con G: apagada.
2. Conectar G: y volcar deja la biblioteca idéntica a la que habría dejado el flujo antiguo (mismos nombres y carpetas) y el almacén vacío.
3. Cortar la corriente a mitad del volcado y reabrir permite reanudar sin duplicar ni perder ficheros.
4. La auditoría posterior no encuentra discrepancias nuevas.
5. El flujo directo a biblioteca (`LIBRARY`) sigue funcionando con G: conectada.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (nuevo flujo diario), `CLAUDE.md` (secciones «Rutas de salida» y «Flujo de ejecución»), `staging/MODULE.md`, `docs/modularizacion_v2.md`, `tasks/done/`.

## Fuera de alcance

Volcado automático al detectar la unidad, deduplicación avanzada de contenido por hash, sincronización entre almacenes de dos equipos.
