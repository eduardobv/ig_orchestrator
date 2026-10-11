# feat-uc2-4 — Motor de operaciones de disco + mover / renombrar carpetas desde el catálogo

| | |
|---|---|
| **Dificultad** | 4 / 12 |
| **Cubre** | UC2 (fase 1), cimiento de Problema 1, UC3, UC6 |
| **Riesgo** | Medio: es la primera vez que la app **modifica la biblioteca**. Mitigado con vista previa, diario y deshacer |
| **Dependencias** | `feat-uc1-3` recomendado (sin él solo opera sobre las 334 cuentas gestionadas) |
| **Estimación** | 5–7 días |

## Objetivo

Crear la capa única por la que pasa **toda** modificación de carpetas de la biblioteca, de modo que disco y BD cambien
juntos, con diario recuperable y deshacer; y exponer las dos primeras acciones útiles en el árbol del catálogo:
**mover** una cuenta/carpeta a otra categoría y **renombrar** una carpeta.

## Valor que entrega por sí solo

- Mover una cuenta de `00.FAVORITES\Grupo\user` a `04.INACTIVE` (o entre grupos) con **un clic derecho**: se mueve en disco y se actualiza `bdapp`
  y, mientras exista, el espejo `accounts_lite` (el story inbox y `sc2` siguen funcionando sin pasos manuales).
- Crear carpetas de categoría/grupo desde el árbol.
- Cada operación queda registrada y se puede deshacer; si la app se cierra a mitad, al abrir se ofrece completar o revertir.

## Estado actual (evidencia)

- El menú contextual (`gui/catalog/panel.py:190-207`) solo cambia estados en `bdapp`.
- No hay servicio que mueva carpetas de biblioteca; `filesystem/` mueve ficheros descargados a la carpeta de trabajo (`file_mover.py`) y `sc2` mueve
  carpetas renombradas a la biblioteca (`main.py:129`), con su propio código de fusión.
- Ambas BD de `sc1` se actualizan solo re-ejecutando el script.

## Diseño

### Esquema

```sql
CREATE TABLE IF NOT EXISTS fs_operations (
    id            INTEGER PRIMARY KEY,
    op_group      TEXT    NOT NULL,                 -- uuid: agrupa operaciones de una misma acción de usuario
    seq           INTEGER NOT NULL,                 -- orden dentro del grupo
    op_type       TEXT    NOT NULL,                 -- MKDIR | MOVE_DIR | RENAME_DIR | (futuro: DELETE_DIR, MERGE_DIR…)
    root_id       INTEGER REFERENCES path_roots(id),
    src_rel       TEXT,
    dst_rel       TEXT,
    account_id    INTEGER REFERENCES catalog_accounts(id),
    status        TEXT    NOT NULL,                 -- PLANNED | DISK_DONE | COMMITTED | FAILED | UNDONE
    error         TEXT,
    undo_of       INTEGER REFERENCES fs_operations(id),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fs_operations_group ON fs_operations(op_group, seq);
```

(`root_id`/`*_rel` reutilizan el modelo de rutas de `feat-uc1-3`.)

### Módulo (sin Tk)

```
src/ig_orchestrator/library/
    fsops.py            # FsOperationService: plan_*(), execute(plan), undo(op_group), recover()
    fsops_plan.py       # dataclasses Plan/Step/Conflict; validaciones
    compat_lite.py      # mirror_to_lite(app_conn, lite_path): bdapp → accounts_dir (solo escritura compatible)
```

Contrato de una acción (ej. `move_account(account_id, dest_folder_id)`):

1. **plan** (sin efectos): calcula origen/destino, comprueba existencia, colisiones, mismo volumen, nombre válido en Windows,
   cuentas afectadas (todas las del subárbol si se mueve una carpeta), y devuelve el `Plan` con `Conflict`s.
2. **vista previa** en la GUI (lista «de → a», cuentas afectadas, avisos). Nada se ejecuta hasta confirmar.
3. **ejecución**, por cada `Step`:
   - fila `fs_operations` en `PLANNED` (commit);
   - `os.rename` si es mismo volumen (instantáneo en NTFS, solo metadatos) o `shutil.move` si cambia de unidad (copia + verificación + borrado);
   - estado `DISK_DONE`;
   - en **una transacción SQLite**: actualizar `catalog_accounts.rel_path`, `folder_id`, `catalog_folders`, `disk_state`, y marcar `COMMITTED`;
   - refrescar el espejo `accounts_lite` (mientras `compat.lite.enabled = 1`).
4. **recuperación al arrancar** (`recover()`): operaciones en `PLANNED`/`DISK_DONE` se resuelven comprobando el disco (si el destino existe y el origen no → completar BD;
   si ninguno se movió → marcar `FAILED`); se avisa al usuario.
5. **deshacer**: crea las operaciones inversas con `undo_of` y las ejecuta por el mismo camino; solo si el estado actual coincide con el resultado registrado.

Reglas de seguridad:

- Nunca sobrescribir: si el destino existe → `Conflict(DEST_EXISTS)`; la fusión de carpetas es otra operación (`feat-problem1-7`, `feat-uc2-12`).
- Nunca operar fuera de la raíz `LIBRARY` (validación con `Path.resolve()` y comprobación de prefijo).
- Rechazar mover una carpeta **dentro de sí misma**.
- Con G: desconectada la acción se deshabilita (la raíz está `OFFLINE`).
- Una sola operación de disco simultánea (bloqueo en la app) para evitar carreras con renombrado o story inbox en ejecución.

### Espejo de compatibilidad `bdapp → accounts_lite`

`compat_lite.mirror_to_lite` actualiza `accounts_dir` **solo con las filas afectadas por la operación** (UPDATE/INSERT/DELETE por `legacy_lite_id`/`path`),
nunca recorre la tabla entera. Es el puente que permite que `sc2` y el story inbox sigan vivos hasta `feat-uc1-9`. Se controla con
`app_settings['compat.lite.enabled']` y `['compat.lite.path']`. Si lite no está accesible (G: apagada) la operación **no falla**: la
diferencia queda en `fs_operations` y el espejo se rehace al reconectar (`mirror_pending()`).

### UI

- Menú contextual del catálogo (árbol): **Mover a…** (diálogo de selección de carpeta destino con el árbol de categorías/grupos),
  **Renombrar carpeta…** (solo carpetas de categoría/grupo en esta fase), **Nueva carpeta…**.
  El renombrado de un **username** (cuenta) queda para `feat-problem1-7` porque implica historial de nombres.
- Diálogo de **vista previa** reutilizable (`gui/library/plan_dialog.py`) con conflictos en rojo y botón «Ejecutar» deshabilitado si hay bloqueantes.
- Panel **Historial de operaciones** (`Catálogo → Operaciones de disco…`): tabla de `fs_operations` agrupadas, botón **Deshacer**.
- Arrastrar y soltar en el árbol: **no** en esta fase (ver `feat-uc2-12`).

## Casos borde

- Cuenta que forma parte de un **lote activo** (`batch_accounts.status` en curso) → bloquear el movimiento (el `working_folder_rel` no cambia, pero evita sorpresas).
- Mismo volumen vs distinto volumen (`os.stat().st_dev`): distinto = operación larga, con progreso y cancelación segura (no se borra origen hasta verificar).
- Nombre de carpeta con caracteres no válidos en Windows, nombres reservados (`CON`, `NUL`), espacio/punto final.
- Capitalización: renombrar `User` → `user` en NTFS es una operación de dos pasos (`os.rename` vía nombre temporal).
- Rutas largas: prefijo `\\?\`.
- El árbol tiene `catalog_folders.full_path` único: al mover/renombrar una carpeta se actualizan **todas** las rutas descendientes en una sola transacción (`UPDATE … SET full_path = replace(…)` limitado al prefijo exacto).

## Pruebas

- `tests/library/test_fsops_plan.py`: conflictos, destino existente, dentro de sí misma, fuera de raíz, nombres inválidos.
- `tests/library/test_fsops_exec.py`: éxito, fallo a mitad (inyectando excepción tras `DISK_DONE`), `recover()`, deshacer, idempotencia.
- `tests/library/test_compat_lite.py`: solo se tocan las filas afectadas; lite inaccesible → pendiente y reintento.
- `tests/gui/test_catalog_actions.py`: acciones habilitadas/deshabilitadas según estado de la raíz y de lote.
- Prueba manual en una **copia** de una categoría pequeña (`10.TEMP` tiene 2 cuentas) antes de usarlo en `FAVORITES`.

## Criterios de aceptación

1. Mover una cuenta cambia carpeta en disco, `catalog_accounts.rel_path/folder_id` y `accounts_lite.path` en el mismo gesto; el story inbox la encuentra de inmediato **sin reiniciar la app**.
2. Matar el proceso entre `DISK_DONE` y `COMMITTED` y reabrir → la app lo detecta y deja todo consistente.
3. Deshacer devuelve disco y BD al estado anterior.
4. Intentar mover sobre una carpeta existente muestra el conflicto y no hace nada.
5. Con G: desconectada, las acciones aparecen deshabilitadas con explicación.

## Documentación a actualizar

`CHANGELOG.md`, `README.md`, `gui/catalog/MODULE.md`, `library/MODULE.md`, `docs/modularizacion_v2.md` (tabla `fs_operations`), `tasks/done/`.

## Fuera de alcance

Eliminar carpetas (papelera/cuarentena → `feat-uc2-12`), fusionar carpetas (→ `feat-problem1-7`), renombrar usernames (→ `feat-problem1-7`), escaneo (→ `feat-uc3-8`).
