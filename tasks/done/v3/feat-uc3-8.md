# feat-uc3-8 — Sincronización incremental disco ↔ BD (sustituye a `sc1`)

| | |
|---|---|
| **Dificultad** | 8 / 12 |
| **Cubre** | UC3 (completo) y la parte de `sc1` de UC1 · proceso manual M5 |
| **Riesgo** | Medio: escribe contadores/estados en `bdapp`; lee el disco de forma acotada |
| **Dependencias** | `feat-uc1-3` (rutas relativas y columnas de escaneo). Se apoya en `feat-uc2-4` (cambios hechos por la app ya se anotan y no se releen) |
| **Estimación** | 6–8 días |

## Objetivo

Mantener `bdapp` sincronizada con el disco **leyendo lo mínimo**: un escáner incremental que decide qué carpetas releer con una pista barata
(fecha de modificación de la carpeta), que se ejecuta **solo a petición** (no al arrancar), y que permite corregir discrepancias desde la app.
Sustituye a `generatedirmap.py` (`--complete/--lite/--update`).

## Valor que entrega por sí solo

- Actualizar el catálogo pasa de **~8 minutos de lectura intensa del disco** (`--complete`: 455–504 s medidos en el log) a **segundos–1 minuto** y solo de lo cambiado.
- Botón **«Verificar cuenta»** (1 cuenta, instantáneo) y **«Verificar categoría»**.
- Contadores, `ownerId`, `last_media_at` y `disk_state` al día; se ven en el árbol (cuentas cuyo disco no coincide con la BD aparecen marcadas).
- Menos desgaste del HDD USB: decenas/centenares de directorios en vez de ~910 000 nombres de fichero.

## Cómo se reduce la lectura (la idea central)

1. **Principio write-through (coste cero).** Todo lo que la app hace en disco (descargas movidas, rename, mover/renombrar carpetas, volcados) **ya anota** el efecto en la BD
   (contadores y `last_*`). Eso cubre el ~100 % del tráfico normal sin leer nada.
2. **Pista por `mtime` de carpeta (coste mínimo).** En NTFS la fecha de modificación de una carpeta cambia cuando se **crean, borran o renombran** entradas directas.
   La app guarda el `mtime` observado (`dir_mtime`) de cada carpeta de cuenta y de sus subcarpetas `story/`, `reels/`, `highlights/`. Un barrido de `stat` (sin listar ficheros) dice qué carpetas cambiaron.
   - **Medido hoy:** 4 721 `stat` (1 231 cuentas × raíz + 3 subcarpetas) en **41 s en frío** (menos con caché) frente a 455–504 s del escaneo completo; 629 carpetas con cambios en los últimos 30 días.
3. **Relectura selectiva.** Solo las carpetas con `mtime` distinto al guardado se listan (`os.scandir`), y se recalculan contadores/`ownerId`/`last_media_at` de esa carpeta.
4. **Niveles superiores casi gratis.** El árbol de categorías/grupos (niveles 1–2) se lista con `scandir` (< 0,1 s medido) para detectar carpetas nuevas, desaparecidas o renombradas.
5. **Verificación profunda ocasional y manual.** «Verificación completa» (equivalente a `--complete`) queda como opción explícita, con aviso de coste y estimación basada en el último tiempo medido.

> El `mtime` es una **pista**, no una garantía (herramientas que no actualizan la fecha, restauraciones con atributos). Por eso: (a) siempre se puede verificar una cuenta o categoría a mano,
> (b) un contador de ficheros de control (`entries_count` de `scandir` de la carpeta) se compara en la verificación por cuenta, y (c) la verificación completa sigue disponible.

## Estado actual (evidencia)

- `sc1` solo se ejecuta a mano, con G: conectada. `--lite` ya es barato (13–55 s) porque no lista ficheros de cuentas; lo caro es `--complete` (lista ~910 000 nombres).
- `last_modified` tiene dos significados y formatos (ver `v3-status.md` §4.1).
- `upsert_lite_account` colapsa usernames repetidos en una sola fila (una segunda carpeta con el mismo username se vuelve invisible).
- 15 rutas muertas y 116 discrepancias lite↔complete al día de hoy.

## Diseño

### Esquema (ampliando `feat-uc1-3`)

```sql
ALTER TABLE catalog_accounts ADD COLUMN dir_mtime_root       REAL;    -- st_mtime de la carpeta de cuenta
ALTER TABLE catalog_accounts ADD COLUMN dir_mtime_story      REAL;
ALTER TABLE catalog_accounts ADD COLUMN dir_mtime_reels      REAL;
ALTER TABLE catalog_accounts ADD COLUMN dir_mtime_highlights REAL;
ALTER TABLE catalog_accounts ADD COLUMN scan_state TEXT NOT NULL DEFAULT 'UNKNOWN';  -- OK | CHANGED | MISSING | UNKNOWN

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY, scope TEXT NOT NULL,          -- ALL | CATEGORY | ACCOUNT | DEEP
    root_id INTEGER REFERENCES path_roots(id), rel_scope TEXT,
    started_at TEXT NOT NULL, finished_at TEXT,
    dirs_stat INTEGER DEFAULT 0, dirs_listed INTEGER DEFAULT 0, files_seen INTEGER DEFAULT 0,
    accounts_changed INTEGER DEFAULT 0, accounts_new INTEGER DEFAULT 0, accounts_missing INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0, seconds REAL);
CREATE TABLE IF NOT EXISTS scan_findings (
    id INTEGER PRIMARY KEY, scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,        -- NEW_FOLDER | MISSING_FOLDER | COUNT_CHANGED | OWNER_CHANGED | OWNER_DUP | NAME_CASE | NEEDS_REVIEW
    account_id INTEGER REFERENCES catalog_accounts(id), rel_path TEXT, detail TEXT, resolved INTEGER NOT NULL DEFAULT 0);
```

### Módulo (sin Tk; lógica heredada de `sc1` y simplificada)

```
src/ig_orchestrator/library/
    filenames.py   # regex y parseo (única fuente: media_id, owner_id, timestamp)  ← sc1 + sc2
    detect.py      # is_account_folder(entries, rules), NON_ACCOUNT_FOLDER_NAMES configurable
    scanner.py     # scan(app_conn, root, scope, *, deep=False, cancel_event, progress_cb) -> ScanReport
    rules.py       # LibraryRules: extensiones, subcarpetas multimedia, nivel máximo (lee app_settings)
```

Reglas heredadas y ahora **configurables** en `app_settings`: `library.max_depth` (3), `library.media_subfolders` (`reels,story,highlights`),
`library.media_extensions`, `library.non_account_names` (lista de `sc1`).

Algoritmo `scan(scope=ALL)`:

1. `scandir` niveles 1..`max_depth` para enumerar candidatas (misma detección que `sc1`, pero reutilizando `rel_path` conocidos para no re-evaluar contenido).
2. Comparar con `catalog_accounts`: nueva (`NEW_FOLDER`), desaparecida (`MISSING_FOLDER`; **no se borra**, se marca `disk_state=MISSING`), movida (misma `instagram_user_id`, otra ruta → propuesta de `feat-problem1-7`/`feat-uc2-4`, no se aplica sola).
3. Para las conocidas: `stat` de raíz y subcarpetas; relistar solo las cambiadas; recalcular `posts/reels/story/highlights_count`, `instagram_user_id` (solo para rellenar vacíos o avisar de cambios), `last_media_at`.
4. Poda segura: igual que `sc1`, **no marcar ausentes** si hubo errores de lectura en el recorrido.
5. Escribir `scan_runs`, `scan_findings`; actualizar `dir_mtime_*` y `scan_state`.

Operaciones de coste: `scan(scope=ACCOUNT, id)`: 4 `stat` + a lo sumo 4 `scandir` (la cuenta). `scan(scope=CATEGORY, rel)`: lo anterior para su subárbol. `deep=True`: relee todo (equivale a `--complete` sin tabla `media`).

### UI

- `Catálogo → Sincronizar` con tres opciones: **Rápida (por cambios)**, **Verificar categoría seleccionada**, **Verificación completa…** (con estimación y confirmación).
  También menú contextual de cuenta: **Verificar ahora**.
- Panel de **hallazgos** (`gui/library/scan_findings_dialog.py`): lista filtrable por tipo con acciones: *Aceptar* (actualiza BD a lo que hay en disco), *Mover*/*Renombrar* (abre el plan de `feat-uc2-4`/`feat-problem1-7`), *Ignorar*.
- Indicador en el árbol: ✓ ok · ⟳ cambiada desde el último escaneo · ✕ ausente · • desconocida.
- **Nunca** se escanea al arrancar. Opcional: aviso discreto «hace N días de la última sincronización» (`app_settings.scan.remind_days`).
- CLI: `python -m ig_orchestrator scan [--scope all|category|account] [--deep] [--path REL]`.

### Paridad con el algoritmo de `accounts_complete` (actualizado 2026-10-11)

El algoritmo de carga de `sc1 --complete` es la referencia: este escáner **lo porta, no lo reinterpreta**. `deep=True` debe producir en `bdapp` los mismos
`ownerId`, contadores, `last_media_at` y **filas de `media_index`** que `--complete` produce en `accounts_complete` (prueba de paridad obligatoria). El escáner es además quien
mantiene fresco el `media_index` (reemplaza las filas del `(cuenta, kind)` cuya carpeta cambió) y quien detecta lo cambiado fuera de la app. Al terminar este feat, `sc1` ya no se necesita.

### Retirada gradual de `sc1`

- Mientras exista `compat.lite.enabled`, el espejo (`feat-uc2-4`) se actualiza con el resultado del escaneo (solo las filas cambiadas).
- La importación inicial de `media` ya la hace `feat-uc1-3`; este feat solo la mantiene al día (ver sección anterior).

## Casos borde

- G: desconectada → la sincronización se deshabilita; los datos conservan `disk_state` anterior (no pasa a `MISSING`).
- Carpetas que contienen un único fichero suelto (no cuenta como cuenta, igual que `sc1`): hallazgo `NEEDS_REVIEW`, no se crea cuenta.
- Dos carpetas con el mismo username → ambos hallazgos (`sc1` perdía una); la BD no se corrompe gracias al índice único; se resuelve con `feat-problem1-7`.
- `mtime` en el futuro o a cero (restauraciones) → se trata como «cambiada».
- Cancelación a mitad: lo ya procesado queda guardado (commit por cuenta o por bloque de 50) y el resto sigue con su estado anterior.
- Rendimiento: `stat` por lote con hilos opcionales (HDD USB: limitado por latencia; se mide si compensa).

## Pruebas

- `tests/library/test_filenames.py`: casos del regex (con `_manual`, sufijos, nombres inválidos) iguales a los de `sc1`/`sc2`.
- `tests/library/test_detect.py`: reproduce `scanner.md` (Ejemplos 1 y 2, carpetas de categoría).
- `tests/library/test_scanner.py`: árbol temporal; sin cambios → 0 relecturas (contador `dirs_listed`); añadir un fichero → solo esa cuenta se relee; carpeta nueva/desaparecida/movida; error de lectura → sin poda; cancelación.
- **Paridad con `sc1`:** prueba que ejecuta `generatedirmap.py --complete` y el escáner `deep=True` sobre el mismo árbol de prueba y compara `ownerId`, contadores y `last_modified`.
- Prueba manual: ejecutar «Rápida» dos veces seguidas en tus datos reales (la segunda debe listar 0 carpetas) y comparar con el informe de `feat-uc3-1`.

## Criterios de aceptación

1. «Rápida» sin cambios termina en < 60 s en frío y lista 0 carpetas de cuenta; con N cuentas cambiadas relee solo N.
2. Tras descargar y renombrar un lote desde la app, «Rápida» no encuentra diferencias (write-through correcto).
3. Mover una carpeta en Explorer aparece como `MISSING_FOLDER` + `NEW_FOLDER` con la sugerencia «¿misma cuenta? (mismo id)».
4. La verificación completa coincide con `sc1 --complete` en `ownerId`, contadores y último contenido en la muestra de paridad.
5. La app no escanea nunca por sí sola al arrancar.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (nuevo flujo de sincronización), `library/MODULE.md`, `gui/catalog/MODULE.md`, `tasks/done/`.

## Fuera de alcance

Índice de ficheros (`media`), detección automática de renombrados sin confirmación, observadores del sistema de ficheros (USN/ReadDirectoryChangesW) — se descartan por exigir G: conectada en todo momento.

## Resultado de la implementación (2026-10-12, v3.8.0)

- Implementado el escáner incremental con `stat` por carpeta, línea base tras la importación, escaneo por ámbito (todo, categoría, cuenta) y completo, hallazgos con Aceptar/Ignorar, reglas configurables y CLI.
- **Paridad con `sc1` verificada** con un árbol de prueba (id de Instagram, contadores, último contenido y filas de índice). La única diferencia deliberada: el índice solo guarda `jpg`/`jpeg`/`mp4` (el resto cuenta en los contadores, como en `sc1`).
- **Primer escaneo = línea base:** en tu base real tomó 1 158 cuentas como base y relistó 11 (sin id de Instagram). Si dudas de la importación, usa **Verificación completa**.
- **No implementado (diferido):** indicador ✓/⟳/✕ en el árbol, aviso «hace N días» (`scan.remind_days`; el texto existe como `_scan_reminder`), botones *Mover*/*Renombrar* dentro de hallazgos (se resuelven con «Cambió de username…» / «Mover a…»), prueba automática contra `generatedirmap.py` (se ejecutó a mano), hilos para el `stat` (0,5 s con caché; ~40 s en frío medido antes).
- **Write-through pendiente:** hasta los feats 9–10 el renombrado (`sc2`) no anota contadores, así que las carpetas que toca aparecen como «con cambios» en la siguiente sincronización rápida (esperado y barato).
- `accounts_lite` no se actualiza con el escáner (se retira `sc1`); las cuentas nuevas aceptadas no se escriben en lite.
