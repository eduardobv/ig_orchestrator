# Modularización v2 (GUI, persistencia, tests)

Documento canónico del corte de módulos. Complementa `PLAN.md` y
`tasks/Tarea_v2_modularize.md`. No cambia el comportamiento: el código se
mueve, no se reescribe.

Rama: `v2/orchestrator`. Esto entra en Unreleased v2.0.0. El tag y la PR a
`master` siguen en `tasks/Tarea_v2_0_0_release.md`.

## Objetivo

Un cambio de catálogo (o editor, cola, settings, …) debe resolverse leyendo
**un `MODULE.md` y unos pocos ficheros de &lt;400 líneas**, no
`gui/app.py` de ~3900 líneas ni `tests/test_gui_services.py` de ~2500.

## Principios

1. Mover, no reescribir. Mismos algoritmos, SQL, widgets y asserts.
2. Tope blando ~350 líneas por fichero, techo ~500.
3. `InstagramOrchestratorApp` es el composition root y guarda el estado de
   sesión. Los paneles son mixins (o un diálogo-clase) sobre `self`.
4. Los servicios GUI son puros: `connection` in → datos out. No importan Tk.
5. Las rutas viejas quedan como shims de reexport para no romper imports.
6. Cada paquete tiene un `MODULE.md` (contrato para una IA).

## Comunicación entre partes

No hay event-bus. Los canales ya existían:

```text
  [Widgets Tk / mixins]
           │  leen y escriben atributos de App
           v
  InstagramOrchestratorApp          ← estado de sesión
           │  llama
           v
  Servicios GUI (catalog / draft / resume / queue / transfer)
           │  SQL
           v
  SQLite  data/orchestrator_gui.sqlite
           │
           │  ProcessRunner lanza subprocess
           v
  CLI  python -m ig_orchestrator run_continue --batch-id N
           │  stdout + exit code
           v
  callbacks en App  (_handle_process_output / _complete)
```

| Canal | Quién | Para qué |
|---|---|---|
| Atributos de `App` | mixins / diálogos | Estado y widgets (`self.accounts`, `self.tree`, `self.connection`) |
| Tk `StringVar` / `trace_add` | widgets entre sí | Filtros, nombre de lote, indicadores |
| Servicios GUI | App → SQLite | Persistencia; no conocen widgets |
| `ProcessRunner` | App ↔ CLI | Ejecutar lote / renombrar |
| SQLite | GUI y CLI | Fuente de verdad entre procesos |

Un módulo no importa widgets de otro. El catálogo no importa el editor: llama
`self._load_catalog()` (mixin de catálogo) y escribe `self.username_var`.

## Árbol GUI

```text
src/ig_orchestrator/gui/
|-- MODULE.md
|-- __init__.py
|-- app.py                             # shim → shell.app + helpers de tests
|-- shell/                             # composition root
|-- chrome/                            # menú, toolbar, barra de estado
|-- catalog/                           # panel izquierdo
|-- editor/                            # panel superior derecho
|-- batch_accounts/                    # cuentas del lote actual
|-- run/                               # ejecución, progreso, renombrado
|-- batches/                           # diálogo Lotes guardados y ejecuciones
|-- queue/                             # cola y secuencia
|-- settings/                          # diálogo Configuración
|-- draft/                             # AccountDraft / BatchDraft + persistencia
|-- stories/                           # organizar stories (inbox → path/story)
`-- shared/                            # i18n, theme, icons, helpers, locales, static
```

Mapa rápido “dónde está X”:

| Quiero cambiar… | Paquete | Ficheros |
|---|---|---|
| Lista/árbol del catálogo, colores, filtro | `gui/catalog` | `panel.py`, `service.py`, `colors.py`, `tree.py` |
| Username, URLs, pegar, normalizar, nueva cuenta | `gui/editor` | `panel.py`, `text_edit.py` |
| Tabla de cuentas del lote, sort, eliminar | `gui/batch_accounts` | `panel.py`, `progress.py` |
| Diálogo de URLs completed/retry/failed | `gui/batch_accounts` | `problem_urls.py` |
| Menú, toolbar, título, consola | `gui/chrome` | `menubar.py`, `toolbar.py`, `statusbar.py` |
| Ejecutar / detener / cola→siguiente | `gui/run` | `controller.py`, `process_runner.py` |
| Renombrar / leftovers | `gui/run` | `rename.py` |
| Diálogo Lotes (activos / históricos) | `gui/batches` | `dialog.py`, `resume/*.py`, `transfer.py` |
| Cola de secuencia | `gui/queue` | `panel.py`, `service.py` |
| Idioma, stories_first, notify, paleta | `gui/settings` | `dialog.py` |
| Guardar draft en SQLite | `gui/draft` | `models.py`, `service.py` |
| Traducciones, iconos, tema | `gui/shared` | `i18n.py`, `icons.py`, `theme.py` |
| Arranque de la ventana | `gui/shell` | `app.py` |
| Organizar stories (inbox) | `gui/stories` + `filesystem/story_inbox.py` | `dialog.py`, `settings.py` |

## Árbol persistencia

```text
src/ig_orchestrator/db/
|-- MODULE.md
|-- __init__.py                        # API pública igual (reexporta)
|-- connection.py
|-- schema_mode.py
|-- _mapping.py
|-- v1/                                # CLI rollback, orchestrator.sqlite
|-- v2/                                # GUI, orchestrator_gui.sqlite
|   |-- schema.sql
|   |-- migrations.py
|   |-- catalog/
|   `-- adapters/                      # Gui*Repository por entidad
`-- <shims de las rutas v1/v2 antiguas>
```

v1 no se fusiona con v2. Los repositorios v1 siguen despachando a adapters v2
cuando `user_version >= 100`.

## Árbol tests

```text
tests/
|-- gui/          # un fichero (o pocos) por paquete GUI
|-- db/
|-- orchestration/
|-- telegram/
|-- input/
|-- filesystem/
|-- reports/
`-- test_package_smoke.py
```

## CLI

```text
src/ig_orchestrator/cli/
|-- main.py           # argparse + dispatch
|-- gui_cmd.py
|-- run_batch.py
|-- run_continue.py
`-- progress.py
```

`src/ig_orchestrator/main.py` es shim hacia `cli.main`.

## Shims (imports estables)

Siguen funcionando:

```python
from ig_orchestrator.gui.app import launch_gui, InstagramOrchestratorApp
from ig_orchestrator.gui.account_catalog_service import AccountCatalogService
from ig_orchestrator.db.gui_adapters import GuiBatchRepository
from ig_orchestrator.main import main
```

## Cómo trabajar (IA o persona)

1. Leer este archivo.
2. Leer el `MODULE.md` del paquete afectado.
3. Editar solo ese paquete, salvo un atributo nuevo de estado en `shell/app.py`.
4. Correr los tests listados en el `MODULE.md`.
5. No abrir `gui/app.py` salvo el shim; la clase vive en `gui/shell/app.py`.

## Estado del corte (lo que quedó grande a propósito)

`gui/app.py` ya no es el monolito: es un shim. Siguen por encima de ~500 líneas
porque son un solo diálogo/servicio copiado tal cual:

* `gui/batches/dialog.py` — diálogo Lotes + panel de cola embebido
* `gui/batches/resume.py` — listados + load + runtime + acciones
* `gui/queue/service.py`
* `cli/main.py` — argparse + run/continue (movido desde `main.py`)

Un cambio de catálogo/editor/settings no pasa por esos ficheros.

## Fuera de alcance de este corte

- Event-bus, DI, reescritura a Frames “limpios”.
- Cambio de esquema SQLite o migraciones.
- Escribir en `data/orchestrator.sqlite`.
- Release / tag `v2.0.0`.
- Partir `orchestration/` o `telegram/` (queda para un patch posterior).
