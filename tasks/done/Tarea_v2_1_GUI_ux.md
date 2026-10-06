# Tarea v2.1 — GUI: editor, catálogo, estado de rename y organizador de stories

Fecha: 2026-09-13
Serie: v2.1.0
Rama: `v2/gui-ux-stories` (no trabajar en `master`)
Estado: **APROBADO — implementación por fases**

Leer antes de implementar: `PLAN.md`, `Agents.md`, `docs/modularizacion_v2.md`
y el `MODULE.md` de cada paquete tocado. No abrir `gui/app.py` salvo el shim;
la clase vive en `gui/shell/app.py`.

## Cómo pedir esta tarea (otra sesión)

* «Ejecuta `tasks/Tarea_v2_1_GUI_ux.md`»
* «Implementa el plan v2.1 por fases»
* «Sigue con la fase N del plan GUI ux»

## Problema

Cuatro huecos de la GUI v2.0.0:

1. Los checks del editor (Stories / New account / Update) sobreviven al
   cambiar de username (catálogo o pegado).
2. No hay forma de marcar una cuenta del lote como primera en la lista.
3. El buscador del catálogo no tiene botón Pegar; pegar no selecciona ni
   rellena el editor.
4. Tras Renombrar, la barra de estado no distingue error / incompleto /
   éxito, ni avisa con claridad de que el renombrado está en curso.
5. Falta una herramienta para mover stories sueltas (ficheros cuyo
   filename empieza por `{username}-…`) a `{path}\story` según una BD
   externa `accounts_dir`.

## Fuera de alcance

* Escribir en `data/orchestrator.sqlite` (v1).
* Cambiar el algoritmo stories-first (dos barridas) salvo respetar el
  orden de cuentas *dentro* de cada barrida.
* Prioridad N simultánea en la UI (el modelo sí queda preparado).
* Rediseñar el diálogo Lotes / ejecuciones.
* Tag `v2.1.0` hasta terminar todas las fases y `pytest` en verde.
* Borrar ficheros de origen si el move no confirma destino.
* Integrar el organizador de stories con el script de renombrado.

## Decisiones de diseño (aprobadas 2026-09-13)

| Tema | Decisión |
|---|---|
| Botón Stories | Toolbar, a la derecha de **Renombrar manual**, más ítem de menú `Lote → Organizar stories…`. |
| Icono Pegar del catálogo | `clipboard_black.png` compacto (igual que Pegar username del editor). El ❌ de limpiar se queda. |
| Reset de checks | El username *normalizado* (`strip`, quitar `@`, `casefold`) es la identidad. Si cambia, se resetean Stories / New account / Update / Priority y se oculta el frame de metadatos. Eventos: catálogo, pegar editor, pegar catálogo, `<<ComboboxSelected>>`, limpiar Username. No resetear en cada tecla si la identidad no cambia. Al cargar una fila del lote, se hidratan los checks de esa cuenta. |
| Prioridad actual | Un solo rank `1` exclusivo. El campo es `int` (`0` = sin prioridad) para poder tener `1, 2, 3…` más adelante. |
| BD de stories | SQLite **externa** de solo lectura (`accounts_dir.username` → `accounts_dir.path`). No es `orchestrator_gui.sqlite`. |

## Arquitectura

Sin event-bus. Misma tabla de canales de `docs/modularizacion_v2.md`.

```text
  [Widgets Tk / mixins]
           │  atributos de App
           v
  InstagramOrchestratorApp
           │
           ├── gui/editor          checks + priority
           ├── gui/catalog         pegar → seleccionar → username_var
           ├── gui/chrome          color de status_button
           ├── gui/run             rename running/error/incomplete/ok
           ├── gui/draft           AccountDraft.priority
           ├── gui/stories         diálogo (Tk)  ← NUEVO paquete
           └── filesystem/story_inbox.py  (puro, sin Tk)  ← NUEVO
                    │
                    ├── app_settings (rutas recordadas)
                    └── SQLite externa accounts_dir (solo SELECT)
```

Servicios puros: `connection` o `Path` in → datos out. No importan Tk.
Un módulo no importa widgets de otro: el catálogo escribe
`self.username_var` y llama helpers del editor (`self._on_username_identity_changed`)
que ya viven en el mixin de App.

## Modelo de prioridad (preparado para N cuentas)

```text
PRIORITY_NONE = 0
PRIORITY_HIGHEST = 1   # único valor que expone el check actual
```

`AccountDraft.priority: int = 0`

Helper puro (sin Tk), p.ej. `gui/draft/priority.py`:

```python
def assign_exclusive_priority(
    accounts: list[AccountDraft],
    username: str,
    rank: int = PRIORITY_HIGHEST,
) -> list[AccountDraft]:
    """Pone *rank* en *username* y deja en 0 a quien tuviera ese mismo rank.

    Hoy rank=1 y como mucho una cuenta. Mañana: llamar en bucle con
    rank=2, 3… o sustituir por assign_shifted_priority() (incrementar
    los demás en vez de limpiarlos).
    """

def ordered_accounts_for_display(
    accounts: list[AccountDraft],
) -> list[AccountDraft]:
    """priority > 0 primero (1, 2, 3…), el resto conserva orden relativo."""
```

Reglas de UI:

* Check **Priority** al lado de **Update**.
* Al Agregar/Actualizar con el check marcado: esa cuenta pasa a
  `priority=1`, cualquier otra del lote con `priority==1` vuelve a `0`,
  y la lista se reordena (la cuenta priorizada queda primera).
* Al Agregar/Actualizar sin el check: `priority=0`; si se actualiza la
  que era 1, deja de serlo.
* Solo afecta al **orden** de `self.accounts` (tabla y `sort_order` al
  guardar). La ejecución sigue siendo stories-first: primero jobs
  `STORY` del lote, después el resto. Dentro de cada barrida se respeta
  el orden de cuentas (la priorizada sale antes *dentro de su grupo*
  story-only vs mixta).
* `_ordered_accounts_for_creation` hoy reordena por solo-stories y
  cantidad de URLs y **pisaría** la prioridad. Hay que componer:
  cuentas con `priority>0` primero (por rank), y el sort legado solo
  sobre las de `priority==0`.

Persistencia:

* Columna nueva `batch_accounts.priority INTEGER NOT NULL DEFAULT 0`
  vía `_add_column_if_missing` en `db/gui_migrations.py` (mismo patrón
  que `working_relative_path`; no subir `user_version`).
* `save_batch_draft` / `load_batch_draft` / `gui_batch_creation` leen y
  escriben el campo.
* Visual en la tabla: columna compacta **Prio** con `1` o vacío (el
  número deja sitio a ranks futuros). No hace falta columna SQLite
  extra.

## 1. Editor — reset de checks

Causa: `_load_catalog` y `_paste_username` solo hacen
`username_var.set(...)`. `stories_var` / `new_account_var` /
`catalog_update_var` no se tocan. `_clear_editor` sí los pone a False,
pero no se llama al cambiar de cuenta.

Comportamiento:

* Identidad = username normalizado.
* Si la identidad cambia (catálogo, pegar en editor, pegar en catálogo,
  `<<ComboboxSelected>>`, limpiar Username):
  * `stories_var = False`
  * `new_account_var = False`
  * `catalog_update_var = False`
  * `priority_var = False`
  * owner / startInitDate / path vacíos y frame oculto
* `_apply_catalog_date` puede rellenar metadatos del catálogo *después*
  del reset, pero los checks siguen off (el usuario los marca otra vez).
* `_load_selected_row` hidrata checks desde `AccountDraft` usando un
  token silencioso (`_editor_hydrate_token`), igual que
  `_catalog_silent_token`, para no resetear y luego pitar los valores.

Ficheros: `gui/editor/panel.py`, tests en `tests/gui/test_editor.py`.

## 2. Catálogo — pegar y seleccionar

Hoy: `catalog_filter_var` filtra y, si hay match exacto, selecciona en
lista/árbol **sin** volcar al editor (`_select_catalog_tree_leaf` usa
token silencioso). Pegar por menú contextual inserta texto y no carga
el editor. No hay botón Pegar.

Comportamiento:

* Botón compacto de portapapeles a la **izquierda** del ❌ del buscador.
* El botón **reemplaza** el filtro por la primera línea no vacía del
  portapapeles (misma helper `first_clipboard_line`).
* Tras cualquier pegado en esa caja (botón, menú contextual, Ctrl+V):
  1. Normalizar el texto (`strip`, quitar `@`).
  2. Dejarlo en el filtro (dispara `_refresh_catalog` → selección si
     hay match exacto, lista o árbol).
  3. **Siempre** escribir ese texto en `username_var` del editor.
  4. Si hay match, seleccionar y hacer `see` (lista y árbol). Si no hay
     match, no inventar selección; el editor igual muestra lo pegado.
  5. El cambio de `username_var` resetea los checks (punto 1).
* Teclear en el filtro **no** rellena el editor (sigue siendo búsqueda).
  Solo el pegado.

Ficheros: `gui/catalog/panel.py`, `gui/editor/text_edit.py` (Ctrl+V +
`after_change` en el filtro), `tests/gui/test_catalog.py`.

## 3. Barra de estado — color de rename

Hoy `status_button` es `ttk.Button` a ancho completo; abre “Estado de
ejecución”. `_handle_rename_complete` ya distingue:

* éxito: `exit_code == 0` y sin leftovers
* incompleto: leftovers en `working_folder`
* error: `exit_code != 0` (BD/unidad ausente, script, etc.)
* en curso: `_set_status("Renombrando archivos...")` sin color

`ttk.Button` + sv-ttk no pinta `background` de forma fiable en Windows.
Usar `tk.Button` (o un `tk.Frame` de color detrás) para el status:

| Estado | Color | Texto |
|---|---|---|
| idle / listo | estilo normal | el status de siempre |
| rename running | azul `#2563EB` (ACCENT) texto blanco | `Renombrando…` |
| rename error | rojo `#cf222e` texto blanco | el error ya existente |
| rename incomplete | amarillo `#b76e00` / `#fff2cc` | `Renombrado incompleto: N carpeta(s)…` |
| rename success | verde `#238636` texto blanco | `Renombrado finalizado correctamente` |

También pintar error si el rename **ni llega a arrancar** (script no
encontrado, fecha inválida, sin batch, `OSError` al `Popen`).

El color permanece hasta: nuevo rename, nuevo lote, o ejecutar un lote.
Mientras corre, la UI ya se bloquea (`_set_process_running`); el color
azul es el aviso visual pedido.

Ficheros: `gui/chrome/statusbar.py`, `gui/run/rename.py`,
`gui/shared/theme.py` (constantes de color), `gui/shell/app.py` (widget),
`tests/gui/test_rename.py`.

## 4. Organizador de stories

Herramienta **independiente del lote**. No usa el orquestador ni
Telegram.

### UI

Modal no bloqueante o `Toplevel` modal ligero:

* `Ruta Stories` (directorio origen) + Browse
* `Ruta BD` (fichero SQLite con `accounts_dir`) + Browse
* Botones: Guardar rutas, Ejecutar, Cerrar
* Log/resumen en el propio modal (moved / skipped / errors)
* Al abrir, rellena las últimas rutas desde `app_settings`

Claves:

```text
stories.inbox_path
stories.accounts_db_path
```

Mismo patrón `INSERT … ON CONFLICT(key) DO UPDATE` que
`ui.catalog_view`.

### Algoritmo (puro, testeable)

Entrada: `inbox: Path`, `accounts_db: Path`.

1. Validar que `inbox` es directorio y `accounts_db` es fichero SQLite
   legible. Si falla, error global (no se mueve nada).
2. Listar ficheros multimedia en `inbox` (no recursivo en v2.1, salvo
   que al implementar se vea que 4K Stogram deja subcarpetas; documentar
   la decisión). Extensiones:
   `jpg jpeg png webp bmp gif mp4 mov mkv webm m4v avi`.
3. Para cada fichero:
   * Username = caracteres **antes del primer `-`**.
     Ejemplo:
     `best.slips-20260817_151729-777297818_…_n.jpeg` → `best.slips`
   * Sin `-`, o username vacío → error `NO_USERNAME_IN_NAME`, no mover.
   * `SELECT path FROM accounts_dir WHERE username = ?` (comparar
     case-insensitive; guardar el username tal cual del filename).
   * 0 filas → `USERNAME_NOT_IN_DB`
   * `path` vacío → `EMPTY_PATH`
   * `Path(path)` no existe en disco → `ACCOUNT_PATH_MISSING`
   * Destino = `Path(path) / "story"`. Crear `story` si no existe y el
     padre sí.
   * Destino con el mismo nombre ya existe → `DESTINATION_EXISTS` (no
     overwrite).
   * `shutil.move` → `MOVED`. Si `move` lanza OSError → `MOVE_FAILED`.
4. Devolver un resumen inmutable por fichero (`src`, `username`,
   `dest`, `status`, `detail`).

La BD externa se abre en modo URI `mode=ro` cuando SQLite lo permite;
nunca `INSERT/UPDATE/DELETE` ahí.

Ficheros nuevos:

```text
src/ig_orchestrator/filesystem/story_inbox.py
src/ig_orchestrator/gui/stories/MODULE.md
src/ig_orchestrator/gui/stories/__init__.py
src/ig_orchestrator/gui/stories/dialog.py
src/ig_orchestrator/gui/stories/settings.py   # leer/escribir app_settings
tests/filesystem/test_story_inbox.py
tests/gui/test_stories_dialog.py               # settings + parse, sin Tk real si se puede
```

Icono toolbar: reutilizar `list.png` no. Preferible texto **Stories** en
un `ttk.Button` compacto (no hay icono de cámara en `static/icons` y no
añadir dependencia de diseño). Tooltip i18n.

## Fases de implementación

Cada fase es un commit propio. No mezclar con refactors ajenos.
Tras cada fase: tests de esa fase en verde.

### Fase 0 — Rama y esqueleto de docs

* Rama `v2/gui-ux-stories` (este archivo).
* No tocar código todavía.

### Fase 1 — Reset de checks del editor

Estado: **hecho**

* Identidad de username + reset de BooleanVars.
* Hidratación al cargar fila del lote (`hydrate=True`).
* Tests: catálogo → otro username; mismo username conserva flags;
  pegar username; hidratar fila no resetea.

### Fase 2 — Check Priority y orden del lote

Estado: **hecho**

* `AccountDraft.priority`.
* Helper exclusivo + reorder.
* Check en el editor; columna Prio en la tabla.
* Columna SQLite + save/load.
* Componer `_ordered_accounts_for_creation` con ranks.
* Tests unitarios del helper y del upsert (lista en memoria).
* Tests de save/load con `init_gui_database` temporal.

### Fase 3 — Pegar en el catálogo

Estado: **hecho**

* Botón + Ctrl+V + menú contextual.
* Match → seleccionar lista/árbol y rellenar editor.
* Sin match → editor igual, sin selección inventada.
* Tests de `catalog_focus_username` + handler de pegado.

### Fase 4 — Color de la barra de estado en rename

Estado: **hecho**

* API `_set_status_tone(tone)` en chrome.
* Mapear running / success / incomplete / error.
* Tests de `_handle_rename_complete` y de arranque fallido.

### Fase 5 — Organizador de stories

Estado: **hecho**

* Servicio puro + tests con tmp_path y SQLite mínima `accounts_dir`.
* Persistencia de rutas en `app_settings`.
* Diálogo + botón toolbar + menú.
* Casos: not in db, path missing, no hyphen, collision, éxito.

### Fase 6 — i18n, CHANGELOG, MODULE.md, PLAN.md, versión

Estado: **docs hechos; versión/tag pendientes de cierre**

* Claves `es.json` / `en.json`.
* `__version__` sigue en `2.0.0` hasta el tag `v2.1.0`.
* `CHANGELOG.md` bloque Unreleased.
* Actualizar `MODULE.md` de editor, catalog, chrome, run, draft, db.
* `docs/modularizacion_v2.md`: fila del mapa para `gui/stories`.
* `PLAN.md`: sección corta del organizador y de prioridad.

## Tests previstos (mínimo)

```bash
python -m pytest -q tests/gui/test_editor.py tests/gui/test_catalog.py
python -m pytest -q tests/gui/test_draft.py tests/gui/test_batch_accounts.py
python -m pytest -q tests/gui/test_rename.py tests/filesystem/test_story_inbox.py
python -m pytest -q
```

No Telegram real. SQLite temporal. El parser de filename y el mover se
prueban sin Tk.

## Riesgos

* sv-ttk vs color de `ttk.Button`: se evita usando `tk.Button` en la
  barra.
* `_ordered_accounts_for_creation` vs prioridad: hay que componer, no
  sustituir en silencio el sort legado para cuentas sin rank.
* `load_batch_draft` lee la vista `accounts` (compat v2). Añadir
  `priority` a la vista si hace falta para que el reload de un DRAFT
  muestre la estrella.
* La tabla `accounts_dir` no existe en este repo: el servicio debe
  fallar con mensaje claro si no está (`no such table`).
* Pegar en el filtro hoy también dispara `trace_add("write")` →
  `_refresh_catalog`. El volcado al editor debe ser un paso explícito
  del handler de pegado, no del trace (si no, teclear rellenaría el
  editor).

## Respuesta al cerrar cada fase

Según `Agents.md`: resumen, pruebas, commit sugerido, tag solo al
cerrar v2.1.0.

```bash
git add .
git commit -m "feat: implement tarea v2.1 fase N ..."
# tag solo en la fase 6:
git tag v2.1.0
```
