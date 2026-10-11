# feat-uc3-1 — Auditoría de discrepancias (solo lectura)

| | |
|---|---|
| **Dificultad** | 1 / 12 |
| **Cubre** | UC3 (sincronización), base de UC1, UC2 y Problema 1 |
| **Riesgo** | Ninguno: no escribe en disco ni en ninguna BD |
| **Dependencias** | Ninguna |
| **Estimación** | 1–2 días |

## Objetivo

Mostrar, en un informe, **qué tan desincronizados están hoy** `bdapp`, `bdsc1` (lite y complete) y el disco,
sin cambiar nada. Es el primer paso porque convierte «puede haber alguna discrepancia» en una lista concreta
y accionable, y valida con datos reales las suposiciones del resto de feats (sobre todo Q3 de `v3-status.md`).

## Valor que entrega por sí solo

- Lista exacta de rutas rotas, cuentas huérfanas, ids repetidos y candidatos a renombrado/eliminación.
- Exportable a Markdown/CSV para revisarlo con calma o corregirlo a mano con las acciones actuales.
- Línea base: tras cada feat posterior se puede volver a ejecutar para comprobar que el número de discrepancias baja.

## Qué comprueba

Cada comprobación tiene un código estable (para poder filtrar y, más adelante, enlazar acciones de reparación).

| Código | Comprobación | Fuente | Hoy (medido 2026-10-11) |
|---|---|---|---:|
| `PATH_MISSING` | Ruta de `accounts_dir` que no existe en disco | lite + `os.stat` | 15 |
| `OWNER_DUP` | Mismo `ownerId` con ≥ 2 usernames/carpetas | lite (y complete) | 69 grupos |
| `OWNER_MISMATCH` | `ownerId` distinto entre `bdapp` y lite para el mismo username | bdapp ↔ lite | 4 |
| `FOLDER_MISMATCH` | Carpeta en `bdapp` ≠ carpeta de lite | bdapp ↔ lite | 1 |
| `ONLY_IN_APP` | Cuenta de `bdapp` ausente en lite | bdapp ↔ lite | 5 (DISABLED) |
| `ONLY_IN_LITE` | Cuenta en lite no presente en `bdapp` | bdapp ↔ lite | 902 (informativo: son las no gestionadas por la app) |
| `COMPLETE_STALE` | Fila de complete con ruta ≠ lite, o ausente en uno de los dos | lite ↔ complete | 116 / 138 / 24 |
| `LAST_MODIFIED_MIXED` | Formato de fecha ISO con `T` vs `YYYY-MM-DD HH:MM:SS` en `last_modified`/`modified_at` | lite | verificado: coexisten ambos |
| `NAME_CASE` | Carpeta en disco con distinta capitalización que `username` | lite + stat | por medir |

Para `OWNER_DUP` el informe añade una **pista de clasificación** por grupo (no una decisión):

- `SAME_CATEGORY` (p. ej. los 19 grupos dentro de `00.FAVORITES`): probable renombrado no resuelto o duplicado.
- `DELETED_PAIR` (una carpeta en `09.DELETED` y otra en categoría activa): probable cuenta renombrada cuya carpeta antigua ya se archivó.
- `ALL_DELETED` (11 grupos solo en `09.DELETED`).
- `CROSS_CATEGORY`: resto.

## Diseño

### Módulos nuevos (sin dependencias de Tk)

```
src/ig_orchestrator/library/
    __init__.py
    audit.py          # run_audit(app_conn, lite_path, complete_path|None, *, check_disk=True) -> AuditReport
    audit_report.py   # AuditReport, Finding, render_markdown(), render_csv()
    MODULE.md
```

- `AuditReport`: lista de `Finding(code, severity, username, owner_id, paths, detail)` + resumen por código.
- Apertura de lite/complete **siempre** con `file:...?mode=ro` (mismo patrón que `filesystem/story_inbox._connect_accounts_db`).
- `check_disk=True` hace solo `os.stat` por ruta de cuenta (≈ 1 231 llamadas; medido: 4 721 `stat` en 41 s en frío). Si G: no está
  conectada, la comprobación de disco se omite y el informe lo indica (`DISK_OFFLINE`).
- Se ejecuta en un hilo (patrón de `gui/run/process_runner.py`) para no bloquear Tk.

### UI

- Nueva entrada **`Catálogo → Auditar biblioteca…`** en `gui/chrome/menubar.py` y diálogo `gui/library/audit_dialog.py` con:
  tabla filtrable por código, barra de progreso, botón **Exportar Markdown/CSV**, botón **Abrir en Explorer** (usa `_open_path_in_explorer`).
- CLI: `python -m ig_orchestrator audit-library [--lite PATH] [--complete PATH] [--md out.md]` (permite programarlo y probarlo sin GUI).
- Rutas por defecto: `app_settings.stories.accounts_db_path` (ya existe) para lite y su carpeta vecina para complete.

### Datos y esquema

Ningún cambio de esquema.

## Casos borde

- G: desconectada → solo comparaciones entre BD; mensaje claro.
- `accounts_complete.sqlite` ausente → se omiten los códigos `COMPLETE_*`.
- Mismo username en dos rutas (`UNIQUE(path)` lo permite): se informa como `USERNAME_DUP`.
- Rutas con mayúsculas/minúsculas distintas: comparar con `os.path.normcase`.

## Pruebas

- `tests/library/test_audit.py` con SQLite temporales (lite, complete y bdapp mínimos) y un árbol de carpetas en `tmp_path`:
  un caso por código; G: «desconectada» simulada con ruta inexistente.
- `tests/gui/test_audit_dialog.py` de humo (construcción sin errores).
- Prueba manual: ejecutar contra los datos reales y comparar contra la tabla de arriba.

## Criterios de aceptación

1. El informe sobre tus datos reproduce las cifras de la tabla (±cambios desde el 2026-10-11).
2. Ninguna BD ni carpeta se modifica (comprobable: `mtime` de los `.sqlite` idéntico antes/después).
3. Con G: desconectada la auditoría termina en < 5 s y avisa.
4. Exportación Markdown legible y CSV abrible en Excel.

## Documentación a actualizar (regla del repo)

`CHANGELOG.md`, `README.md` (comando `audit-library`), `src/ig_orchestrator/library/MODULE.md`, mover la tarea a `tasks/done/` al terminar.

## Fuera de alcance

Reparar nada. Las reparaciones llegan en `feat-uc3-8` (sincronización) y `feat-problem1-5/7`.
