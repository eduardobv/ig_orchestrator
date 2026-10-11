# feat-uc5-10 — Renombrar sin la unidad G: (índice de timeline en `bdapp`)

> **Actualizado 2026-10-11:** el esquema `media_index` y su **importación inicial desde `accounts_complete`** pasan a `feat-uc1-3` (primer paso, como pediste).
> Este feat conserva lo demás: uso del índice por el renombrador, escritura en el momento, selección disco/índice, renombrado offline con movimiento pendiente, verificación y reparación.
> La vía 1 de «Poblado» y el esquema que siguen abajo son la referencia de diseño; la implementación se hace en el feat 3.

| | |
|---|---|
| **Dificultad** | 10 / 12 |
| **Cubre** | UC5 · parte de UC6 |
| **Riesgo** | Alto-medio: si el índice está desactualizado el renombrado puede asignar fechas algo distintas o no detectar duplicados. Mitigado con estado/antigüedad del índice y verificación al reconectar G: |
| **Dependencias** | `feat-uc1-9` (motor con `ConsultProvider`) y `feat-uc1-3` (cuentas/rutas en `bdapp`). Recomendado: `feat-uc3-8` (mantiene el índice fresco) |
| **Estimación** | 6–8 días |

## Objetivo

Poder **renombrar con G: desconectada** guardando en `bdapp` exactamente lo que el algoritmo de `sc2` necesita de la biblioteca,
en lugar de leerlo del disco en cada renombrado.

## Valor que entrega por sí solo

- Renombrar en cualquier momento (G: apagada, en otro sitio, en `inst1`), sin esperar a conectar el disco.
- Renombrar es más rápido: ya no se listan carpetas de miles de ficheros del HDD USB por cada cuenta.
- Menos lectura del disco externo (UC3).
- Deja las carpetas renombradas **marcadas como pendientes de mover**; cuando G: vuelve, un botón las mueve (primer paso hacia UC6).

## Lo que necesita `sc2` de la biblioteca (análisis, ver `v3-status.md` §4.3)

Para cada cuenta y cada subcarpeta (`raíz`, `reels`, `story`, `highlights`), la lista de ficheros ya renombrados con:
`media_id`, `fecha del nombre`, `owner_id` (+ `ext`, y el sufijo, para colisiones). Con eso calcula: (a) duplicados (¿el id ya está?), (b) los vecinos que acotan las fechas
de los bloques nuevos, (c) el `user_id` a propagar. **No necesita nada más** (ni contadores, ni rutas de ficheros, ni tamaños).

Esa información ya existe en `accounts_complete.sqlite → media` (909 929 filas; **todas** `jpg/jpeg/mp4`; 909 921 cumplen el regex de `sc2`; media_id máximo 3,94·10¹⁸ = 43 % del máximo de un entero de 64 bits;
media 815 filas por cuenta, máximo 28 486), pero con tres problemas: está en G:, está desactualizada (última actualización 2026-07-18) y guarda texto redundante (`username`, `path`).

## Diseño

### Esquema

```sql
CREATE TABLE IF NOT EXISTS media_index (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
    kind        INTEGER NOT NULL,         -- 0 raíz(post) · 1 reels · 2 story · 3 highlights
    media_id    INTEGER NOT NULL,         -- 64 bits (con comprobación al insertar)
    taken_at    INTEGER NOT NULL,         -- fecha del nombre (naive) como segundos desde 1970 (no es un instante real)
    owner_id    INTEGER NOT NULL,
    ext         INTEGER NOT NULL,         -- 0 jpg · 1 jpeg · 2 mp4
    suffix      TEXT    NOT NULL DEFAULT '',     -- lo que hay entre owner_id y la extensión (p. ej. '_manual', '(1)')
    location    INTEGER NOT NULL DEFAULT 0,      -- 0 biblioteca · 1 pendiente de mover (carpeta de trabajo / almacén)
    origin      INTEGER NOT NULL DEFAULT 0       -- 0 importado/escaneado · 1 creado por el renombrador de la app
);
CREATE INDEX IF NOT EXISTS idx_media_index_lookup ON media_index(account_id, kind, media_id);

CREATE TABLE IF NOT EXISTS media_index_state (
    account_id INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
    kind       INTEGER NOT NULL,
    items      INTEGER NOT NULL,
    max_media_id INTEGER,
    indexed_at TEXT NOT NULL,
    dir_mtime  REAL,                      -- mtime de la carpeta cuando se indexó (para detectar cambios externos)
    source     TEXT NOT NULL,             -- COMPLETE_IMPORT | SCAN | RENAME
    PRIMARY KEY (account_id, kind)
);
```

Tamaño estimado: ~910 000 filas × ~35 B + índice ≈ **50–80 MB**, menos que el `accounts_complete.sqlite` actual (282 MB) por no guardar `username`/`path` repetidos. A medir.

### Poblado (tres vías)

1. **Importación única desde `accounts_complete.media`** (`library/import_media.py`): no recorre el árbol de carpetas; lee un fichero SQLite de ~280 MB de forma secuencial y parsea cada nombre con `library/filenames.py`
   (la misma función que usa el escáner). Estimación < 1–2 min (a medir). Deja el estado `COMPLETE_IMPORT` con la fecha de julio.
2. **Refresco por el escáner** (`feat-uc3-8`): cuando detecta que cambió el `mtime` de una subcarpeta, además de contadores **reemplaza las filas de ese `(cuenta, kind)`** (una lectura de esa carpeta, que ya hace por otros motivos).
   Es el mecanismo que cubre cambios hechos fuera de la app.
3. **Escritura en el momento (*write-through*)** en el renombrador (`feat-uc1-9`): por cada fichero renombrado se inserta su fila (`origin=1`, `location=1` si sigue en carpeta de trabajo; pasa a `0` al moverse a la biblioteca). Cubre el 100 % de lo que hace la app.

### Uso en el renombrador

`renaming/consult.py` gana `IndexConsultProvider(app_conn, account_id, kind)`, que devuelve los mismos `ConsultItem` que `DiskConsultProvider` (ordenados por `media_id`). Selección automática:

| Situación | Proveedor |
|---|---|
| G: conectada y el índice de la cuenta está al día (`dir_mtime` coincide) | Índice (más rápido) — o disco si el usuario fuerza «Leer del disco» |
| G: conectada y el índice está desfasado | Se refresca esa cuenta (1 lectura) y luego índice |
| G: desconectada y hay índice | Índice, con aviso de antigüedad: «índice del 18/07; los cambios hechos fuera de la app desde entonces no se tienen en cuenta» |
| G: desconectada y **no** hay índice para la cuenta y no es nueva | La cuenta se omite con motivo `NO_INDEX` |
| Cuenta nueva | Sin consult (como `sc2`) con `start_init_date`/`startNowDate` |

### Movimiento pendiente (mínimo de UC6 incluido aquí)

Con G: desconectada, `move_renamed` no puede completarse. El servicio:
- renombra **en su sitio** (en la carpeta de trabajo),
- deja `rename_run_accounts.status = RENAMED_PENDING_MOVE` y las filas del índice con `location = 1`,
- ofrece **Lote → Mover renombradas pendientes** que, cuando G: está disponible, ejecuta el mismo movimiento/fusión de `feat-uc1-9`/`feat-uc2-4` y pone `location = 0`.
La generalización a un almacén dedicado con volcado selectivo es `feat-uc6-11`.

### Verificación y reparación

- **Estado del índice** en la ficha de la cuenta y en la modal de Renombrar: «completo · 12/07 · 4 718 ficheros».
- **«Verificar índice con el disco»** (solo G: conectada): compara `(cuenta, kind)` con `scandir` y lista altas/bajas; botón *Aceptar disco*.
- Auditoría integrada en `feat-uc3-1`: nuevos códigos `INDEX_STALE` y `INDEX_MISSING`.

## Casos borde

- **Duplicados del mismo `media_id`** en una subcarpeta (p. ej. `…_manual` y `…(1)`): el índice admite filas repetidas (no hay unicidad); `sc2` también las trata como piezas separadas.
- **Renombrado de una cuenta con fusión** (`feat-problem1-7`): el motor debe reasignar `account_id` de las filas del índice de la cuenta absorbida.
- **Ficheros borrados fuera de la app**: aparecen como «bajas» en la verificación; mientras tanto el renombrador puede considerar duplicado un id que ya no existe (impacto bajo y reversible).
- **IDs mayores de 2⁶³−1** (improbable; hoy 43 %): se rechaza la fila con aviso y se usa el proveedor de disco para esa cuenta.
- **Carpeta de cuenta recién movida**: el índice depende de `account_id`, no de rutas; mover carpetas no lo invalida.
- **Dos ejecuciones simultáneas**: el servicio de renombrado toma el bloqueo único de operaciones de disco.

## Pruebas

- `tests/library/test_import_media.py`: importación desde un `accounts_complete` sintético (y el caso `username` con mayúsculas distintas).
- `tests/renaming/test_index_provider.py`: **equivalencia** entre `DiskConsultProvider` e `IndexConsultProvider` sobre el mismo árbol, para las 4 subcarpetas y con nombres `_manual`, `(1)`.
- `tests/renaming/test_parity_index_vs_disk.py`: el resultado completo del renombrado (con semilla) es idéntico usando disco o índice.
- `tests/renaming/test_offline_rename.py`: G: «desconectada» (ruta inexistente) → renombra en su sitio, `RENAMED_PENDING_MOVE`, mover pendientes tras «reconectar».
- `tests/library/test_scanner_updates_index.py`: el escáner reemplaza solo el `(cuenta, kind)` cambiado.
- Prueba real: renombrar un lote pequeño con G: **desconectada físicamente** y luego con G: conectada; comparar nombres.

## Criterios de aceptación

1. Con G: desconectada se renombra un lote completo; las cuentas quedan renombradas en la carpeta de trabajo y marcadas «pendiente de mover».
2. Con G: conectada, el resultado con índice es idéntico al resultado leyendo del disco (con semilla fija).
3. La importación inicial tarda ≤ 2 min y el tamaño añadido a `bdapp` ≤ 100 MB.
4. «Verificar índice» sobre una cuenta con cambios externos los muestra.
5. Tras mover pendientes, `location` vuelve a 0 y la carpeta aparece en la biblioteca con los mismos nombres.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (renombrar sin disco), `library/MODULE.md`, `renaming/MODULE.md`, `docs/modularizacion_v2.md` (tablas del índice), `tasks/done/`.

## Fuera de alcance

Almacén dedicado y volcado selectivo (→ `feat-uc6-11`); retirar `accounts_complete.sqlite` (se puede archivar tras validar el índice).
