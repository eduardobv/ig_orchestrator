# Plan v2.0.0 — GUI, base de datos y aviso Telegram

## Context

La versión activa es `1.31.0` (`src/ig_orchestrator/__init__.py`, `pyproject.toml`). La GUI vive en un único archivo grande (`src/ig_orchestrator/gui/app.py`, tkinter + ttk). El motor de descarga (Telethon, orquestadores, repositorios, CLI `--run` / `--dry-run` / `run_continue`) funciona y no debe reescribirse.

Estado real de `data/orchestrator.sqlite` (~23 MB):

| Tabla v1 | Filas | Lectura |
|---|---:|---|
| `account_history` | 269 | Es el catálogo. Única cosa que se importa a v2. `field1` = ruta destino, `field2` = startInitDate, `user_ig_id` = ownerId. |
| `accounts` | 3384 | Snapshot por lote; 270 usernames distintos. No se migra. |
| `url_jobs` | 28415 | Cola de descargas. No se migra. |
| `download_files` | 42126 | Crece guardando rutas completas repetidas. No se migra. En v2 se rediseña y se puede vaciar. |
| `runs` / `input_batches` | 3216 / 159 | Historial v1. No se migra: v2 arranca sin lotes. |
| `batch_run_queue_*` | 0 | Código v1.31 sí las usa al encadenar lotes. En v2 se recrean vacías con nombres nuevos. |
| `app_config` | 8 | Claves operativas del `.env`. En v2 se rehacen como settings; no hace falta copiar filas. |

Causa de la lentitud al registrar un lote: `commit()` por cada URL y cuenta, SQLite en modo DELETE (no WAL). El árbol del catálogo no es lento por volumen (71 nodos + 269 cuentas).

Objetivo de v2.0.0: GUI unificada, esquema SQLite nuevo **empezando de cero salvo el catálogo**, avisos Telegram configurables. **Nada de esto debe impedir volver a `v1.31.0` y usar `data/orchestrator.sqlite` como ahora.**

Aclaraciones respecto al borrador anterior:

- **No** se importan lotes `PARTIAL`, jobs, runs ni ficheros. Solo catálogo (ids, username, path, ownerId, startInitDate, status, favorito, timestamps).
- Las rutas de fichero no se guardan enteras: un catálogo de raíces + nombre relativo.
- Estados, tipos de publicación y errores del bot viven en tablas de catálogo (id, name, description) consultables y editables.
- Nombres de tablas/campos en inglés alineados con la GUI. Se abandona `job` (un job no es un lote).
- Colores de catálogo configurables con paleta, guardados en hex.
- Toda tabla de la GUI se puede ordenar alfabéticamente.
- Aviso Telegram: destino, texto y disparadores (fin de lote y errores concretos) configurables.

---

## Principio de no-regresión (obligatorio, antes de cualquier tarea)

1. Crear tag `v1.31.0` en el commit actual si aún no existe.
2. Trabajar en rama `v2/orchestrator` (nunca en `master` hasta que v2 esté validada).
3. **No escribir** en `data/orchestrator.sqlite`. Copiarlo a `data/old/` como respaldo de solo lectura.
4. GUI v2 usa `data/orchestrator_gui.sqlite` (`SQLITE_GUI_DB_PATH`).
5. CLI v1 (`--run`, `--dry-run`, `run_continue`, reportes Markdown) sigue apuntando a `SQLITE_DB_PATH`. Dry-run se quita de la GUI, no del motor CLI.
6. Rollback: `git checkout v1.31.0` + `.env` original + `data/orchestrator.sqlite`.

Orden: **0 seguridad → 2 BBDD (esquema + import solo catálogo + inserts masivos) → 1 GUI → 3 Telegram**. Cada paso es una tarea con tests y `CHANGELOG.md`.

---

## Vocabulario (GUI ↔ tablas)

`job` desaparece: confundía con lote. Un **lote** (`batch`) contiene **cuentas** (`batch_accounts`) y cada cuenta tiene **URLs** (`batch_urls`).

| En la GUI | Tabla v2 | Qué es |
|---|---|---|
| Catálogo | `catalog_accounts` + `catalog_folders` | Cuentas conocidas y su árbol de carpetas |
| Editor | (no es tabla) | Formulario de una cuenta del lote |
| Cuentas del lote actual | `batch_accounts` | Cuentas incluidas en el lote en edición/ejecución |
| URLs de una cuenta | `batch_urls` | Cada URL a enviar al bot (antes `url_jobs`) |
| Lotes / ejecuciones | `batches` + `batch_runs` | Lote persistido y cada ejecución |
| Cola de lotes | `batch_queues` + `batch_queue_items` | Encadenar 2+ lotes |
| Estado de ejecución | log en vivo + estados de `batch_urls` | No se persiste el texto del log |
| Ficheros descargados | `downloaded_files` + `path_roots` | Relativo a una raíz; vaciable |
| Configuración | `app_settings` | Idioma, colores, avisos, rutas, reintentos |
| — | `catalog_account_statuses`, `batch_statuses`, … | Diccionarios id/name/description |
| — | `bot_errors` | Mensajes del bot, reintento y aviso |

---

## 1) Plan GUI / UI-UX

### Decisión de diseño

Seguir con **tkinter + ttk**. No migrar a Qt/CustomTkinter: el riesgo de romper flujos ya estables (cola, rename, New account / Update, menús contextuales) es alto.

Aspecto:

- Tema claro tipo Windows 11: `sv-ttk` modo *light*. Fondo `#F7F8FA`, paneles blancos, un acento `#2563EB`, bordes `#E2E5EA`. No gris clásico, no arcoíris.
- Tipografía Segoe UI.
- Colores de catálogo (favorito, inactivo, en lote, hoy, disabled) **ya no van hardcodeados**. Se leen de `catalog_account_statuses.color_hex` y de `app_settings` para los colores de sesión (en lote / hoy). En Configuración, un color picker estándar (`tkinter.colorchooser.askcolor`) guarda el hexadecimal (`#fff2cc`). Cambiar un color no exige reiniciar (se reaplica el tag del listado); cambiar idioma sí.

Iconos:

- No CDN, no GIF. PNG Lucide MIT en `src/ig_orchestrator/gui/assets/icons/` (20×20 y 40×40).
- `tk.PhotoImage` (Python 3.11 soporta PNG). Tooltip i18n en cada icono.
- Set mínimo: `new`, `save`, `folder-open`, `play`, `stop`, `rename`, `terminal`, `plus`, `clipboard-plus`, `clipboard`, `wand`, `eraser`, `list`, `tree`, `trash`, `copy`, `settings`, `sort-asc`.

Idioma:

- Todo el texto GUI por claves. Locales `es` (default) y `en` en JSON.
- Helper `t(key, **kwargs)`. Preferencia `app_settings.ui.language`. Cambio de idioma → persistir y **reiniciar** el proceso.

### Arquitectura de ventana

```
┌ Instagram Orchestrator — Nuevo lote ─────────────────────────────────────┐
│ Archivo  Edición  Ver  Lote  Catálogo  Herramientas  Configuración  Ayuda│
├──────────────────────────────────────────────────────────────────────────┤
│ [＋] [💾] [📂] [▶] [■] │ [✎] [⌨] │  Lote: [descargas_...    ]  Fecha: 2026-08-22 │
├──────────────┬───────────────────────────────────────────────────────────┤
│ Catálogo  [≡]│ Editor                                                    │
│ [buscar] [x] │ [📋＋] [＋] [📋] [✨] [⌫]     Stories  New account  Update  │
│ lista|árbol  │ Username [lidieblush     ]                                │
│              │ URLs                                                      │
│              ├───────────────────────────────────────────────────────────┤
│              │ Cuentas del lote actual   (columnas ordenables A↔Z)       │
├──────────────┴───────────────────────────────────────────────────────────┤
│ [ 42% · 12/28 cuentas · 145/320 URLs · lidieblush ]  clic = log          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Menú

| Menú | Contenido |
|---|---|
| **Archivo** | Nuevo lote · Registrar / actualizar lote · Lotes / ejecuciones… · Exportar · Importar · Salir |
| **Edición** | Pegar/Agregar · Agregar/Actualizar · Pegar · Normalizar · Limpiar editor · Eliminar selección · Eliminar todo |
| **Ver** | Catálogo · Editor · Cuentas del lote · Estado de ejecución… · Vista lista / árbol |
| **Lote** | Ejecutar · Detener · Renombrar · Renombrar manual |
| **Catálogo** | Abrir, Favorito, Inactivo, Delete, Activar |
| **Configuración** | Idioma · Colores de catálogo · Aviso Telegram (destino, plantilla, errores que avisan) · Rutas / reintentos · **Vaciar ficheros descargados** |
| **Ayuda** | Acerca de |

Título de ventana: `Instagram Orchestrator - {modo}`. El label `Modo: NUEVO LOTE...` desaparece.

### Header, editor, dry-run, start date

- Quitar Dry-run de GUI (`--dry-run` CLI se conserva).
- Start date deja de ser editable (header y editor). Label informativo con la fecha de hoy. Al crear lote se persiste `batches.start_date = hoy`.
- Botones de texto de lote → iconos de toolbar: Nuevo, Guardar, Abrir lotes, Ejecutar, Detener, Renombrar, Renombrar manual.
- Editor: toolbar horizontal de iconos (Pegar/Agregar, Agregar/Actualizar, Pegar, Normalizar, Limpiar). Username ~28–32 chars. URLs ~60–70 cols. Checkboxes Stories / New account / Update y el frame ownerId/path **sin modales**.

### Catálogo lista + árbol

- Conmutador icono lista/árbol.
- Árbol: `G:\4K Stogram\00.MODELS-A\Lidiia-Filippova` + username `lidieblush` → raíz `G:\4K Stogram` → `00.MODELS-A` → carpeta `Lidiia-Filippova` → **hoja** `lidieblush`.
- Sin ruta → nodo i18n “Sin ruta”. Solo las hojas cargan el editor.
- Colores desde la tabla de estados + settings (en lote / hoy).

### Ordenación alfabética (todas las tablas GUI)

Hoy solo el encabezado Username de “Cuentas del lote actual” ordena. En v2, **cualquier Treeview/listado**:

- Cuentas del lote: Username, URLs, Estado, Stories, fecha (A↔Z / Z↔A, indicador ▲/▼).
- Diálogo Lotes / ejecuciones (Activos, Históricos, cola).
- Catálogo en modo lista: click en encabezado o control de orden (username A↔Z). En modo árbol: hijos de cada carpeta ordenados A↔Z; opción de ordenar hojas por username.
- Diálogos de URLs completadas / reintento / fallidas.

Implementación única: helper `bind_treeview_sort(tree, columns)` reutilizable. El orden no reescribe `sort_order` de procesamiento del lote (eso sigue siendo el de persistencia); solo cambia la vista.

### Estado de ejecución

- La caja grande desaparece. Barra de una línea con % global; clic abre Toplevel (cerrar / min / max, scroll, seleccionable, copiar con click derecho).
- `Clean` se elimina del frontal.
- Split editor/lote 50/50; el catálogo gana el espacio de la consola.

### Renombrar / Detener

Toolbar global: Detener junto a Ejecutar; Renombrar y Renombrar manual en el grupo post-proceso, misma habilitación que v1.31.

### Configuración de colores

Página/sección “Colores del catálogo”:

- Una fila por estado de `catalog_account_statuses` (Inactivo, Favorito se modela como flag + color en settings o status; Disabled, Enabled).
- Colores de sesión: “En el lote actual”, “Activa hoy”.
- Botón muestra el swatch; clic abre paleta nativa; se guarda `#rrggbb`.

Favorito hoy no es un `status` (es `is_favorite` + ENABLED). En v2 el color de favorito vive en `app_settings.ui.color_favorite` y el de “hoy” / “en lote” igual. Los estados reales (ENABLED, INACTIVE, DISABLED, CHANGED) llevan `color_hex` en su tabla.

### Tareas GUI

1. **T2.1** Shell: menú, i18n, sv-ttk, iconos. Comportamiento idéntico.
2. **T2.2** Header iconos, quitar Dry-run y Start date editable, título de ventana.
3. **T2.3** Editor compacto (iconos frecuentes, checkboxes intactos).
4. **T2.4** Log → status bar + modal. Split 50/50.
5. **T2.5** Mover Renombrar / Manual / Detener.
6. **T2.6** Catálogo árbol + colores desde settings/BBDD.
7. **T2.7** Configuración: idioma, colores (paleta), Telegram, vaciar `downloaded_files`.
8. **T2.8** Sort A↔Z en todos los Treeview.

No tocar: flujo New account / Update, cola, export/import, contextuales (salvo i18n y sort).

---

## 2) Plan de base de datos

### Decisión: fichero nuevo, arranque de cero salvo catálogo

`data/orchestrator_gui.sqlite`, `PRAGMA user_version = 100`.

Importador **solo** `account_history` → `catalog_folders` + `catalog_accounts`, **conservando `id`** de cada cuenta para no romper referencias mentales / ownerId. No se copian lotes, URLs, runs, queues ni `download_files`. El primer “Nuevo lote” en v2 es el lote 1 de esa BBDD.

CLI no-GUI sigue en `orchestrator.sqlite`. La GUI v2 nunca lo abre en escritura. No hay “histórico v1” dentro de v2 (fuera de alcance salvo que más adelante se pida un visor read-only).

### Tablas de diccionario (estados y tipos)

Cada una: `id`, `code` (estable para el motor), `name` (etiqueta GUI), `description` (para que al abrir la tabla se entienda), `sort_order`, `is_active`. Las de catálogo añaden `color_hex`.

Semilla inicial (INSERT en schema); el usuario puede añadir filas nuevas (p. ej. un estado) sin tocar código, siempre que el motor ignore `code` desconocidos de forma segura.

```text
catalog_account_statuses   ENABLED, INACTIVE, DISABLED, CHANGED
batch_statuses             DRAFT, IMPORTED, PROCESSING, COMPLETED, PARTIAL, FAILED, AWAITING_RENAME
batch_account_statuses     PENDING, PROCESSING, COMPLETED, FAILED, PARTIAL
batch_url_statuses         PENDING, SENT_TO_BOT, WAITING_DOWNLOAD, DOWNLOADED,
                           RETRY_PENDING, FAILED_TEMPORARY, FAILED_FINAL, COMPLETED
publication_types          POST, REEL, STORY, HIGHLIGHTS, UNKNOWN
url_sources                GENERATED_STORY, INPUT_URL
media_types                IMAGE, VIDEO, UNKNOWN
queue_statuses             DRAFT, RUNNING, PAUSED, AWAITING_RENAME, COMPLETED, CANCELLED
queue_item_statuses        PENDING, RUNNING, COMPLETED, REMOVED, SKIPPED
downloaded_file_statuses   DETECTED, MOVED, CLASSIFIED, FINALIZED
```

Vista opcional `v_all_statuses` (`UNION ALL` de dominio, id, code, name, description) para inspeccionar todo de un vistazo en DB Browser.

Las tablas de hecho (`catalog_accounts.status_id`, `batches.status_id`, `batch_urls.status_id`, `batch_urls.publication_type_id`, …) referencian **id entero**, no el texto. El adaptador al motor sigue exponiendo el `StrEnum` actual (`AccountStatus.PENDING`) resolviendo por `code`, así no se reescribe el orquestador.

### Errores del bot (`bot_errors`)

Hoy están hardcodeados en `bot_response_parser.py`. En v2:

```text
id
code                 STORIES_NOT_FOUND, MEDIA_NOT_FOUND, OVERLOADED, GEOBLOCK, PRIVATE_ACCOUNT, NOT_FOUND, …
match_pattern        texto o regex (p. ej. Stories for {username} not found)
match_kind           CONTAINS | REGEX
is_retryable         0/1
max_retries_override NULL = usar MAX_RETRIES global; 1 = tope propio (Media not found)
notify_on_match      0/1  → dispara aviso Telegram (plan 3)
notify_template      texto opcional de ese aviso; placeholders {username} {url} {error}
description
is_active            0/1  (desactivar sin borrar)
sort_order
```

Semilla con los errores conocidos de v1. Desde Configuración se pueden editar patrones, marcar “avisar” y añadir filas si el bot cambia el texto. El parser lee la tabla al iniciar el run (no en cada URL) y cachea.

### Raíces de path (nada de prefijos repetidos)

No guardar `C:\Users\eduba\Downloads\DW\Telegram_Desktop\3649803477901056672.mp4`.

```text
path_roots
  id, code (TELEGRAM_DESKTOP | WORKING | FINAL_BASE), path
  UNIQUE(code)

downloaded_files
  id
  batch_url_id
  root_id              → path_roots
  relative_path        3649803477901056672.mp4
                       o username\reels\file.mp4
  media_type_id
  extension            mp4
  file_size
  sha256               opcional; se puede omitir si no aporta a GUI
  status_id
  created_at
```

Ruta absoluta = `path_roots.path / relative_path` en Python (`pathlib`). Las 8 claves operativas actuales de carpeta viven en `path_roots` + `app_settings`, no repetidas por fichero.

Tras completar un lote y (si aplica) renombrar/mover: **vaciar** `downloaded_files` de ese lote por defecto. Además, en Configuración: botón “Vaciar tabla de ficheros descargados” (TRUNCATE/DELETE de toda la tabla o de lotes ya COMPLETED). Los estados de las URLs (`batch_urls`) no se tocan.

`generated_story_url` no se persiste: se calcula. `username` no se duplica en `batch_accounts`: FK a `catalog_accounts.id`.

### Esquema v2 (resumen)

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 100;

CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE path_roots (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- diccionarios: ver sección anterior (id, code, name, description, ...)

CREATE TABLE catalog_folders (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES catalog_folders(id),
    name TEXT NOT NULL,
    full_path TEXT NOT NULL UNIQUE,
    depth INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE catalog_accounts (
    id INTEGER PRIMARY KEY,            -- se conserva el id v1
    username TEXT NOT NULL COLLATE NOCASE,
    instagram_user_id TEXT,
    folder_id INTEGER REFERENCES catalog_folders(id),
    start_init_date TEXT,
    status_id INTEGER NOT NULL REFERENCES catalog_account_statuses(id),
    is_favorite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_catalog_accounts_username
    ON catalog_accounts(username COLLATE NOCASE);
CREATE INDEX idx_catalog_accounts_folder ON catalog_accounts(folder_id);
CREATE INDEX idx_catalog_accounts_status ON catalog_accounts(status_id);

CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    status_id INTEGER NOT NULL REFERENCES batch_statuses(id),
    start_date TEXT NOT NULL,          -- hoy al crear; no editable en GUI
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE batch_accounts (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    catalog_account_id INTEGER NOT NULL REFERENCES catalog_accounts(id),
    download_stories INTEGER NOT NULL DEFAULT 0,
    is_new_account INTEGER NOT NULL DEFAULT 0,
    is_catalog_update INTEGER NOT NULL DEFAULT 0,
    rename_owner_id TEXT,
    rename_start_init_date TEXT,
    rename_destination_path TEXT,
    working_folder_rel TEXT,           -- relativo a path_root WORKING
    status_id INTEGER NOT NULL REFERENCES batch_account_statuses(id),
    sort_order INTEGER NOT NULL,       -- orden de procesamiento, no el de la vista
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, catalog_account_id)
);

CREATE TABLE batch_urls (
    id INTEGER PRIMARY KEY,
    batch_account_id INTEGER NOT NULL REFERENCES batch_accounts(id),
    batch_run_id INTEGER REFERENCES batch_runs(id),
    url TEXT NOT NULL,
    publication_type_id INTEGER NOT NULL REFERENCES publication_types(id),
    source_id INTEGER NOT NULL REFERENCES url_sources(id),
    status_id INTEGER NOT NULL REFERENCES batch_url_statuses(id),
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER,
    last_error_id INTEGER REFERENCES bot_errors(id),
    last_error_text TEXT,              -- mensaje original del bot
    non_retryable INTEGER NOT NULL DEFAULT 0,
    sent_message_id INTEGER,
    started_at TEXT,
    finished_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_account_id, url)
);

CREATE TABLE downloaded_files ( /* root_id + relative_path, vaciable */ );
CREATE TABLE batch_runs ( /* una ejecución de un lote */ );
CREATE TABLE duplicate_urls ( /* duplicados detectados al pegar */ );
CREATE TABLE batch_queues ( /* cola GUI */ );
CREATE TABLE batch_queue_items ( /* ítems de cola */ );
CREATE TABLE bot_errors ( /* patrones + notify_on_match */ );
```

`app_settings` incluye: `ui.language`, `ui.theme`, `ui.catalog_view`, visibilidad de paneles, geometría, `ui.color_in_batch`, `ui.color_today`, `ui.color_favorite`, `notify.enabled`, `notify.target`, `notify.template_batch_done`, `retention.downloaded_files` (`on_complete` | `keep`).

### Capa de código

El orquestador sigue hablando de `Account.username` y de ids de URL. Adaptadores:

- `batch_account_repository` JOIN a `catalog_accounts` hidrata el dataclass `Account` actual.
- `batch_url_repository` sustituye a `UrlJobRepository` por dentro; el processor recibe el mismo `UrlJob` (o se aliasa el modelo; no se reescribe Telethon).
- `build_story_url(username)` al crear `batch_urls` con `source = GENERATED_STORY`.
- Catálogo: una query indexada; árbol lazy por `folder_id`.

### Inserts rápidos

1. `connect()`: WAL, `synchronous=NORMAL`, `foreign_keys=ON`.
2. Guardar lote = **una transacción** + `executemany` de `batch_urls`.
3. Sin `commit()` dentro de `create()` fila a fila.
4. Objetivo de test: 100 cuentas × 20 URLs < 1 s en SQLite temporal.

### Tareas BBDD

1. **T2.D1** Tag `v1.31.0`, backup, `SQLITE_GUI_DB_PATH`, WAL.
2. **T2.D2** `schema_v2.sql` con diccionarios sembrados + `bot_errors` + `path_roots`. Tests de init vacío.
3. **T2.D3** Importador **solo catálogo** (conservar ids, partir `field1` en folders). Tests con fixture de `account_history`.
4. **T2.D4** Repositorios v2 + adaptadores al modelo actual. Tests.
5. **T2.D5** `save_batch_draft` transaccional + `executemany`.
6. **T2.D6** GUI arranca contra el fichero nuevo (catálogo lleno, cero lotes).
7. **T2.D7** Vaciar `downloaded_files` al completar/renombrar + acción de Configuración.

---

## 3) Plan de aviso Telegram

### ¿Puedo enviarme un mensaje a mí mismo?

**Sí.** El cliente Telethon es un usuario real. `send_message("me", texto)` escribe en **Mensajes guardados** y el móvil muestra la notificación nativa.

También vale un contacto (`@username`, teléfono o `chat_id`). Todo configurable.

### Dónde enviar (sesión ocupada)

La GUI lanza el lote en subproceso y ese proceso **ya tiene Telethon abierto**. Por eso los avisos salen **desde el orquestador**, no desde Tk al terminar:

- Fin de lote / fin de cola: el mismo cliente envía y luego cierra.
- Error del bot con `bot_errors.notify_on_match = 1`: se envía en caliente, sin pelear el `.session`.
- Si Telethon no está (p. ej. prueba desde Configuración con la GUI idle): `notify_service` abre-envía-cierra.

Fallo de envío: log, **nunca** marca el lote como fallido.

### Qué es configurable (menú Configuración → Aviso Telegram)

| Campo | Default | Uso |
|---|---|---|
| Activar avisos | off | Master switch |
| Destino | `me` | `me`, `@usuario` o id numérico |
| Plantilla fin de lote | texto i18n con `{batch_name}`, `{batch_id}`, `{accounts_done}`, `{accounts_total}`, `{urls_ok}`, `{urls_failed}` | Mensaje a medida |
| Plantilla fin de cola | similar + `{queue_id}` | Resumen al encadenar |
| Errores que avisan | los marcados en `bot_errors.notify_on_match` | Lista editable (checkbox por error) + plantilla `{username} {url} {error}` |
| Enviar prueba | botón | “Prueba de notificación” al destino actual |

No avisar si el usuario pulsó Detener. La GUI ya no tiene dry-run.

Ejemplo de plantilla:

```
Instagram Orchestrator
Lote {batch_name} (id={batch_id}) completado
Cuentas: {accounts_done}/{accounts_total} · URLs ok: {urls_ok} · fallidas: {urls_failed}
Siguiente: Renombrar
```

### Tareas Telegram

1. **T2.T1** `notify_service` + envío con cliente ya abierto o efímero. Tests con fake client.
2. **T2.T2** Orquestador: fin de lote/cola + match de `bot_errors.notify_on_match`.
3. **T2.T3** UI Configuración: destino, plantillas, checkboxes de errores, botón de prueba.

---

## Archivos críticos

Nuevos: `db/schema_v2.sql`, `db/gui_migrations.py`, `db/catalog_importer.py`, `telegram/notify_service.py`, `gui/i18n.py`, `theme.py`, `icons.py`, `menus.py`, `gui/locales/{es,en}.json`, `gui/assets/icons/`, `gui/widgets/*`, `tasks/Tarea_v2_*.md`.

Modificar: `gui/app.py` (partir), `account_catalog_service.py`, `batch_draft_service.py`, `batch_creation_service.py` (transacción), `connection.py` (WAL), repositorios (adaptadores), `bot_response_parser.py` (leer `bot_errors`), `settings.py`, versiones → `2.0.0` al cerrar, `Agents.md`, `CHANGELOG.md`, `README.md`, `requirements.txt` (`sv-ttk`).

Reutilizar sin reescribir: `orchestration/*` (enganche mínimo de notify), `telegram_client.py` (añadir `send_message_to(target, text)`), cola/resume/rename/export GUI.

---

## Verificación

- `python -m pytest -q` en cada tarea.
- Tests nuevos: importador de catálogo conserva ids y parte `G:\4K Stogram\00.FAVORITES\Valeria-Makusheva` → hoja `lerabuns`; diccionarios sembrados; bulk insert; vaciado de `downloaded_files`; notify fake; sort de Treeview; claves i18n es+en.
- Manual GUI:
  1. v2 arranca: catálogo presente, **cero lotes**, `orchestrator.sqlite` mtime intacto.
  2. Registrar ~200 URLs: inmediato.
  3. Pegar/Agregar, checkboxes, sin modales de alta.
  4. Lista/árbol, filtro, colores desde paleta, sort A↔Z en lote y en Lotes.
  5. Ejecutar lote pequeño, barra de estado, modal log, Detener.
  6. Completar: aviso a Saved Messages (o destino elegido); tabla de ficheros vacía o vaciable; Renombrar se habilita.
  7. Forzar un error marcado como “avisar” y comprobar el mensaje.
  8. Cambio de idioma → reinicio.
  9. Drill rollback: `git checkout v1.31.0` y GUI/CLI v1 sobre el SQLite viejo.

Cierre v2.0.0: tareas GUI + BBDD + Telegram verdes, drill de rollback en `CHANGELOG.md`, tag `v2.0.0`.

---

## Fuera de alcance v2.0.0

- Migrar lotes, URLs, runs o `download_files` de v1.
- Qt / web / tema oscuro / idiomas extra.
- Eliminar CLI, `--dry-run` del motor o reportes Markdown no-GUI.
- Escribir en `data/orchestrator.sqlite`.
- Movimiento final a `G:\4K Stogram` más allá del renombrador actual.


## Context

La versión activa es `1.31.0` (`src/ig_orchestrator/__init__.py`, `pyproject.toml`). La GUI vive en un único archivo grande (`src/ig_orchestrator/gui/app.py`, tkinter + ttk). El motor de descarga (Telethon, orquestadores, repositorios, CLI `--run` / `--dry-run` / `run_continue`) funciona y no debe reescribirse.

Estado real de `data/orchestrator.sqlite` (~23 MB):

| Tabla | Filas | Lectura |
|---|---:|---|
| `account_history` | 269 | Es el catálogo. `field1` es la ruta destino (`G:\4K Stogram\00.FAVORITES\Valeria-Makusheva`). 258 con ruta, 11 sin ella. |
| `accounts` | 3384 | Una fila por cuenta **en un lote**, no el catálogo. Solo 270 usernames distintos. `generated_story_url` vacío en 1749; `final_destination_folder` vacío en todas. |
| `url_jobs` | 28415 | Cola real de descargas. Lotes grandes llegan a 700–860 URLs. |
| `download_files` | 42126 | Crece en cada descarga. Lo usa el motor (`bot_conversation_service`, `file_mover`), no solo el reporte Markdown. |
| `runs` | 3216 | Historial de ejecuciones. |
| `input_batches` | 159 | 134 `COMPLETED`, 25 `PARTIAL`. |
| `batch_run_queues` / `batch_run_queue_items` | 0 | Vacías hoy, pero **sí se usan** en GUI v1.31.0 (`gui/batch_queue_service.py`) cuando se encadenan lotes. |
| `app_config` | 8 | Solo claves operativas copiadas del `.env`. No hay idioma, tema ni avisos. |

Causa de la lentitud al registrar un lote: `UrlJobRepository.create` y `AccountRepository.create` hacen `commit()` **por cada fila**, y `_populate_batch` inserta cuenta a cuenta / URL a URL. SQLite además abre en modo DELETE (no WAL). El árbol del catálogo **no** es lento por volumen (71 nodos de carpeta + 269 cuentas): es lento el modelo (`field1` opaco, `list_all()` sin árbol, y `list_usernames_active_on_date` barre `accounts` y `runs`).

Objetivo de v2.0.0: GUI de escritorio unificada y más usable, esquema SQLite normalizado y rápido, aviso Telegram al terminar un lote. **Nada de esto debe impedir volver a `v1.31.0` y usar `data/orchestrator.sqlite` como ahora.**

---

## Principio de no-regresión (obligatorio, antes de cualquier tarea)

1. Crear tag `v1.31.0` en el commit actual si aún no existe.
2. Trabajar en rama `v2/orchestrator` (nunca en `master` hasta que v2 esté validada).
3. **No escribir** en `data/orchestrator.sqlite` desde v2. Copiarlo a `data/old/` como respaldo de solo lectura.
4. La GUI v2 usa un fichero nuevo: `data/orchestrator_gui.sqlite` (configurable por `SQLITE_GUI_DB_PATH`).
5. El motor CLI (`--run`, `--dry-run`, `run_continue`, reportes Markdown) sigue existiendo y apunta por defecto a `SQLITE_DB_PATH` (el fichero v1). Dry-run **se quita de la GUI**, no del motor.
6. Si v2 falla: `git checkout v1.31.0` + el `.env` original + `data/orchestrator.sqlite` = comportamiento idéntico.

Orden de implementación recomendado: **0 (seguridad) → 2 (BBDD, al menos WAL + inserts masivos + esquema nuevo) → 1 (GUI sobre el nuevo esquema) → 3 (Telegram)**. La GUI en árbol y la carga rápida dependen del esquema; hacer el rediseño visual primero sobre el esquema viejo duplicaría trabajo.

Cada bloque de abajo es una serie de tareas pequeñas (una por PR/commit), con tests, `CHANGELOG.md` y sin mezclar refactors ajenos.

---

## 1) Plan GUI / UI-UX

### Decisión de diseño

Seguir con **tkinter + ttk**. No migrar a Qt/CustomTkinter: el riesgo de romper flujos ya estables (cola, rename, histórico, New account / Update, menús contextuales) es alto para el beneficio visual.

Aspecto:

- Tema claro tipo Windows 11: dependencia `sv-ttk` (Sun Valley), modo *light*. Fondo `#F7F8FA`, paneles blancos, un solo acento `#2563EB`, bordes `#E2E5EA`. No gris clásico, no arcoíris.
- Conservar la semántica de color del catálogo (favorito / inactivo / en lote / hoy / disabled), suavizada al tema claro.
- Tipografía: Segoe UI en Windows.

Iconos (respuesta a “¿descargar gifs / online / librería?”):

- **No** cargar iconos de internet en runtime (la app debe funcionar offline).
- **No** GIFs.
- Empaquetar ~24 PNG 20×20 (y @2x 40×40) de [Lucide](https://lucide.dev) (MIT) en `src/ig_orchestrator/gui/assets/icons/`.
- Cargarlos con `tk.PhotoImage` (Python 3.11 + Tcl 8.6 soporta PNG; no hace falta Pillow).
- Cada botón-icono lleva **tooltip** con el texto i18n (el usuario deja de ver la etiqueta, no el significado).
- Mapa mínimo: `new`, `save`, `folder-open`, `play`, `stop`, `rename`, `terminal`, `plus`, `clipboard-plus`, `clipboard`, `wand` (normalizar), `eraser`, `list`, `tree`, `trash`, `copy`, `settings`.

Idioma:

- Unificar **todo** el texto de GUI a claves i18n. Hoy está mezclado (`Batch name` / `Start date` / `Dry-run` / `Ready` vs `Nuevo lote` / `Catalogo` / `Ejecutar`).
- Locales `es` (default) y `en` en JSON: `src/ig_orchestrator/gui/locales/{es,en}.json`.
- Helper `t(key, **kwargs)` (stdlib, sin gettext ni dependencias).
- Preferencia en `app_settings.ui.language`. Al cambiar idioma: persistir y **reiniciar el proceso** (`os.execv` del mismo `python -m ig_orchestrator gui`), como pediste.
- Los textos del motor/log (inglés técnico de Telethon, `GUI_ITEM_PROGRESS`) se dejan en el idioma original del motor; la barra de estado y el modal los presentan traducidos cuando sean mensajes nuestros.

### Arquitectura de ventana (wireframe)

```
┌ Instagram Orchestrator — Nuevo lote ─────────────────────────────────────┐
│ Archivo  Edición  Ver  Lote  Catálogo  Herramientas  Configuración  Ayuda│
├──────────────────────────────────────────────────────────────────────────┤
│ [＋] [💾] [📂] [▶] [■] │ [✎] [⌨] │  Lote: [descargas_...    ]  Fecha: 2026-08-22 │
├──────────────┬───────────────────────────────────────────────────────────┤
│ Catálogo  [≡]│ Editor                                                    │
│ [buscar] [x] │ [📋＋] [＋] [📋] [✨] [⌫]     Stories  New account  Update  │
│              │ Username [lidieblush     ]                                │
│ lista|árbol  │ URLs (textarea, ~70 chars visibles)                       │
│ más alto     ├───────────────────────────────────────────────────────────┤
│ y más ancho  │ Cuentas del lote actual                                   │
│              │ tabla (igual)                                             │
│              │ [Eliminar] [Guardar selección] [Eliminar todo]            │
├──────────────┴───────────────────────────────────────────────────────────┤
│ [ 42% · 12/28 cuentas · 145/320 URLs · lidieblush ]  clic = log          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Menú (todo el texto vive aquí)

| Menú | Contenido |
|---|---|
| **Archivo** | Nuevo lote · Registrar / actualizar lote · Lotes / ejecuciones… · Exportar lote · Importar lote · Salir |
| **Edición** | Pegar/Agregar · Agregar/Actualizar · Pegar · Normalizar · Limpiar editor · Eliminar selección · Eliminar todo |
| **Ver** | Catálogo (check) · Editor (check) · Cuentas del lote (check) · Estado de ejecución… · Vista catálogo: lista / árbol |
| **Lote** | Ejecutar · Detener · Renombrar · Renombrar manual |
| **Catálogo** | (acciones del contextual también aquí: Abrir, Favorito, Inactivo, Delete, Activar) |
| **Herramientas** | mismas de Lote si se prefiere agrupar; Rename puede vivir en los dos |
| **Configuración** | Idioma (es/en) · Aviso Telegram · Tema claro (único en v2.0) · Rutas / reintentos (lectura + edición de las 8 claves actuales de `app_config`) |
| **Ayuda** | Acerca de (versión) |

Al ocultar un panel desde **Ver**, el `PanedWindow` reparte el espacio. Estado de visibilidad se guarda en `app_settings`.

### Barra de herramientas (solo iconos)

Agrupación visual con separadores:

1. Lote: Nuevo · Guardar · Abrir lotes · Ejecutar · Detener.
2. Post-proceso: Renombrar · Renombrar manual.
3. Identidad del lote: `Entry` compacto de nombre + **fecha de hoy en solo lectura** (label, no Entry). El `start_now_date` sigue persistiendo en SQLite como hoy; ya no es editable ni en el header ni en el editor.

El título de ventana pasa a ser `Instagram Orchestrator - {modo}`:

- `Nuevo lote`
- `Editando lote · {nombre} (id=N)`
- `En ejecución · {nombre} (id=N)`
- `Histórico · {nombre} (id=N)`

El label actual `Modo: NUEVO LOTE...` (fila 1 del header) **desaparece**.

### Editor (accesibilidad de lo más usado)

- Quitar la columna izquierda de botones de texto.
- Toolbar **horizontal de iconos** pegada al título “Editor”: Pegar/Agregar, Agregar/Actualizar, Pegar, Normalizar, Limpiar. Ese es el grupo de mayor frecuencia; va primero, a un clic, sin recorrer menú.
- Username: `Combobox` ~28–32 caracteres (usernames reales caben; el catálogo a la izquierda es el sitio para leer nombres largos).
- URLs: ancho pensado para `https://www.instagram.com/p/DRnU6pdjoXg/?img_index=1` (~60–70 cols). Highlights más largas se recorren con scroll horizontal (`wrap="none"`, ya está).
- **Se mantienen** exactamente los checkboxes `Stories`, `New account`, `Update` y el `LabelFrame` “Datos de cuenta nueva” (ownerId, startInitDate, path). Sin modales nuevos para introducir esa info.
- Quitar el Entry “Start date” del editor.

### Catálogo: lista + árbol

Un botón-icono junto al título conmuta `list` ↔ `tree` (preferencia persistida).

- **Lista**: comportamiento actual (filtro, colores, click, doble click Chrome, menú contextual).
- **Árbol** (`ttk.Treeview` con `show="tree"`):
  - Parsear `field1` de forma Windows-aware: `G:\4K Stogram\00.MODELS-A\Lidiia-Filippova` → raíz `G:\4K Stogram` · hijo `00.MODELS-A` · carpeta cuenta `Lidiia-Filippova` · **hoja** `lidieblush` (`user_name`).
  - Cuentas sin `field1` bajo un nodo i18n “Sin ruta”.
  - Solo las hojas son seleccionables como username (mismos binds que la lista).
  - Carpetas no disparan carga al editor; expand/collapse sí.
  - Colores de hoja iguales a la lista.
  - Filtro: si hay match exacto de username, expandir y seleccionar esa hoja + peers de la misma carpeta cuenta (equivalente al filtro actual por `field1`).

Implementación inicial del árbol puede agrupar en memoria (269 filas). En cuanto exista el esquema v2, el árbol se alimenta de `catalog_folders` + `catalog_accounts` (lazy: hijos al expandir).

### Cuentas del lote actual

Misma tabla, mismas columnas (salvo que “start date” puede ocultarse porque ya no se edita; si se deja, es informativa). Mismos botones `Eliminar` / `Guardar selección` / `Eliminar todo` y el menú contextual (Completar, URLs, Abrir carpeta). El split vertical Editor / Lote pasa de 3:2 a **1:1**. El catálogo gana el espacio que hoy come la consola.

### Estado de ejecución (la caja grande desaparece del frontal)

- Sustituir el `Text` de 8 líneas + botón Clean por una **barra de estado de una línea** (ttk.Label o Button plano):
  `42% · 12/28 cuentas · 145/320 URLs · lidieblush`
- Clic abre un **Toplevel** “Estado de ejecución”:
  - barra de título con cerrar, minimizar, maximizar (Toplevel nativo Windows).
  - `Text` con scroll, seleccionable.
  - menú contextual Copiar / Copiar todo / Limpiar.
  - no modal bloqueante (`grab_set` no); se puede seguir trabajando.
- El log en memoria se sigue acumulando aunque el modal esté cerrado.
- `Clean` del frontal se elimina; “Limpiar” vive en el menú del modal y en Edición si se quiere.

### Reubicación de Renombrar / Renombrar Manual / Detener / Clean

| Control | Sitio v2 | Motivo |
|---|---|---|
| Detener | Toolbar global, junto a Ejecutar; deshabilitado en idle | Acción de emergencia, siempre visible |
| Renombrar | Toolbar grupo post-proceso; habilitado solo cuando el lote/cola está listo (igual que hoy) | Es el siguiente paso del flujo, no un pie de consola |
| Renombrar Manual | Toolbar al lado de Renombrar + menú Lote | Inspección/copia del comando; uso menos frecuente |
| Clean | Eliminado del frontal | El log ya no ocupa el frontal |

### Dry-run en GUI

- Quitar checkbox, `dry_run_var` y el paso de `dry_run=True` en `build_run_continue_command` desde la GUI.
- Conservar `--dry-run` en CLI, `BatchOrchestratorConfig.dry_run` y tests del motor.
- `last_run_was_dry_run` en GUI se elimina; la cola nunca se pausará por dry-run porque la GUI ya no lo lanza.

### Despiece de `app.py`

Hoy `InstagramOrchestratorApp` concentra layout, i18n inexistente, catálogo, ejecución y diálogos. Para v2, extraer (sin cambiar comportamiento):

- `gui/i18n.py`
- `gui/theme.py` (sv-ttk + paleta + tooltips)
- `gui/icons.py`
- `gui/widgets/toolbar.py`, `status_bar.py`, `log_window.py`
- `gui/widgets/catalog_list.py`, `catalog_tree.py`
- `gui/menus.py`

`app.py` queda como orquestador de widgets y callbacks.

### Tareas GUI (paso a paso)

1. **T2.1 Shell**: menú + i18n es/en + tema sv-ttk + iconos empaquetados. Comportamiento idéntico. Reinicio al cambiar idioma.
2. **T2.2 Header**: quitar Dry-run, Start date editable, botones de texto de lote, label “Modo:…”. Toolbar de iconos + título de ventana. Fecha informativa.
3. **T2.3 Editor compacto**: iconos de acciones frecuentes, username/URLs más estrechos, checkboxes intactos, sin start date.
4. **T2.4 Log → status bar + modal**. Quitar Clean. Split 50/50. Catálogo más alto/ancho.
5. **T2.5 Mover Renombrar / Manual / Detener** a toolbar. Verificar habilitación actual (`batch_ready_for_rename`, `cancel_button`).
6. **T2.6 Catálogo árbol** (conmutador lista/árbol) sobre el servicio de catálogo.
7. **T2.7 Configuración** en menú: idioma, aviso Telegram (UI; el envío es el plan 3), paths/reintentos.

No tocar en GUI v2.0: flujo New account / Update, cola de lotes, histórico solo lectura, export/import, menús contextuales de catálogo y de lote (salvo traducir).

---

## 2) Plan de base de datos

### Decisión: fichero nuevo, no migrar in-place

Usar `data/orchestrator_gui.sqlite` (esquema `user_version = 100` para no chocar con el `3` de v1).

Razones:

- Rollback real: v1.31.0 sigue abriendo `orchestrator.sqlite` sin migraciones v2 aplicadas a medias.
- El GUI no necesita 42k `download_files` históricos ni 3.2k `runs` para arrancar.
- Permite índices y FKs por id sin pelear con filas legacy (`field1`/`field2`, `generated_story_url` derivado, `final_destination_folder` vacío).

Importador de arranque (una vez, idempotente):

1. Copia de seguridad de `orchestrator.sqlite`.
2. Importa **catálogo** (`account_history` → `catalog_folders` + `catalog_accounts`).
3. Importa `app_config` operativa.
4. Importa lotes **reanudables** (`PARTIAL`, `DRAFT`, `IMPORTED`, `FAILED`, `AWAITING_RENAME`) con sus `accounts` + `url_jobs` + metadatos de rename. Así no se pierde trabajo a medias.
5. No importa por defecto: `download_files` históricos, lotes `COMPLETED`, `runs` de v1. El histórico v1 se consulta en solo lectura (menú Lotes puede ofrecer “Abrir histórico v1…” leyendo el fichero viejo con conexión aparte, sin escribir).

CLI no-GUI sigue usando `SQLITE_DB_PATH`. La GUI usa `SQLITE_GUI_DB_PATH`. El motor de orquestación es el mismo; cambia el path y los repositorios.

### Diagnóstico de tablas actuales

- **`account_history`**: catálogo mal nombrado. `field1` = ruta destino, `field2` = `startInitDate`, `user_ig_id` = ownerId. Hay que partir la ruta en árbol y dejar de tratar strings de path como clave de agrupación en Python.
- **`accounts`**: *snapshot de cuenta dentro de un lote*. Por eso se repite `username`. Relación correcta: `batch_accounts.catalog_account_id → catalog_accounts.id`. `generated_story_url` se calcula (`https://www.instagram.com/stories/{username}/`); no se persiste. `working_folder` sí se guarda (se usa). `final_destination_folder` se omite hasta que haya movimiento final.
- **`batch_run_queue_items`**: no está muerta; está vacía porque no has encadenado lotes. Se conserva.
- **`download_files`**: no es solo reporte. El bot asocia ficheros a un `url_job` y `file_mover` los clasifica. En v2 se mantiene **para el run en curso** (y se puede podar al completar el lote si no hay reporte GUI). No se usa para pintar la GUI al arrancar.

### Esquema v2 (nombres claros, FKs por id, índices)

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 100;

-- Preferencias GUI + operativas (unifica app_config)
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL, -- TEXT|INTEGER|BOOLEAN|PATH
    updated_at TEXT NOT NULL
);

CREATE TABLE catalog_folders (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES catalog_folders(id),
    name TEXT NOT NULL,
    full_path TEXT NOT NULL,
    depth INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_catalog_folders_full_path ON catalog_folders(full_path);
CREATE INDEX idx_catalog_folders_parent ON catalog_folders(parent_id);

CREATE TABLE catalog_accounts (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE,
    instagram_user_id TEXT,
    folder_id INTEGER REFERENCES catalog_folders(id), -- última carpeta de field1
    start_init_date TEXT,                             -- era field2
    status TEXT NOT NULL DEFAULT 'ENABLED',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_catalog_accounts_username
    ON catalog_accounts(username COLLATE NOCASE);
CREATE INDEX idx_catalog_accounts_folder ON catalog_accounts(folder_id);
CREATE INDEX idx_catalog_accounts_status ON catalog_accounts(status);
CREATE INDEX idx_catalog_accounts_favorite ON catalog_accounts(is_favorite);

CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    start_date TEXT NOT NULL, -- YYYY-MM-DD, se fija a hoy al crear; no editable
    source_file TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_batches_name ON batches(name);
CREATE INDEX idx_batches_status ON batches(status);

CREATE TABLE batch_accounts (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    catalog_account_id INTEGER NOT NULL REFERENCES catalog_accounts(id),
    download_stories INTEGER NOT NULL DEFAULT 0,
    is_new_account INTEGER NOT NULL DEFAULT 0,
    is_catalog_update INTEGER NOT NULL DEFAULT 0,
    rename_owner_id TEXT,
    rename_start_init_date TEXT,
    rename_destination_path TEXT,
    working_folder TEXT,
    status TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, catalog_account_id)
);
CREATE INDEX idx_batch_accounts_batch ON batch_accounts(batch_id);
CREATE INDEX idx_batch_accounts_catalog ON batch_accounts(catalog_account_id);
CREATE INDEX idx_batch_accounts_status ON batch_accounts(status);

CREATE TABLE url_jobs (
    -- igual semántica v1, FK a batch_accounts.id
    id INTEGER PRIMARY KEY,
    batch_account_id INTEGER NOT NULL REFERENCES batch_accounts(id),
    run_id INTEGER REFERENCES runs(id),
    url TEXT NOT NULL,
    publication_type TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER,
    last_error TEXT,
    last_error_type TEXT,
    non_retryable INTEGER NOT NULL DEFAULT 0,
    sent_message_id INTEGER,
    started_at TEXT,
    finished_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_url_jobs_batch_account ON url_jobs(batch_account_id);
CREATE INDEX idx_url_jobs_status ON url_jobs(status);
CREATE UNIQUE INDEX uq_url_jobs_account_url ON url_jobs(batch_account_id, url);

CREATE TABLE download_files ( /* misma forma v1, FK url_jobs */ );
CREATE TABLE runs ( /* batch_id + opcional batch_account_id */ );
CREATE TABLE duplicate_url_jobs ( /* se mantiene por si el parser detecta duplicados */ );
CREATE TABLE batch_run_queues ( /* igual v1.31 */ );
CREATE TABLE batch_run_queue_items ( /* igual v1.31 */ );
```

Claves nuevas en `app_settings` (además de las 8 operativas):

- `ui.language`, `ui.theme`, `ui.catalog_view` (`list`|`tree`)
- `ui.show_catalog`, `ui.show_editor`, `ui.show_batch`, `ui.window_geometry`
- `notify.telegram_enabled`, `notify.telegram_target` (`me` por defecto)

### Capa de código (sin romper el motor)

El orquestador habla de `Account.username`, `account_id`, `url_jobs`. No reescribir `account_orchestrator` / `url_job_processor` / Telethon.

Estrategia:

1. Nuevos repositorios v2 (`catalog_account_repository`, `catalog_folder_repository`, `batch_account_repository`).
2. Adaptador: `AccountRepository` v2 **hidrata** el dataclass `Account` actual con `username` vía JOIN a `catalog_accounts`. El motor sigue recibiendo el mismo modelo.
3. `build_story_url(username)` se calcula en creación de jobs, no se guarda.
4. `AccountCatalogService.list_entries` lee `catalog_accounts` + `catalog_folders` (una query, no JSON ni backups). El fallback a `config/batch.json` solo si el catálogo está vacío (igual que hoy).
5. Árbol: `list_folder_children(parent_id)` y `list_accounts_in_folder(folder_id)` — lazy, indexado.

### Inserts rápidos (el arreglo que más se nota)

Aunque el esquema nuevo ayude, el cuello de botella actual es transaccional:

1. `connect()`: `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `temp_store=MEMORY`, `foreign_keys=ON`.
2. `create_batch` / `update_draft_batch`: **una sola transacción**. Quitar `commit()` de `UrlJobRepository.create` / `AccountRepository.create` cuando se llaman en bucle; el caller hace commit.
3. `executemany` para `url_jobs` (un lote de 860 URLs = 1 insert masivo, no 860 commits).
4. Upsert de catálogo: `INSERT ... ON CONFLICT(username) DO NOTHING` + recoger ids.
5. Al actualizar un DRAFT, en vez de DELETE+reinsert fila a fila, transacción única (ya se borra; el coste es el reinsert).

Esto se puede (y se debe) aplicar también al motor v1 si se desea un parche, pero en v2 es obligatorio.

Carga de GUI al arrancar:

- Catálogo: `SELECT` cuentas + folders (~300 filas), no 3384 `accounts`.
- “Hoy”: índice por `batch_accounts.created_at` / `runs.started_at` del **fichero GUI**, no un JOIN completo del histórico v1.
- `list_usernames_active_on_date` actual barre toda `accounts` y `runs`; reescribir con `WHERE created_at >= ? AND created_at < ?`.

### Poda de `download_files`

Política v2 GUI: al marcar un lote `COMPLETED` y tras rename, borrar `download_files` de ese lote (los jobs y estados de URL se quedan). Configurable `retention.download_files` = `on_complete` | `keep`. Default `on_complete` porque no hay reportes en GUI.

El motor en memoria durante la cuenta no cambia: sigue insertando para que `file_mover` clasifique.

### Tareas BBDD (paso a paso)

1. **T2.D1** Tag `v1.31.0`, backup SQLite, `SQLITE_GUI_DB_PATH`, WAL en `connect()` (sin cambiar esquema aún si se aplica a v1 connection factory de forma compatible).
2. **T2.D2** `schema_v2.sql` + `init_gui_database` + tests de migración vacía.
3. **T2.D3** Importador v1→v2 (catálogo + lotes reanudables). Tests con SQLite temporal copiando un subconjunto.
4. **T2.D4** Repositorios v2 + adaptadores al modelo `Account`/`UrlJob`. Tests de repositorio.
5. **T2.D5** `create_batch` / `save_batch_draft` con transacción + `executemany`. Test de rendimiento: 100 cuentas × 20 URLs < 1 s en SQLite temporal (hoy eso dispara cientos de commits).
6. **T2.D6** GUI arranca contra el fichero nuevo. Catálogo y lotes pendientes viven ahí.
7. **T2.D7** (opcional) Lectura del histórico v1 en el diálogo Lotes, conexión read-only al fichero viejo.

---

## 3) Plan de aviso Telegram al terminar un lote

### ¿Es posible enviarme un mensaje a mí mismo?

**Sí.** El cliente ya es un **usuario real Telethon** (no un bot API). Con la misma sesión se puede:

```python
await client.send_message("me", texto)
```

`"me"` es **Saved Messages / Mensajes guardados**. En el móvil aparece notificación nativa, que es exactamente el alert que quieres.

También es posible un contacto u otro chat (`username`, `+telefono` o `chat_id` numérico). Saved Messages es el default: no hay que “encontrarte” en la lista de dialogs y no molesta a nadie.

Restricciones reales:

- Hay que usar **la misma** `*.session`. Telegram no permite dos procesos Telethon con el mismo fichero a la vez.
- Hoy la GUI lanza el lote en **subproceso**. Mientras descarga, la sesión está ocupada. El aviso debe ir **después** de que el subproceso termine (`_handle_process_complete`), cuando el `.session` ya está libre.
- No enviar al bot de descargas: ese chat es de trabajo y no te alerta igual.
- No loguear el destino si algún día es un teléfono.

### Diseño

Nuevo servicio pequeño `src/ig_orchestrator/telegram/notify_service.py`:

- `send_user_notification(settings, text, target="me")` → abre Telethon, `send_message`, desconecta.
- Timeout corto (10–15 s). Si falla, se escribe en el log GUI y **no** se considera fallo del lote.
- Nunca se llama en medio de una cuenta.

Disparadores GUI:

- Cada lote de la cola que termina con éxito.
- Resumen final cuando la cola pasa a `AWAITING_RENAME` / `COMPLETED`.
- Lote único igual.
- No notificar si el usuario pulsó Detener (cancel).
- No notificar dry-run (la GUI ya no lo tiene).

Texto (i18n), ejemplo:

```
Instagram Orchestrator
Lote descargas_22_agosto_2026 (id=160) completado
Cuentas: 12/12 · URLs ok: 140 · fallidas: 5
Siguiente: Renombrar
```

Configuración (menú Configuración, persistida en `app_settings`):

- Enable checkbox.
- Destino: `me` (default) o texto libre (username / id).
- Probar aviso (botón) que envía “Prueba de notificación”.

`.env` opcional (no secretos nuevos): `TELEGRAM_NOTIFY_ENABLED=true`, `TELEGRAM_NOTIFY_TARGET=me`.

### Tareas Telegram (paso a paso)

1. **T2.T1** `notify_service` + test con cliente fake (mismo patrón que `tests/test_telegram_client.py`).
2. **T2.T2** Enganche en `_handle_process_complete` / fin de cola. Hilo o `asyncio.run` corto para no bloquear Tk.
3. **T2.T3** UI de configuración + “Enviar prueba”.

---

## Archivos críticos

Nuevos:

- `src/ig_orchestrator/db/schema_v2.sql`
- `src/ig_orchestrator/db/gui_migrations.py`
- `src/ig_orchestrator/db/v1_to_v2_importer.py`
- `src/ig_orchestrator/gui/i18n.py`, `theme.py`, `icons.py`, `menus.py`
- `src/ig_orchestrator/gui/locales/es.json`, `en.json`
- `src/ig_orchestrator/gui/assets/icons/*.png`
- `src/ig_orchestrator/gui/widgets/*`
- `src/ig_orchestrator/telegram/notify_service.py`
- `tasks/Tarea_v2_*.md`

Modificar (con testers existentes actualizados):

- `src/ig_orchestrator/gui/app.py` (se parte; no se reescribe el flujo de ejecución)
- `src/ig_orchestrator/gui/account_catalog_service.py`
- `src/ig_orchestrator/gui/batch_draft_service.py`, `process_runner.py`
- `src/ig_orchestrator/input/batch_creation_service.py` (transacción + executemany)
- `src/ig_orchestrator/db/connection.py` (WAL)
- `src/ig_orchestrator/db/*_repository.py` (adaptadores v2)
- `src/ig_orchestrator/settings.py` (`sqlite_gui_db_path`, notify)
- `src/ig_orchestrator/__init__.py`, `pyproject.toml` → `2.0.0` solo al cerrar la serie
- `Agents.md` (serie v2.x), `CHANGELOG.md`, `README.md`
- `requirements.txt`: añadir `sv-ttk`

Reutilizar sin reescribir:

- `orchestration/*`, `telegram/bot_conversation_service.py`, `telegram/telegram_client.py` (añadir `send_message` genérico o usarlo en notify)
- `gui/batch_queue_service.py`, `batch_resume_service.py`, `batch_transfer_service.py`, `rename_folder_status.py`
- CLI `main.py` (`--dry-run`, reportes) intacto frente a `SQLITE_DB_PATH`

---

## Verificación

Tras cada tarea, no solo al final:

- `python -m pytest -q` (suite completa; hoy es la red de seguridad de v1).
- Tests nuevos: i18n keys presentes en es y en; importador v1→v2; bulk insert; árbol de `G:\4K Stogram\00.FAVORITES\Valeria-Makusheva` → hoja `lerabuns`; notify con fake client.
- Manual GUI (no hay browser tools; la app es Tk):
  1. Arrancar v2: catálogo carga, lotes PARTIAL importados, no se toca `orchestrator.sqlite` (comparar mtime/size).
  2. Registrar un lote grande (~200 URLs) y cronometrar: debe ser inmediato.
  3. Recorrer Pegar/Agregar, Agregar/Actualizar, checkboxes Stories/New/Update (sin modal).
  4. Conmutar lista/árbol, filtrar, contextual, colores.
  5. Ejecutar un lote real pequeño, ver barra de estado, abrir modal de log, copiar, Detener.
  6. Al completar: notificación en Saved Messages; Renombrar se habilita como en v1.31.
  7. Cambiar idioma → la app reinicia en el otro idioma.
  8. Rollback drill: `git checkout v1.31.0`, `python -m ig_orchestrator gui` sobre el SQLite v1, un `run_continue` de un PARTIAL que no se haya tocado.

Criterio de cierre v2.0.0: las 7 tareas GUI + 7 BBDD + 3 Telegram verdes, drill de rollback documentado en `CHANGELOG.md`, tag `v2.0.0`.

---

## Fuera de alcance v2.0.0

- Reescritura Qt / web.
- Eliminar CLI, `--dry-run` del motor, o reportes Markdown del modo no-GUI.
- Borrar en caliente `data/orchestrator.sqlite`.
- Movimiento final a `G:\4K Stogram` más allá de lo que ya hace el renombrador.
- Temas oscuros / paletas extra (solo claro).
- Más idiomas que `es` y `en`.
