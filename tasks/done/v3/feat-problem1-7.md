# feat-problem1-7 — Cuenta renombrada en Instagram (mismo id, otro username)

| | |
|---|---|
| **Dificultad** | 7 / 12 |
| **Cubre** | Problema 1 (parte «renombrada») · proceso manual M4 |
| **Riesgo** | Medio-alto: puede **fusionar carpetas** (mover miles de ficheros) y reasignar referencias de lotes |
| **Dependencias** | `feat-uc2-4` (motor de operaciones) y `feat-uc1-3` (catálogo completo con `ownerId`). Se apoya en `feat-uc3-1` para la lista de candidatos |
| **Estimación** | 6–8 días |

## Objetivo

Resolver un cambio de username **desde la app, en un solo gesto**: renombrar (o fusionar) la carpeta, actualizar `bdapp` y el espejo `accounts_lite`,
conservar el historial de nombres y refrescar la GUI **sin cerrar y reabrir la app**.

## Valor que entrega por sí solo

- Sustituye el proceso M4 completo (buscar el id en dos BD, renombrar en las dos, renombrar la carpeta, reiniciar).
- **Detecta candidatos solo:** hoy hay **69 grupos de `ownerId` con más de un username** (19 de ellos dentro de `00.FAVORITES`); la app los presenta ordenados con una propuesta.
- Evita perder histórico: el nombre antiguo queda como alias y los lotes antiguos siguen apuntando a la cuenta correcta.
- El story inbox y el editor resuelven nombres antiguos sin fallar.

## Estado actual (evidencia)

- `catalog_accounts.username` es único sin distinguir mayúsculas y **no hay historial**; `batch_accounts` referencia `catalog_account_id` (bien: renombrar la fila no rompe los lotes).
- `filesystem/story_inbox.py` busca por `username` exacto en `accounts_dir`; un nombre antiguo da `USERNAME_NOT_IN_DB`.
- Los nombres de fichero de la biblioteca **no contienen el username** (`YYYY-MM-DD HH.MM.SS {media_id}_{owner_id}[...].ext`), así que renombrar la carpeta no obliga a renombrar ficheros.
- Los 69 grupos duplicados son una mezcla (misma categoría, antigua + `09.DELETED`, etc.) — `v3-status.md` §4.2; la mayoría serán renombrados no resueltos, pero la lista se debe revisar a mano (Q3).

## Diseño

### Esquema

```sql
CREATE TABLE IF NOT EXISTS account_usernames (
    id INTEGER PRIMARY KEY,
    catalog_account_id INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
    username TEXT NOT NULL COLLATE NOCASE,
    valid_from TEXT,                    -- fecha en que se empezó a usar (si se conoce)
    valid_to   TEXT,                    -- NULL = nombre vigente
    reason     TEXT NOT NULL,           -- INITIAL | RENAMED | MANUAL
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_usernames_name ON account_usernames(username);
CREATE TABLE IF NOT EXISTS owner_dup_ignored (   -- grupos que el usuario confirma «no es renombrado»
    owner_id TEXT PRIMARY KEY, note TEXT, created_at TEXT NOT NULL);
```

Backfill: una fila `INITIAL` vigente por cuenta.

> Un username antiguo **puede ser reutilizado por otra persona** en Instagram. Por eso el alias no es único globalmente y nunca se aplica en silencio: se pide confirmación.

### Servicio (`library/account_lifecycle.py`, ampliado)

`plan_rename(account_id, new_username, *, keep_location="auto") -> Plan` produce uno de dos escenarios:

**A. Renombrado simple** (no existe carpeta/cuenta con el nombre nuevo)
1. `RENAME_DIR` de `…\old` a `…\new` (mismo padre).
2. `catalog_accounts.username = new`; alias `RENAMED` con `valid_to = hoy` para el nombre antiguo y fila vigente nueva.
3. Espejo `accounts_lite` (UPDATE de esa fila).
4. Si hay lotes DRAFT con URLs manuales que contienen `/stories/<old>/`, se ofrece reescribirlas (las URL de stories generadas salen de `catalog_accounts.username` y cambian solas).

**B. Fusión** (ya existe una cuenta/carpeta con el nombre nuevo — típico cuando se descargó la cuenta con su nuevo nombre antes de darse cuenta)
1. Validar que **ambas tienen el mismo `instagram_user_id`** (o que uno está vacío y el usuario confirma). Si difieren → bloqueante.
2. Elegir carpeta superviviente: por defecto la de la cuenta con **más contenido / más antigua**, editable en el diálogo; se muestran ambas con contadores y fechas.
3. Renombrar la superviviente al nombre nuevo; **fusionar** la otra dentro de ella con la lógica de `sc2.find_directory_merge_conflicts/merge_directory_contents`, mejorada:
   - mismo nombre y tamaño → se omite (idéntico) y se retira del origen;
   - mismo `media_id` con distinto nombre (duplicado semántico) → va a `_duplicates\` de la superviviente, no se borra;
   - mismo nombre y distinto tamaño → sufijo `_1`, `_2`.
   El plan lista cuántos ficheros se mueven, se omiten y chocan **antes** de ejecutar.
4. BD en una transacción: se conserva la fila con más historial, se re-apuntan `batch_accounts.catalog_account_id` de la otra (respetando `UNIQUE(batch_id, catalog_account_id)`: si ambas están en el mismo lote se fusionan sus URLs), se elimina la fila sobrante y se registran los alias.
5. Se escribe un **manifiesto de la fusión** (lista de movimientos) en `fs_operations.payload` para poder deshacer mientras los ficheros sigan en su sitio.

### Detección de candidatos

`library/owner_groups.py: find_owner_groups(app_conn) -> list[OwnerGroup]` agrupa `catalog_accounts` por `instagram_user_id` con ≥ 2 miembros y propone:

| Pista | Criterio | Acción sugerida |
|---|---|---|
| `RENAME_PROBABLE` | un miembro en categoría activa, otros en `09.DELETED`/`06.EXCLUDED` o con `last_media_at` mucho más antiguo | Renombrar/fusionar → el activo conserva el nombre nuevo |
| `SAME_CATEGORY` | todos en la misma categoría activa | Revisar: fusionar |
| `ALL_DELETED` | todos en `09.DELETED` | Ignorar/consolidar |
| `CROSS_CATEGORY` | resto | Revisión manual |

UI: **Catálogo → Revisar ids repetidos…** (`gui/library/owner_groups_dialog.py`): lista de grupos → seleccionar → botones **Resolver…** (abre el plan A/B pre-rellenado), **No es renombrado** (inserta en `owner_dup_ignored`).

### Entradas manuales

- Menú contextual de una cuenta: **Cambió de username…** (campo «nuevo username» + validación `^[A-Za-z0-9._]{1,30}$` y comprobación de existencia).
- Desde el buscador del catálogo: pegar un `ownerId` selecciona la cuenta (el índice `idx_catalog_accounts_owner` de `feat-uc1-3` lo hace instantáneo).

### Resolución de alias (sin reiniciar la app)

- `AccountCatalogService.resolve_username(name)` devuelve la cuenta vigente o, si no existe, las cuentas con ese alias (el editor muestra «@old ahora es @new — ¿usar?»).
- `story_inbox` consulta el alias cuando el username no existe como vigente y mueve a la carpeta actual, marcando el resultado `MOVED_VIA_ALIAS`.
- **Refresco:** toda mutación publica un evento interno `catalog_changed` que llama a `_refresh_catalog()`, recarga el editor y la tabla de cuentas del lote. Esto elimina el «cierra y abre la app».

## Casos borde

- Carpeta en uso (Explorer, antivirus) → el motor deja la operación `FAILED` y se puede reintentar.
- Capitalización distinta solo en el nombre (`User` → `user`): renombrado en dos pasos con nombre temporal (NTFS no distingue mayúsculas).
- Cuentas en lote activo → bloqueante hasta que termine.
- Ambas cuentas en categorías distintas (`00.MODELS-A\GrupoX\old` y `00.FAVORITES\GrupoY\new`): el diálogo pregunta qué ubicación conservar; el resto se mueve con el motor.
- `instagram_user_id` vacío en las dos: no se puede validar → confirmación explícita y registro en el historial.
- Ficheros heredados con username dentro del nombre: no se renombran; el escáner (`feat-uc3-8`) los listará.

## Pruebas

- `tests/library/test_rename_account.py`: renombrado simple, mayúsculas, destino existente, ids distintos (bloqueo).
- `tests/library/test_merge_account.py`: ficheros idénticos, mismo id distinto nombre, conflictos de tamaño, deshacer, ambas en el mismo lote, fallo a mitad.
- `tests/library/test_owner_groups.py`: clasificación de pistas con datos sintéticos que reproduzcan las combinaciones reales.
- `tests/filesystem/test_story_inbox_alias.py`: movimiento con username antiguo.
- `tests/gui/test_catalog_refresh_after_rename.py`: el evento `catalog_changed` actualiza lista, árbol y editor.
- Manual: resolver en una **copia** de `10.TEMP` un renombrado simple y una fusión; luego uno real de `00.FAVORITES`.

## Criterios de aceptación

1. Renombrado simple: carpeta, `bdapp` y `accounts_lite` quedan con el nombre nuevo; la GUI se refresca sin reiniciar.
2. Fusión: sin pérdida de ficheros (suma de ficheros origen = destino + omitidos idénticos + duplicados en `_duplicates`).
3. El alias antiguo se resuelve en el editor y en el story inbox con aviso.
4. Los 69 grupos actuales aparecen clasificados; marcar «No es renombrado» los retira del listado.
5. **Deshacer** funciona para renombrado simple y, mientras los ficheros no se hayan movido de nuevo, para la fusión.

## Documentación a actualizar

`CHANGELOG.md`, `README.md`, `gui/catalog/MODULE.md`, `library/MODULE.md`, `tasks/done/`.

## Fuera de alcance

Detectar renombrados **automáticamente** al descargar (el bot no entrega el id), consultar Instagram, fusionar cuentas con `instagram_user_id` distinto.

## Resultado de la implementación (2026-10-12, v3.7.0)

- Implementado: renombrado simple (misma fila/id), fusión con `MERGE_DIR`/`UNMERGE_DIR` en el motor, alias (`account_usernames`, relleno automático de las cuentas existentes), grupos de ids repetidos con pistas, ignorar grupo, alias en el editor y en el story inbox, refresco de la GUI sin reiniciar, deshacer de renombrado y de fusión.
- **Servicio nuevo `account_rename.py`** (no se amplió `account_lifecycle.py`) para mantener módulos pequeños.
- **Superviviente automático:** primero la ubicación que sigue en uso (no `09.DELETED`/`06.EXCLUDED`/`-Deleted`), después la de más contenido, después la más antigua. Siempre editable en la ventana.
- Una carpeta con el nombre nuevo **sin cuenta** en la app también se fusiona, pero exige confirmación (no hay id que comparar).
- **Deshacer una fusión** no es posible si se unieron filas del mismo lote (se explica el motivo); el índice de ficheros del superviviente se vuelve a generar en el siguiente escaneo.
- **No implementado:** pegar un `ownerId` en el buscador para seleccionar la cuenta (el índice `idx_catalog_accounts_owner` ya existe); la reescritura de URLs de stories es automática (solo lotes borrador/importados) y se informa en la vista previa en lugar de ofrecerse.
- Tus datos actuales solo tienen 2 grupos de id repetido (los 69 de antes se resolvieron con la limpieza manual).
- Sin probar contra `G:` real: probar primero con una cuenta de `10.TEMP`.
