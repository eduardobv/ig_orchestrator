# feat-problem1-5 — Cuenta eliminada: flag + mover su carpeta a «eliminadas»

| | |
|---|---|
| **Dificultad** | 5 / 12 |
| **Cubre** | Problema 1 (parte «eliminada») · proceso manual M3 |
| **Riesgo** | Medio-bajo: un movimiento de carpeta con vista previa y deshacer (usa el motor de `feat-uc2-4`) |
| **Dependencias** | `feat-uc2-4` (motor). Mejor con `feat-uc1-3` (para que cuentas fuera de `FAVORITES` también estén en la app) |
| **Estimación** | 2–3 días |

## Objetivo

Una sola acción «**Marcar como eliminada en Instagram…**» que haga, en un único paso con vista previa:

1. poner a la cuenta el estado de catálogo `DELETED`,
2. mover su carpeta a la carpeta de eliminadas (por defecto `G:\4K Stogram\09.DELETED`),
3. actualizar `bdapp` y el espejo `accounts_lite` con la nueva ruta,

sin tocar a mano ninguna base de datos.

## Valor que entrega por sí solo

- Sustituye el proceso M3 (flag + mover en Explorer + editar `lite` y `complete`).
- El story inbox y `sc2` dejan de apuntar a rutas muertas.
- Se distingue «ocultar» (`DISABLED`) de «ya no existe en Instagram» (`DELETED`), lo que permite filtrar y contar bien.

## Estado actual (evidencia)

- El menú «Delete» del catálogo (`gui/catalog/panel.py:204`) hace `DISABLED`: oculta, pero **no mueve nada**.
- `G:\4K Stogram\09.DELETED` ya existe con **134** cuentas en estructura plana (`09.DELETED\<username>`), por lo que hay un destino y un criterio ya establecidos.
- Solo hay 3 estados de catálogo (`ENABLED`, `INACTIVE`, `DISABLED`) + `ARCHIVED` si se hizo `feat-uc1-3`.
- Señales automáticas disponibles: `bot_errors` tiene `STORIES_NOT_FOUND` (28 URLs), `NOT_FOUND` (5), `PRIVATE_ACCOUNT_STORIES` (2). **Pero** el 74 % de las URLs
  fallidas lo son por «Executed on another instance» (`v3-status.md` §3.2), así que la detección automática es una señal débil: solo se ofrece como **sugerencia**.

## Diseño

### Estado nuevo (migración aditiva)

```sql
INSERT OR IGNORE INTO catalog_account_statuses (id, code, name, description, color_hex, sort_order)
VALUES (5, 'DELETED', 'Deleted on Instagram', 'Account no longer exists; folder archived.', '#d9d2e9', 5);

ALTER TABLE catalog_accounts ADD COLUMN deleted_at TEXT;
ALTER TABLE catalog_accounts ADD COLUMN previous_rel_path TEXT;   -- de dónde venía (para «Restaurar»)
```

Mapeo en el código (`AccountHistoryStatus`): añadir `DELETED` y tratarlo como no seleccionable en el editor, igual que `DISABLED`.

### Ajustes

| Clave `app_settings` | Valor por defecto |
|---|---|
| `library.deleted_folder_rel` | `09.DELETED` |
| `library.deleted_keep_group` | `0` (aplanar; ver Q2 en `v3-status.md`) |

Se editan en Ajustes → Catálogo.

### Flujo (servicio `library/account_lifecycle.py`)

`mark_deleted(account_id, *, dest_rel=None) -> Plan`:

1. Calcula destino = `LIBRARY\<deleted_folder_rel>\<username>`. Si `deleted_keep_group` = 1 → `…\<grupo>\<username>`.
2. Conflictos: destino existe → bloqueante con opciones «Cancelar» o «Sufijo `_2`» (la fusión real es de `feat-problem1-7`).
3. Efectos laterales mostrados en la vista previa:
   - cuenta en **lotes DRAFT** → se ofrece quitarla (o dejarla);
   - cuenta en lote activo → bloqueante;
   - `is_favorite` → se pone a 0;
   - URLs pendientes de la cuenta en lotes cerrados → no se tocan.
4. Ejecuta con `FsOperationService` (`MOVE_DIR`) y, en la misma transacción de commit, `status = DELETED`, `deleted_at = now`, `previous_rel_path`, `folder_id` nuevo.
5. El historial queda en `fs_operations` → **Deshacer** o **Restaurar cuenta…** (mueve de vuelta a `previous_rel_path` y vuelve a `ENABLED`/`ARCHIVED`).

### UI

- Catálogo (menú contextual y menú `Catálogo`): **Marcar como eliminada…** (cambia el actual «Delete» a «Ocultar» para no confundir; etiquetas en `i18n`).
- Diálogo de vista previa común (`gui/library/plan_dialog.py`, de `feat-uc2-4`).
- **Selección múltiple**: pegar o seleccionar varios usernames y ejecutarlo en lote (un plan con N pasos, un solo diálogo).
- Filtro del catálogo: «Eliminadas» (color lila).
- **Sugerencias** (`Catálogo → Sugerir eliminadas…`): lista cuentas cuyo último historial real (excluyendo `Executed on another instance`) sea
  `STORIES_NOT_FOUND` / `NOT_FOUND` en ≥ 2 lotes distintos y sin ninguna URL `COMPLETED` posterior. Nunca actúa sola.

### Migración de lo ya eliminado

Botón único «**Etiquetar 09.DELETED**» (con vista previa): pasa a `DELETED` las cuentas importadas cuyo `rel_path` ya esté bajo `09.DELETED` (134 hoy)
sin mover nada (`previous_rel_path = NULL`).

## Casos borde

- La cuenta no tiene carpeta en disco (`disk_state = MISSING`): solo cambia el estado, con aviso.
- Carpeta en uso por Explorer/antivirus → el `os.rename` falla con `PermissionError`: se queda en `FAILED` con mensaje; reintentar.
- Mismo username ya presente en `09.DELETED` (la cuenta fue eliminada, recreada y vuelta a eliminar): sufijo `_2` con registro del motivo.
- Cuenta con `ownerId` repetido en otra carpeta (probable renombre, no eliminación): la vista previa avisa «este id aparece también en @otro» y sugiere `feat-problem1-7`.

## Pruebas

- `tests/library/test_account_lifecycle.py`: marcar eliminada, restaurar, conflicto, cuenta en lote DRAFT/activo, favorito, multi-selección, carpeta inexistente.
- `tests/db/test_gui_migrations.py`: estado `DELETED` y columnas añadidas una sola vez.
- `tests/gui/test_catalog_delete_flow.py`: etiquetas y estados del menú.
- Manual: marcar como eliminada una cuenta de `10.TEMP` y restaurarla.

## Criterios de aceptación

1. Tras la acción, la carpeta está en `09.DELETED\<username>`, `bdapp` y `accounts_lite` reflejan la nueva ruta y el story inbox ya no la propone para movimientos nuevos.
2. «Deshacer» deja todo como estaba, incluyendo favorito y estado anterior.
3. El editor de lotes no deja añadir una cuenta `DELETED` sin confirmación explícita.
4. «Etiquetar 09.DELETED» clasifica las 134 cuentas sin mover nada.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (estados del catálogo), `gui/catalog/MODULE.md`, `i18n`, `tasks/done/`.

## Fuera de alcance

Borrado físico de carpetas (→ `feat-uc2-12`, con cuarentena), detección automática sin confirmación, renombrados (→ `feat-problem1-7`).
