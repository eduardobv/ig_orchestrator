# feat-uc1-3 — Unificar catálogo: importar `accounts_complete` (y lite) en `bdapp`

> **Actualizado 2026-10-11 con tus decisiones:** `accounts_complete.sqlite` es la fuente principal (su algoritmo de carga es el estructurado; `accounts_lite` es solo su versión ligera);
> este feat incluye ahora **también el índice de ficheros para renombrar** (`media_index`) y permite **reestructurar `bdapp`** porque solo importa el catálogo.

| | |
|---|---|
| **Dificultad** | 3 / 12 |
| **Cubre** | UC1 (todo en `bdapp`), base de UC2/UC3/UC5 · elimina la dependencia del story inbox con `accounts_lite` |
| **Riesgo** | Medio: reestructura el catálogo de `bdapp`; importación idempotente y con *dry-run*; no escribe en `bdsc1` ni en disco |
| **Dependencias** | Ninguna dura. Recomendado tras `feat-uc3-1` (para conocer las discrepancias antes de importar) |
| **Estimación** | 5–6 días (incluye el índice `media_index`) |

## Objetivo

Que `bdapp` sea la **única** base de datos y conozca **toda la biblioteca** (las ~1 231 carpetas de cuenta, no solo las 334 gestionadas) con ruta,
`ownerId`, contadores, fecha del último contenido **y el índice de ficheros que necesita el renombrado**, de forma que el catálogo sea un reflejo del disco y ya no haga
falta consultar `accounts_lite` ni `accounts_complete` para nada (salvo, una sola vez, para importarlos).

## Paso 0 (manual, una vez): refrescar `accounts_complete`

`accounts_complete` está desactualizada (último `--update`: 2026-07-18; 116 rutas distintas respecto a lite). Antes de importar, con G: conectada:

1. `python generatedirmap.py --lite` (13–55 s) → actualiza rutas.
2. `python generatedirmap.py --update` (2–32 s según cambios) → reconstruye en complete las cuentas movidas/nuevas y su tabla `media`.
3. (Opcional, más lento) `python generatedirmap.py --complete` (~8 min) si prefieres una carga completa limpia.

El importador comprueba la antigüedad y avisa («complete: 18/07, lite: 09/10 → ejecuta el paso 0»). Es la **última vez** que se usa `sc1`.

## Estrategia de base de datos única (decisión)

Como solo importa el catálogo (lotes, colas, URLs, ejecuciones no son relevantes), hay dos caminos; **recomendado B**:

| | A · Aditiva | **B · Catálogo reconstruido (recomendada)** |
|---|---|---|
| Qué hace | Añade columnas/tablas a las existentes | Crea el catálogo con el modelo definitivo (nodos, cuentas, historial de nombres, índice) y migra solo los datos del catálogo actual (favoritos, estados, ids, fechas, colores/ajustes) |
| Lotes/URLs/runs | se conservan | se conservan si cuesta poco; **pueden descartarse** (se archiva el fichero anterior en `data/old/`) |
| Riesgo | bajo | medio, mitigado con copia previa y *dry-run* |
| Ventaja | sin tocar nada existente | modelo limpio sin las vistas de compatibilidad v1 en el catálogo |

Regla: **antes de cualquier migración se copia `orchestrator_gui.sqlite` a `data/bkp/`**. Con B, `catalog_folders` pasa a ser un árbol de nodos real (categoría/grupo) con `rel_path` calculable,
las cuentas cuelgan de un nodo, y todo lo demás (estados, favoritos, colores, `start_init_date`) se copia tal cual. Las tablas de lotes se mantienen solo para no perder el historial mientras no estorbe.

## Valor que entrega por sí solo

- El árbol del catálogo muestra la biblioteca completa (filtro «Solo gestionadas / Toda la biblioteca»).
- Búsqueda por `ownerId` y detección inmediata de ids repetidos (base del Problema 1).
- El **story inbox** deja de depender de G: para resolver rutas: pasa a consultar `bdapp` (con *fallback* a lite durante la transición).
- Se separan los dos significados de `last_modified` (ver `v3-status.md` §4.1).

## Estado actual (evidencia)

- `catalog_accounts`: 334 filas; `catalog_folders`: 87; ruta de cuenta = `catalog_folders.full_path` + `username` (absoluta, con letra `G:`).
- Lite tiene 1 231 filas (1 231 usernames distintos); 902 no están en la app; 69 grupos de `ownerId` repetido; 15 rutas muertas.
- El patrón para ampliar el esquema ya existe: `db/gui_migrations._patch_gui_schema` + `_add_column_if_missing` (así se añadió `batch_accounts.priority`).

## Diseño

### Esquema (migración aditiva, `user_version` sigue en 100)

**Antes de migrar** (tarea común a todos los feats con migración, ver `plan-v3-features.md` §7): copia de seguridad automática de `orchestrator_gui.sqlite`
en `data/bkp/` con la API de backup de SQLite, solo si hay cambios de esquema pendientes. Este es el primer feat con migración, así que añade ese mecanismo.

En `_patch_gui_schema`:

```sql
-- raíces
INSERT OR IGNORE INTO path_roots (code, path, updated_at) VALUES ('LIBRARY', 'G:\4K Stogram', datetime('now'));
-- (FINAL_BASE queda como alias histórico; se migra su valor a LIBRARY si estuviera relleno)

-- carpetas: ruta relativa a la raíz y tipo
ALTER TABLE catalog_folders ADD COLUMN root_id   INTEGER REFERENCES path_roots(id);
ALTER TABLE catalog_folders ADD COLUMN rel_path  TEXT;                  -- '00.FAVORITES\Emily-Burns'
ALTER TABLE catalog_folders ADD COLUMN kind      TEXT NOT NULL DEFAULT 'GROUP';   -- CATEGORY | GROUP

-- cuentas: ruta y metadatos del disco
ALTER TABLE catalog_accounts ADD COLUMN rel_path        TEXT;           -- ruta completa relativa a LIBRARY
ALTER TABLE catalog_accounts ADD COLUMN posts_count     INTEGER;
ALTER TABLE catalog_accounts ADD COLUMN reels_count     INTEGER;
ALTER TABLE catalog_accounts ADD COLUMN story_count     INTEGER;
ALTER TABLE catalog_accounts ADD COLUMN highlights_count INTEGER;
ALTER TABLE catalog_accounts ADD COLUMN last_media_at   TEXT;           -- el antiguo last_modified de sc1 (fecha del contenido)
ALTER TABLE catalog_accounts ADD COLUMN last_scan_at    TEXT;
ALTER TABLE catalog_accounts ADD COLUMN disk_state      TEXT NOT NULL DEFAULT 'UNKNOWN';   -- PRESENT | MISSING | UNKNOWN
ALTER TABLE catalog_accounts ADD COLUMN legacy_lite_id  INTEGER;        -- trazabilidad de la importación

CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_accounts_rel_path ON catalog_accounts(rel_path) WHERE rel_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_catalog_accounts_owner ON catalog_accounts(instagram_user_id);

-- nuevo estado de catálogo: «solo en la biblioteca»
INSERT OR IGNORE INTO catalog_account_statuses (id, code, name, description, color_hex, sort_order)
VALUES (4, 'ARCHIVED', 'Archived', 'On disk only; never downloaded by the app.', '#e8eaed', 4);
```

Decisiones:

- **Rutas relativas a `LIBRARY`** (`rel_path`), no absolutas: G: puede cambiar de letra o estar desconectada sin invalidar filas (principio 4).
  `catalog_folders.full_path` se mantiene para no romper la GUI actual y se regenera como `root.path + rel_path`.
- **Unicidad del username:** `catalog_accounts` tiene índice único `username COLLATE NOCASE`. Hoy lite tiene 1 231 usernames distintos
  (medido), pero eso es porque `sc1` **colapsa** en una sola fila los usernames repetidos (`upsert_lite_account` busca por ruta y, si no, por username),
  así que una segunda carpeta con el mismo username en otro sitio **sería invisible** para lite. El importador no puede violar el índice:
  ante cualquier colisión (entre lite y complete, o contra una cuenta de la app) importa **una sola fila canónica** y anota el resto en una tabla de
  incidencias (`library_import_issues`) para que `feat-problem1-7` / `feat-uc3-8` las resuelvan:

```sql
CREATE TABLE IF NOT EXISTS library_import_issues (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,           -- USERNAME_DUP | OWNER_DUP | PATH_MISSING | PARSE_ERROR
    username TEXT, owner_id TEXT, rel_path TEXT, detail TEXT,
    created_at TEXT NOT NULL
);
```

- **Canónica:** gana la que esté en categoría «activa» (fuera de `06.EXCLUDED`, `09.DELETED`, `10.TEMP`, `11.DISCARTED`); a igualdad, la de contenido más reciente.
- **Estado inicial** de lo no gestionado: `ARCHIVED`. Las 334 cuentas ya existentes **no cambian de estado**; solo reciben `rel_path`, contadores y `last_media_at`.

### Índice de ficheros para el renombrado (`media_index`) — incluido en este feat

Se define y se pobla aquí (el uso por el renombrador llega en `feat-uc1-9`/`feat-uc5-10`). Es lo que `sc2` necesita de la biblioteca: por cuenta y subcarpeta, `media_id`, fecha del nombre y `owner_id`.

```sql
CREATE TABLE IF NOT EXISTS media_index (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
    kind INTEGER NOT NULL,            -- 0 raíz(post) · 1 reels · 2 story · 3 highlights
    media_id INTEGER NOT NULL, taken_at INTEGER NOT NULL, owner_id INTEGER NOT NULL,
    ext INTEGER NOT NULL,             -- 0 jpg · 1 jpeg · 2 mp4
    suffix TEXT NOT NULL DEFAULT '',  -- '_manual', '(1)'…
    location INTEGER NOT NULL DEFAULT 0, origin INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_media_index_lookup ON media_index(account_id, kind, media_id);
CREATE TABLE IF NOT EXISTS media_index_state (
    account_id INTEGER NOT NULL, kind INTEGER NOT NULL, items INTEGER NOT NULL, max_media_id INTEGER,
    indexed_at TEXT NOT NULL, dir_mtime REAL, source TEXT NOT NULL, PRIMARY KEY (account_id, kind));
```

Detalles y tamaños (≈ 50–80 MB, 909 929 filas, ids de 64 bits con margen) en `feat-uc5-10.md`. La importación lee `accounts_complete.media` de forma secuencial
(no recorre el árbol de carpetas), parsea cada nombre con el regex único (`library/filenames.py`) y asocia cada fila a su cuenta por `rel_path`/username.

### Qué columnas de `accounts_complete` pasan a `bdapp`

| `accounts_complete` | `bdapp` | Uso |
|---|---|---|
| `username` | `catalog_accounts.username` | catálogo |
| `ownerId` | `instagram_user_id` (solo rellena vacíos; discrepancias → incidencia) | catálogo, renombrado, detección de renombrados |
| `path` | `rel_path` + nodo padre | catálogo, mover, story inbox |
| `posts/reels/story/highlights` | `*_count` | catálogo |
| `last_modified` (fecha del último contenido) | `last_media_at` | catálogo |
| `media.*` | `media_index` | renombrado |
| `created_at/modified_at`, `field1-3` | descartados | — |

### Importador (módulo nuevo, sin Tk)

```
src/ig_orchestrator/library/
    import_bdsc1.py     # import_from_bdsc1(app_conn, lite_path, complete_path|None, *, dry_run) -> ImportReport
    paths.py            # to_rel(path, root) / to_abs(rel, root); normalización (casefold + separadores)
```

Pasos (todo dentro de una transacción; `dry_run=True` solo calcula el informe):

1. Leer **complete** (`mode=ro`) como fuente principal (cuentas, contadores, `last_media_at`, `media`) y lite solo como autoridad de rutas si difiere.
2. Resolver cada fila: `rel_path` = ruta relativa a `LIBRARY`; `kind` de cada carpeta intermedia (nivel 1 = `CATEGORY`, nivel 2 = `GROUP`).
3. Cruce con `catalog_accounts` por **username (sin mayúsculas)**; si no, por `instagram_user_id` (aviso de posible renombrado → incidencia `OWNER_DUP`).
4. Rellenar `instagram_user_id` solo si está vacío en la app (nunca sobrescribir un valor existente; las 4 diferencias se reportan).
5. Crear `catalog_folders` que falten (`INSERT OR IGNORE` por `full_path`).
6. Registrar `legacy_lite_id`; escribir `last_media_at` desde complete cuando esté disponible (**no** desde el `last_modified` de lite: ese valor es la fecha del lote).

Idempotente: ejecutarlo dos veces no duplica filas ni degrada estados. Informe: filas creadas / actualizadas / incidencias por tipo.

### Consumidores que cambian

| Módulo | Cambio |
|---|---|
| `filesystem/story_inbox.py` | `_lookup_account_path` consulta primero `catalog_accounts.rel_path` + raíz `LIBRARY`; si no hay fila, *fallback* a `accounts_dir`. El parámetro `accounts_db` pasa a ser opcional. |
| `gui/catalog/service.py` + adaptador `db/v2/adapters/account.py` | Las consultas de la lista del catálogo filtran por estado (`ARCHIVED` oculto por defecto) para no cambiar el comportamiento del editor. |
| `gui/catalog/tree.py` / `panel.py` | Interruptor «Mostrar biblioteca completa»; `ARCHIVED` en gris. |
| Ajustes → Catálogo | Botón **Importar desde bdsc1…** (usa el diálogo de `feat-uc3-1` para mostrar el informe previo en modo *dry-run*). |
| CLI | `python -m ig_orchestrator import-bdsc1 --lite PATH [--complete PATH] [--dry-run]` |

### Compatibilidad hacia `sc2`

Hasta `feat-uc1-9`, `sc2` sigue leyendo/escribiendo `accounts_lite`. Este feat **no lo modifica**. Tras cada renombrado de `sc2`
(cuentas nuevas insertadas en lite) se ofrece «Reimportar» (idempotente) para traerlas a `bdapp`. El espejo automático bdapp → lite llega
con `feat-uc2-4`.

## Casos borde

- Carpeta de lite con ruta fuera de `LIBRARY` (por si cambiaste de raíz): se importa con `rel_path = NULL` + incidencia.
- `ownerId` vacío en lite (hoy 0): se deja `NULL`.
- Mayúsculas distintas entre carpeta y username: se conserva la capitalización de la **carpeta** (es la que tiene el disco).
- G: desconectada al importar: funciona (lite y complete se pueden copiar a local; el importador no toca el árbol).

## Pruebas

- `tests/library/test_import_bdsc1.py`: SQLite temporal con casos: cuenta ya en la app, cuenta nueva, username repetido en dos carpetas, ownerId duplicado, `last_modified` mixto, ruta fuera de raíz; idempotencia (doble ejecución); `dry_run`.
- `tests/db/test_gui_migrations.py`: la migración añade columnas una sola vez y mantiene los datos.
- `tests/filesystem/test_story_inbox.py`: resolución por `bdapp`, *fallback* a lite, cuenta inexistente.
- Prueba manual: importar con tus datos reales y comparar con el informe de `feat-uc3-1` (1 231 filas; 902 nuevas `ARCHIVED`; incidencias = grupos de `OWNER_DUP`).

## Criterios de aceptación

1. Tras importar: `catalog_accounts` = 1 231 + las 5 cuentas `DISABLED` que solo existen en la app (≈ 1 236 menos colisiones canonizadas) y el árbol muestra las 16 categorías.
2. Las 334 cuentas previas conservan estado, favorito y `start_init_date`.
3. Story inbox mueve un fichero de una cuenta **que no está en lite** pero sí en `bdapp`.
4. El editor/lote sigue mostrando solo cuentas gestionadas por defecto.
5. Una segunda importación sin cambios en disco informa «0 creadas, 0 actualizadas».

## Documentación a actualizar

`CHANGELOG.md`, `README.md`, `gui/catalog/MODULE.md`, `db/MODULE.md` (si existe), `docs/modularizacion_v2.md` (esquema), nuevo `library/MODULE.md`, `tasks/done/`.

## Fuera de alcance

Escanear el disco (→ `feat-uc3-8`), escribir en disco (→ `feat-uc2-4`), usar el índice para renombrar (→ `feat-uc1-9`/`feat-uc5-10`).
