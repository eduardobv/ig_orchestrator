# Changelog

## Unreleased - v2.0.0 (en progreso)

Fecha: 2026-08-22

### Creado

* `src/ig_orchestrator/db/schema_v2.sql` con diccionarios de estados/tipos,
  `bot_errors`, `path_roots`, catálogo, lotes, URLs y ficheros relativos.
* `src/ig_orchestrator/db/gui_migrations.py` (`user_version = 100`).
* `src/ig_orchestrator/db/catalog_importer.py` (solo catálogo, ids conservados).
* `src/ig_orchestrator/db/gui_catalog_repository.py`, `gui_adapters.py`,
  `lookups.py`, `schema_mode.py`, `compat_views_v2.sql`.
* `src/ig_orchestrator/input/gui_batch_creation.py` (inserts en una transacción).
* `tests/test_gui_database.py`, `tests/test_catalog_importer.py`,
  `tests/test_gui_repositories.py`, `tests/test_gui_theme.py`,
  `tests/test_log_window.py`.
* `tasks/Tarea_v2_D1.md` … `Tarea_v2_D6.md`.
* `tasks/Tarea_v2_0_0_release.md` (PR a `master` + tag `v2.0.0`, pendiente
  de validación).
* `tasks/Tarea_v2_GUI_batch_ux.md`.
* Copia local `data/old/orchestrator.v1.31.0.sqlite` (no se commitea).

### Modificado

* Ventana de log: cerrar la oculta (`withdraw`) en vez de destruir el
  `Text`; `append` ignora widgets ya destruidos. Evita
  `TclError: invalid command name ".!toplevel...!text"` al pulsar
  Renombrar después de cerrar el log.
* Tema GUI: `option_add("*Font")` usa `{Segoe UI} 10`. Sin llaves Tk
  interpretaba `UI` como tamaño y `tk.Menu` fallaba al abrir `ejecutar_gui.bat`.
* `connect()` usa WAL + `synchronous=NORMAL`.
* Setting opcional `SQLITE_GUI_DB_PATH` (default `data\orchestrator_gui.sqlite`).
* Repositorios v1 despachan a adaptadores v2 si `user_version >= 100`.
* `create_batch` / `save_batch_draft` en esquema GUI usan `executemany`.
* La GUI arranca contra `orchestrator_gui.sqlite`, importa el catálogo v1
  en solo lectura y lanza `run_continue` con `SQLITE_DB_PATH` apuntando al
  fichero GUI. El diálogo Lotes no se rediseña (vistas de compatibilidad).
* GUI: menú, i18n es/en, tema claro, toolbar de iconos, Start date de solo
  lectura, sin Dry-run, editor compacto, barra de estado + log en ventana,
  Renombrar/Detener en la toolbar. Configuración: idioma (reinicia) y vaciar
  ficheros descargados. `finish_batch` limpia `downloaded_files` si retention
  es `on_complete`.
* Catálogo lista/árbol (`G:\4K Stogram\…` + username hoja). Colores
  configurables con paleta. Orden A↔Z visual en cuentas del lote y URLs.
* Aviso Telegram a `me` u otro chat al terminar un lote y si un error del
  bot está marcado; plantilla y destino en Configuración.
* `.env.example` y `Agents.md` documentan el fichero GUI y el rollback a
  `v1.31.0`.
* Catálogo en árbol: al buscar un username, esa cuenta queda seleccionada
  (y visible) entre los peers de carpeta. Tras Agregar/Actualizar, el
  Username del editor se limpia también en vista árbol; la selección
  programática del árbol no recarga el editor.
* Cuentas del lote: buscador por username, contador `Cuentas: N` (y
  `visible / total` si hay filtro), columna Stories con ✅/❌, y al agregar
  se hace `focus`+`see` de la fila nueva sin seleccionarla (el editor no
  se rellena).
* Editor: botones en columna izquierda, mismo orden que antes en
  horizontal (Pegar/Agregar, Agregar/Actualizar, Pegar, Normalizar,
  Limpiar).
* Cola zombi: una secuencia `AWAITING_RENAME` sin lotes activos (todos
  `REMOVED`/`SKIPPED`) se cancela al abrirla y ya no secuestra el botón
  **Renombrar** de un lote suelto. Causa del error
  «No hay lotes para armar el comando de renombrado» con
  `descargas_2026_08_31_amber` (el lote en sí estaba correcto).
* Renombrar un lote desde Lotes usa ese lote, no la cola abierta.
* Un lote independiente solo avanza la cola si es el ítem `RUNNING`.
* **Quitar de cola** funciona con ítems `PENDING` y `COMPLETED` (no con
  `RUNNING`). Si la secuencia queda vacía, pasa a `CANCELLED`.
* `Finalizar sin renombrar`, `Ejecutado en otra instancia` y `Borrar lote`
  desenganchan el lote de la secuencia abierta. El ítem desaparece; si no
  queda nadie, la cola se cierra.
* Guardar lote muestra el error de nombre duplicado / `IntegrityError`
  en vez de un traceback.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_log_window.py tests/test_gui_theme.py`
* `python -m pytest -q tests/test_catalog_tree.py tests/test_notify_service.py tests/test_i18n.py tests/test_gui_services.py`
* `python -m pytest -q tests/test_gui_services.py -k "catalog_focus or filter_batch or stories_cell"`
* `python -m pytest -q tests/test_i18n.py`
* `python -m pytest -q tests/test_gui_services.py -k "queue or rename or elsewhere or detach or zombie or reactivat"`
* `python -m pytest -q`

## v1.31.0 - GUI: cola de lotes y rename combinado

Fecha: 2026-08-15

### Creado

* `tasks/Tarea_GUI_03.md`.
* `src/ig_orchestrator/gui/batch_queue_service.py`.
* Tablas `batch_run_queues` y `batch_run_queue_items`.

### Modificado

* Modal **Lotes / ejecuciones** deja de ser modal; pestaña Activos con
  selección múltiple y panel **Cola de ejecución**.
* Se pueden encadenar 2+ lotes, reordenar, quitar pendientes en caliente y
  renombrar juntos (parámetros unidos, `--move-renamed`).
* La cola persiste en SQLite para ejecutar en una instancia y renombrar en otra.
* Versión `1.31.0`.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "queue or rename or catalog"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.30.0 - GUI: catálogo, historial de un día

Fecha: 2026-08-15

### Creado

* `list_usernames_active_on_date` en `account_catalog_service.py`.

### Modificado

* Cuentas agregadas a un lote o descargadas hoy se pintan en amarillo claro
  (`#fff59d`) al iniciar la app y en cada refresh del catálogo.
* Prioridad de color: disabled > lote actual > hoy > inactivo > favorito.
* Dry-run no cuenta como descarga.
* Versión `1.30.0`.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "catalog or today or active_on_date"`

## v1.29.0 - GUI: Renombrar activo si quedan carpetas

Fecha: 2026-08-15

### Creado

* `src/ig_orchestrator/gui/rename_folder_status.py`.

### Modificado

* Tras Renombrar se inspecciona `WORKING_FOLDER`. Si quedan subcarpetas, el
  lote no pasa a `COMPLETED` y el botón sigue activo. La llamada conserva
  `--move-renamed`.
* `__version__` alineado con `pyproject.toml`.
* Versión `1.29.0`.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "unmoved or decide_rename or move-renamed or move_renamed"`

## v1.28.2 - Patch - GUI: pestaña Históricos y solo lectura

Fecha: 2026-08-11

### Creado

* `tasks/Patch_v1.28.2.md`.
* `list_historical_batches` para lotes `COMPLETED`.
* Modo `history_readonly` en la GUI principal.

### Modificado

* Modal **Lotes / ejecuciones** con pestañas **Activos** e **Históricos**
  (carga lazy del histórico).
* Abrir histórico: inspección de cuentas/URLs/carpetas sin editar ni ejecutar.
* Docs alineados; versión `1.28.2`.

### Resumen

Los lotes cerrados ya no desaparecen del alcance operativo: se consultan en
Históricos y se abren en solo lectura.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k historical`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.28.1 - Patch - GUI: checkbox Update y catálogo ownerId/path

Fecha: 2026-08-11

### Creado

* `tasks/Patch_v1.28.1.md`.
* `AccountDraft.is_catalog_update` y validación `validate_catalog_update_details`.
* `AccountHistoryRepository.update_identity_and_path` (id+path sin tocar field2).
* `save_catalog_metadata_to_history` unifica New account y Update.

### Modificado

* Editor: checkbox **Update** junto a New account (mutuamente excluyentes).
* Registrar/export/import persisten `ownerId`+`path` sin `is_new_account`.
* Estado de preparación en tabla: `Catálogo` para cuentas Update.
* Docs alineados; versión `1.28.1`.

### Resumen

Cuentas ya presentes en la BBDD maestra se pueden registrar en el orquestador
con id y ruta sin pasar por el renombrador como cuenta nueva, y la metadata
sobrevive export/import y el ciclo multi-instancia.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "catalog_update or rename_parameters or export_import"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.28.0 - Patch - GUI: Abrir carpeta y Ver URLs completadas

Fecha: 2026-08-11

### Creado

* `tasks/Patch_v1.28.0.md` documenta el menú contextual ampliado.
* `resolve_account_download_folder` en `batch_resume_service.py`.
* `list_account_problem_urls(..., kind="completed")` para jobs `COMPLETED`.

### Modificado

* Menú contextual de `Cuentas del lote actual`:
  * **Ver URLs completadas…** (habilitado si hay jobs completados).
  * **Abrir carpeta** (habilitado si la cuenta está `COMPLETED`).
* Doble click en una cuenta Completada abre el listado de URLs completadas.
* Docs alineados (`README.md`, `PLAN.md`, `tasks/task-gui.md`).
* Versión `1.28.0`.

### Resumen

Durante un lote en ejecución, una cuenta ya terminada permite inspeccionar sus
URLs completadas y abrir su carpeta de descarga en el explorador.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k "problem_urls or download_folder"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`

## v1.27.2 - Patch - Catálogo: cuenta exacta primero en el grupo de carpeta

Fecha: 2026-08-08

### Creado

* `tasks/Patch_v1.27.2.md` documenta el ajuste de orden del buscador.

### Modificado

* `filter_catalog_entries`: en match exacto con carpeta, la cuenta buscada
  aparece **primera** y el resto de peers de `field1` después (orden original).
* Docs alineados (`README.md`, `PLAN.md`, `tasks/task-gui.md`).
* Versión `1.27.2`.

### Resumen

Al buscar un username exacto en el catálogo, ya no hay que localizarlo a ojo
entre las hermanas de carpeta: queda siempre al inicio del listado filtrado.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py -k catalog_filter`
* `python -m pytest -q tests/test_package_smoke.py`

## v1.27.1 - Patch - GUI: carpeta en catálogo, URLs de lote, fallos y renombrado manual

Fecha: 2026-08-08

### Creado

* `tasks/Patch_v1.27.1.md` documenta los cuatro cambios de GUI.
* `filter_catalog_entries` en `account_catalog_service.py` (match exacto + peers de carpeta).
* `list_account_problem_urls` / `AccountProblemUrl` en `batch_resume_service.py`.
* `format_manual_rename_command_preview` y `format_command_for_shell` en `process_runner.py`.

### Modificado

* Buscador del catálogo: si el texto coincide exactamente con un username y
  tiene `field1`/`destination_path`, muestra todas las cuentas de esa carpeta.
* Diálogo `Lotes guardados y ejecuciones pendientes`: columna **URLs** con el
  total de `url_jobs` de origen `INPUT_URL` del lote.
* `PendingBatchSummary.url_count` en listados de lotes gestionados y pendientes.
* Durante/tras la ejecución, doble click o menú contextual en cuentas
  `Reintento` / `Fallida` abre una modal no bloqueante con las URLs afectadas;
  doble click en una fila abre Chrome.
* Botón **Renombrar Manual** (siempre habilitado) muestra el comando completo
  del script de renombrado con parámetros y permite copiarlo sin ejecutarlo.
* Tests de GUI actualizados.
* Versión `1.27.1`.

### Resumen

La GUI facilita localizar grupos de carpeta en el catálogo, ver el tamaño del
lote en URLs, inspeccionar fallos/reintentos en vivo y copiar el comando de
renombrado para ejecución manual.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`
* `python -m compileall -q src tests`

## v1.27.0 - Lotes: export/import y ciclo POR RENOMBRAR

Fecha: 2026-08-05

### Creado

* `src/ig_orchestrator/gui/batch_transfer_service.py` exporta e importa lotes
  en JSON portable (`ig_orchestrator.batch_export`).
* `tasks/Patch_v1.27.0.md` documenta el estado `AWAITING_RENAME`, el dialogo
  ampliado y el flujo multi-instancia.

### Modificado

* `InputBatchStatus` incorpora `AWAITING_RENAME` (descargas cerradas; falta
  renombrar o finalizar).
* El batch orchestrator, al completar todas las cuentas, deja el lote en
  `AWAITING_RENAME` en vez de `COMPLETED`.
* `batch_resume_service`: listados incluyen POR RENOMBRAR; `mark_batch_executed_elsewhere`,
  `is_batch_ready_for_rename` y finalizacion manual alineados al nuevo ciclo.
* Dialogo `Lotes / ejecuciones`: Exportar, Importar, Ejecutado en otra
  instancia, Renombrar, Finalizar sin renombrar.
* Tras renombrar con exito el lote pasa a `COMPLETED`.
* Tests de GUI, transfer y orchestrator actualizados.
* Version `1.27.0`.

### Resumen

Se puede llevar un lote a otra maquina (export/import), marcarlo como
ejecutado en otra instancia y, en cualquier caso, renombrar o cerrar el lote
sin perderlo en un limbo `COMPLETED` prematuro.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_batch_orchestrator.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.16 - Patch - Media not found 1 reintento y Detener proceso

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.16.md` documenta el tope de reintentos de
  `Media not found or unavailable` y el renombrado del boton de detencion.

### Modificado

* `src/ig_orchestrator/orchestration/retry_policy.py` limita ese error a
  **1 reintento** via `resolve_max_retries_for_error` /
  `last_error_type` en `calculate_retry_decision`.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` pasa
  `job.last_error_type` a la decision de reintento.
* `src/ig_orchestrator/gui/app.py` cambia el label a `Detener proceso` y alinea
  mensajes de detencion/interrupcion.
* `tests/test_retry_policy.py` cubre el tope de un reintento y que otros
  errores no se capan.
* `Agents.md`, `README.md` y `tasks/task-gui.md` documentan el comportamiento.
* Version actualizada a `1.26.16`.

### Resumen

`Media not found or unavailable` deja de consumir todo el presupuesto de
`MAX_RETRIES`, y la GUI habla de detener el proceso para reanudar despues.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_retry_policy.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.15 - Patch - Lote actual: orden Username y Guardar seleccion

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.15.md` documenta el orden por username, la seleccion
  multiple y el boton `Guardar selección`.

### Modificado

* `src/ig_orchestrator/gui/app.py` permite ordenar la tabla por `Username`
  (A-Z / Z-A), usa `selectmode=extended` y anade `Guardar selección` para
  persistir solo las filas elegidas como DRAFT, dejando el resto en mesa de
  trabajo sin ID de lote.
* `tests/test_gui_services.py` cubre helpers de orden y el guardado de
  seleccion con resto en memoria.
* `README.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.15`.

### Resumen

Desde la mesa de trabajo se puede reordenar el lote por nombre y partir
varias cuentas en lotes distintos sin vaciar a mano las que se quieren dejar
para despues.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.14 - Patch - Editor: checkboxes juntos y foco al final de URLs

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.14.md` documenta el layout de flags del editor y el caret
  al final tras pegar o normalizar URLs.

### Modificado

* `src/ig_orchestrator/gui/app.py` agrupa `Stories` y `New account` en un frame
  horizontal con checkboxes Tk (label clicable) y mueve el foco al final del
  textarea tras `Pegar` y `Normalizar`.
* `tests/test_gui_services.py` cubre el foco al final al pegar y normalizar.
* `README.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.14`.

### Resumen

Los flags del editor dejan de separarse en extremos y el listado de URLs
mantiene el caret al final al pegar o normalizar, sin tener que scrollear a
mano.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.13 - Patch - Catalogo: highlight en lote, Activar, foco y filtro

Fecha: 2026-08-05

### Creado

* `tasks/Patch_v1.26.13.md` documenta el highlight temporal, `Activar`, la
  preservacion de foco y el boton de limpiar busqueda.

### Modificado

* `src/ig_orchestrator/gui/app.py` resalta en amarillo las cuentas del lote
  actual, anade `Activar` y el boton `❌` del filtro, y conserva seleccion y
  scroll al repintar el catalogo.
* `src/ig_orchestrator/gui/account_catalog_service.py` expone `enable` para
  reactivar cuentas `DISABLED` o `INACTIVE`.
* `tests/test_gui_services.py` cubre colores con `in_batch` y la reactivacion.
* `README.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.13`.

### Resumen

Al armar un lote se ve de un vistazo que cuentas ya estan en la tabla, se puede
reactivar un Delete, el catalogo no salta al usar el menu contextual y el
filtro se limpia con un boton compacto.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.

## v1.26.12 - Patch - Estados, favoritos y agrupacion del catalogo

Fecha: 2026-08-01

### Creado

* `tasks/Patch_v1.26.12.md` documenta los nuevos estados visuales, el orden por
  ruta y la reactivacion automatica.

### Modificado

* `account_history` incorpora `is_favorite` y el estado `INACTIVE` mediante una
  migracion compatible con bases existentes.
* El repositorio y el servicio de catalogo persisten favoritos e inactividad,
  muestran tambien las bajas logicas y ordenan las cuentas por categoria,
  `field1` y username.
* El menu contextual del GUI permite marcar una cuenta inactiva, agregar o
  quitar el tag favorito y mantiene `Delete` como baja logica.
* El orquestador reactiva cuentas inactivas cuando realmente empiezan a
  procesarse, sin hacerlo en dry-run.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el comportamiento.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y las pruebas de smoke
  actualizan la version a `1.26.12`.

### Resumen

El catalogo diferencia visualmente las cuentas prioritarias, pausadas y dadas
de baja, conserva la clasificacion en SQLite y agrupa las cuentas activas por
su ruta historica.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_batch_orchestrator.py tests\test_db_repositories.py tests\test_package_smoke.py`.
* `python -m pytest -q`.
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.11 - Patch - Distribucion vertical del GUI

Fecha: 2026-07-26

### Creado

* `tasks/Patch_v1.26.11.md` documenta la nueva distribucion, el orden de las
  acciones, los scrollbars y la seleccion simple del catalogo.

### Modificado

* `src/ig_orchestrator/gui/app.py` mantiene el catalogo a la izquierda, apila
  el editor y el lote en la zona derecha, mueve todas las acciones del editor a
  una columna izquierda, agrega scroll visible a URLs y cambia el texto del
  checkbox a `Stories`.
* La seleccion simple del catalogo carga el username en el editor; el doble
  click conserva la apertura de Instagram.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen la nueva interfaz.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la version a `1.26.11`.

### Resumen

La zona de trabajo aprovecha todo el ancho derecho para editar arriba y revisar
el lote abajo, con acciones alineadas y scrollbars visibles en las tres areas
solicitadas.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py tests\test_package_smoke.py`
  (`56 passed`).
* `python -m pytest -q` (`196 passed`).
* `python -m compileall -q src tests`.
* Construccion temporal de la ventana Tkinter: orden de acciones correcto,
  etiqueta `Stories`, tres scrollbars visibles y paneles horizontal/vertical.
* `git diff --check`.

## v1.26.10 - Patch - Flujo de alta y dimensiones del GUI

Fecha: 2026-07-24

### Creado

* `tasks/Patch_v1.26.10.md` documenta la deseleccion del editor, el pegado
  rapido, los anchos adaptativos y el sonido de finalizacion.

### Modificado

* `src/ig_orchestrator/gui/app.py` agrega `Pegar/Agregar`, deselecciona la
  cuenta al limpiar, reordena y dimensiona las columnas, adapta el catalogo al
  username mas largo y reproduce el aviso sonoro al terminar un lote.
* `tests/test_gui_services.py` cubre el nuevo comportamiento y los calculos de
  presentacion.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el flujo actualizado.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la version a `1.26.10`.

### Resumen

El editor permite volver de forma explicita al modo de alta, incorpora una
accion de pegar y guardar, aprovecha mejor el ancho de la ventana y avisa
audiblemente cuando termina el procesamiento.

### Pruebas ejecutadas

* `python -m pytest -q tests/test_gui_services.py tests/test_package_smoke.py`
  (`55 passed`).
* `python -m pytest -q` (`195 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.9 - Patch - Contexto de lote nuevo y lote registrado

Fecha: 2026-07-23

### Creado

* `tasks/Patch_v1.26.9.md` documenta los contextos del editor y la transición
  segura a un lote nuevo.

### Modificado

* `src/ig_orchestrator/gui/app.py` muestra el contexto actual, diferencia
  `Registrar lote nuevo` de `Actualizar lote`, agrega `Nuevo lote`, reemplaza
  `Limpiar lote` por `Eliminar todo` y bloquea la edición de lotes ya iniciados.
* `src/ig_orchestrator/gui/batch_draft_service.py` y
  `src/ig_orchestrator/gui/batch_resume_service.py` permiten persistir y
  recuperar un `DRAFT` registrado sin cuentas, manteniendo bloqueada su
  ejecución hasta que vuelva a contener al menos una.
* `tests/test_gui_services.py` cubre las etiquetas de contexto, el reinicio de
  IDs y estado al crear un lote nuevo y el aviso con nombre e ID antes de
  eliminar todas las cuentas de un lote registrado.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el flujo actualizado.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la versión a `1.26.9`.

### Resumen

Preparar un segundo lote ya no puede reutilizar silenciosamente el ID de un
borrador recuperado: `Nuevo lote` crea un contexto limpio y el estado visible
indica en todo momento si el siguiente guardado crea o actualiza.

### Pruebas ejecutadas

* `python -m pytest -q tests\test_gui_services.py` (`46 passed`).
* `python -m compileall -q src tests`.
* `python -m pytest -q` (`191 passed`).
* `git diff --check`.

## v1.26.8 - Patch - Doble click del catálogo

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.8.md` documenta el ajuste del evento.

### Modificado

* `src/ig_orchestrator/gui/app.py` carga el username seleccionado y sus datos
  de catálogo en el editor antes de abrir Instagram con doble click.
* `tests/test_gui_services.py` agrega la prueba de regresión de las dos acciones.
* `README.md` y `tasks/task-gui.md` aclaran el comportamiento.
* Version actualizada a `1.26.8`.

### Pruebas ejecutadas

* `pytest -q tests/test_gui_services.py tests/test_package_smoke.py`
  (`46 passed`).
* `pytest -q` (`186 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.7 - Patch - Maestro de lotes y cierre manual

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.7.md` documenta el alcance, los estados y la compatibilidad
  de persistencia del patch.

### Modificado

* `src/ig_orchestrator/models/input_batch.py` incorpora el estado `DRAFT` para
  distinguir lotes guardados de ejecuciones.
* `src/ig_orchestrator/input/batch_creation_service.py`,
  `src/ig_orchestrator/input/__init__.py` y
  `src/ig_orchestrator/gui/batch_draft_service.py` permiten crear y actualizar
  borradores conservando el batch id y bloquean cualquier edición tras la
  primera ejecución.
* `src/ig_orchestrator/gui/batch_resume_service.py` agrega el maestro conjunto,
  activación y borrado seguro de drafts, finalización manual de cuentas y la
  política que habilita el renombrador al cerrar todas las cuentas.
* `src/ig_orchestrator/gui/app.py` abre el catálogo con doble click, reemplaza
  el selector de pendientes por `Lotes / ejecuciones`, expone las acciones de
  borrador y agrega `Completar` al menú contextual de cuentas.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` diferencia la
  ausencia total de respuesta como `NO_BOT_RESPONSE`, evita una segunda espera
  redundante y deja que la política existente finalice la URL al agotar
  reintentos sin bloquear el lote.
* `tests/test_gui_services.py` y `tests/test_bot_conversation_service.py`
  cubren los nuevos estados, acciones y el silencio del bot.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el nuevo flujo.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y
  `tests/test_package_smoke.py` actualizan la versión a `1.26.7`.

### Pruebas ejecutadas

* `pytest -q tests/test_gui_services.py tests/test_bot_conversation_service.py tests/test_account_orchestrator.py`
  (`59 passed`).
* `pytest -q` (`185 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.6 - Patch - Estado de Treeview durante la ejecucion

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.6.md` documenta el error y la correccion.

### Modificado

* `src/ig_orchestrator/gui/app.py` deja de pasar la opcion Tcl inexistente
  `-state` a `ttk.Treeview` y usa la API `Widget.state()` para mantener
  seleccionable `Lote actual` durante la ejecucion.
* `tests/test_gui_services.py` agrega una prueba de regresion para el manejo de
  estados ttk.
* Version del paquete actualizada a `1.26.6`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q`
  (`42 passed`).
* `python -m pytest -q` (`182 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.26.5 - Patch - Control de cuentas y ajustes de GUI

Fecha: 2026-07-22

### Creado

* `tasks/Patch_v1.26.5.md` documenta el alcance del patch.

### Modificado

* `src/ig_orchestrator/gui/app.py` ajusta la ventana a media pantalla, compacta
  `Lote actual`, agrega scrollbars, conserva la seleccion durante el refresco,
  muestra el orden persistido al ejecutar y oculta los botones de reordenado.
* El catalogo incorpora click derecho `Abrir` / `Delete`; la baja usa
  `account_history.status = DISABLED` y no elimina datos.
* El campo `path` de `New account` es ahora un combobox editable con valores
  distintos de `account_history.field1`.
* La recuperacion y `Renombrar` releen desde SQLite la fecha global, el flag de
  cuenta nueva, `ownerId`, `startInitDate` y `path`, evitando depender del
  borrador en memoria despues de cancelar y reanudar.
* `Eliminar` permanece activo durante un lote para marcar una cuenta pendiente
  o en proceso como `FAILED` y sus jobs no terminales como `FAILED_FINAL`, con
  `MANUAL_ACCOUNT_REMOVAL`; los orquestadores respetan esa baja cooperativa.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` describen el comportamiento.
  Version del paquete actualizada a `1.26.5`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_account_orchestrator.py
  tests/test_batch_orchestrator.py -q` (`52 passed`).
* `python -m pytest -q` (`181 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.4 - Patch - Recuperacion y seguimiento de batches desde GUI

Fecha: 2026-07-19

### Creado

* `src/ig_orchestrator/gui/batch_resume_service.py` consulta batches con trabajo
  reanudable, reconstruye el borrador completo, resume estados por cuenta y
  permite finalizar o marcar como interrumpido un lote.
* `tasks/Patch_v1.26.4.md` documenta el alcance del patch.

### Modificado

* `src/ig_orchestrator/gui/app.py` agrega el selector `Ejecuciones pendientes`,
  las acciones `Reanudar seleccionado` y `Dar por finalizado`, la recuperacion
  de `Lote actual` y estados por cuenta actualizados en color desde SQLite.
* `src/ig_orchestrator/gui/batch_draft_service.py`, `db/schema.sql` y
  `db/migrations.py` persisten de forma compatible la fecha global del lote y
  la asociacion de cuentas nuevas con sus parametros de renombrado.
* Al cancelar un proceso de batch desde la GUI, su estado queda `PARTIAL` sin
  alterar cuentas, URL jobs, errores ni archivos ya registrados.
* `tests/test_gui_services.py` cubre persistencia de metadatos, listado y
  reconstruccion de pendientes, progreso, cancelacion y finalizacion manual.
* `README.md`, `PLAN.md` y `tasks/task-gui.md` documentan el flujo y las
  respuestas de persistencia. Version actualizada a `1.26.4`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_db_repositories.py
  tests/test_main_batch_modes.py tests/test_batch_orchestrator.py -q`
  (`42 passed`).
* `python -m pytest -q` (`174 passed`).

## v1.26.3 - Patch - Carpetas bajo demanda y limpieza de lote

Fecha: 2026-07-18

### Creado

* `src/ig_orchestrator/filesystem/batch_cleanup.py` implementa la limpieza
  conservadora posterior a cada lote real: temporales `telegram_media*` en la
  raiz de descargas y duplicados `*_1.mp4` verificados dentro de `reels/`.
* `tests/test_batch_cleanup.py` cubre temporales, alcance no recursivo y
  eliminacion de duplicados solo cuando existe el original.
* `tasks/Patch_v1.26.3.md` documenta el alcance y los criterios del patch.

### Modificado

* `src/ig_orchestrator/filesystem/folder_service.py` crea solo la carpeta raiz
  de la cuenta y deja de generar subcarpetas especulativas.
* `src/ig_orchestrator/filesystem/file_mover.py` crea `story/`, `reels/` o
  `highlights/` justo antes de mover el primer archivo destinado a ellas.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` ejecuta la limpieza
  al finalizar lotes reales, incluidos lotes parciales o con fallo de
  infraestructura, y la omite en dry-run.
* `src/ig_orchestrator/main.py` entrega al orquestador las rutas de descargas y
  trabajo necesarias para limitar la limpieza a las cuentas del lote.
* `src/ig_orchestrator/gui/app.py` agrega el boton `Clean` a la caja de estados
  para vaciar la consola sin alterar el proceso.
* `PLAN.md`, `README.md`, `tasks/Tarea8.md`, `tasks/Tarea17.md` y
  `tasks/task-gui.md` documentan las nuevas reglas.
* Tests de carpetas, movimiento, orquestadores y smoke adaptados al nuevo
  comportamiento. Version del paquete actualizada a `1.26.3`.

### Pruebas ejecutadas

* `python -m pytest tests/test_folder_service.py tests/test_file_mover.py
  tests/test_batch_cleanup.py tests/test_batch_orchestrator.py
  tests/test_package_smoke.py tests/test_gui_services.py -q` (`51 passed`).
* `python -m pytest -q` (`171 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.2 - Patch - Nuevas cuentas desde GUI y renombrador

Fecha: 2026-07-17

### Modificado

* `src/ig_orchestrator/gui/app.py` elimina el boton ambiguo `Agregar cuenta
  nueva` del catalogo y agrega el checkbox condicional `New account` al editor,
  con `ownerId`, `startInitDate` y `path` obligatorios. Las filas nuevas se
  incorporan al lote y al catalogo al pulsar `Agregar / Actualizar`.
* `src/ig_orchestrator/gui/batch_draft.py` y
  `src/ig_orchestrator/gui/batch_draft_service.py` modelan y validan los datos
  adicionales sin mezclarlos con la fecha de descarga de la cuenta.
* `src/ig_orchestrator/db/account_history_repository.py` y
  `src/ig_orchestrator/gui/account_catalog_service.py` conservan y exponen
  `ownerId`, `path` y `startInitDate` en el catalogo global.
* `src/ig_orchestrator/gui/process_runner.py` agrega un bloque repetible
  `--new-account USERNAME OWNER_ID START_INIT_DATE PATH` por cada cuenta nueva
  antes de `--no-duplicated --move-renamed`.
* `tests/test_gui_services.py` cubre campos obligatorios, persistencia del
  catalogo, filtrado de cuentas nuevas y comandos con multiples cuentas.
* `README.md` y `tasks/task-gui.md` documentan el nuevo flujo y el contrato del
  comando externo.
* Version actualizada a `1.26.2`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q`
  (`32 passed`).
* `python -m pytest -q` (`167 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.1 - Patch - Timestamp y renombrado manual desde GUI

Fecha: 2026-07-16

### Modificado

* `src/ig_orchestrator/gui/app.py` agrega fecha y hora local con milisegundos a
  cada linea de la consola de estado y situa el boton contextual `Renombrar`
  junto a las acciones de ejecucion. El boton solo se habilita al completar
  correctamente un lote real y transmite la salida del renombrador sin
  bloquear Tkinter.
* `src/ig_orchestrator/gui/process_runner.py` construye el comando para
  `ManualRenameFiles/main.py` con `--newRename`, la fecha global de la GUI,
  `--no-duplicated` y `--move-renamed`.
* `tests/test_gui_services.py` cubre el comando externo y el timestamp aplicado
  a todas las lineas.
* `tests/test_package_smoke.py` verifica la nueva version del paquete y del
  entrypoint.
* `README.md` y `tasks/task-gui.md` documentan el flujo, la ubicacion y las
  reglas de habilitacion del nuevo boton.
* Version actualizada a `1.26.1`.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py -q` (`21 passed`).
* `python -m pytest -q` (`161 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.26.0 - Tarea GUI 2 - Ejecucion y progreso desde GUI

Fecha: 2026-07-15

### Modificado

* `src/ig_orchestrator/gui/account_catalog_service.py` ordena el catalogo
  alfabeticamente sin distinguir mayusculas y minusculas.
* `src/ig_orchestrator/gui/app.py` diferencia `Registrar lote` de `Ejecutar`,
  lanza el lote registrado sin bloquear Tkinter, transmite la salida al cuadro
  inferior y muestra progreso de cuentas e items.
* `src/ig_orchestrator/gui/process_runner.py` ejecuta `run_continue --batch-id`
  en un subproceso cancelable con salida sin buffer.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` ofrece progreso
  por item, incluyendo stories y reintentos sin incrementar el total.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` informa tambien el
  progreso de cuentas durante dry-run.
* `src/ig_orchestrator/main.py` activa el detalle por item solo para procesos
  nacidos desde GUI y permite dry-run de `run_continue` sin abrir Telegram.
* `tests/test_gui_services.py` y `tests/test_account_orchestrator.py` cubren el
  orden alfabetico, el comando del subproceso y el progreso por item.
* `README.md` documenta el registro, la ejecucion y los indicadores de progreso.
* Version actualizada a `1.26.0`.

### Pruebas ejecutadas

* `python -m pytest -q` (`159 passed`).
* `python -m compileall -q src tests`.
* `git diff --check`.

## v1.25.5 - Patch - URLs equivalentes de publicaciones Instagram

Fecha: 2026-07-11

### Modificado

* `src/ig_orchestrator/gui/batch_draft_service.py` identifica publicaciones
  por su shortcode y considera duplicadas las variantes `/p/{shortcode}/` y
  `/reel/{shortcode}/`, conservando la primera URL pegada.
* `tests/test_gui_services.py` cubre la normalizacion y el contador de
  duplicados para ambas variantes de una misma publicacion.
* Version actualizada a `1.25.5`.

### Pruebas ejecutadas

* `python -m pytest -q` (`155 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.25.4 - Patch - Deduplicacion efectiva de URLs en GUI

Fecha: 2026-07-11

### Modificado

* `src/ig_orchestrator/gui/batch_draft_service.py` separa el parseo de URLs de
  su deduplicacion para que `Normalizar` y `Agregar / Actualizar` conserven
  solo la primera aparicion y el indicador pueda contar las repetidas.
* `tests/test_gui_services.py` corrige el caso de prueba con comillas y comas
  y verifica tanto el resultado normalizado como el contador de duplicados.
* Version actualizada a `1.25.4`.

### Pruebas ejecutadas

* `python -m pytest -q` (`153 passed`).
* `python -m compileall -q src tests`.
* `git diff --check` (solo avisos de normalizacion LF/CRLF).

## v1.25.3 - Patch - Lanzadores de Windows

Fecha: 2026-07-11

### Creado

* `ejecutar_gui.bat` abre la interfaz grafica desde la raiz del proyecto.
* `ejecutar_run_continue.bat` solicita un `batch_id`, valida que sea numerico
  y solo ejecuta `run_continue` cuando se ha introducido un valor.

### Resumen

Los dos lanzadores configuran `PYTHONPATH`, usan el entorno virtual local si
existe y funcionan aunque se invoquen desde otro directorio.

### Pruebas ejecutadas

* Inspeccion de comandos y validacion de los lanzadores sin ejecutar Telegram.

## v1.25.2 - Patch - Deduplicacion de URLs en GUI

Fecha: 2026-07-08

### Modificado

* `src/ig_orchestrator/gui/batch_draft_service.py` elimina URLs repetidas tras
  limpiar comillas y comas, conservando la primera aparicion.
* `tests/test_gui_services.py` cubre normalizacion y guardado con URLs
  duplicadas en formato limpio, con comillas y con coma final.
* Version actualizada a `1.25.2`.

### Resumen

Los botones `Normalizar` y `Agregar / Actualizar` usan la misma normalizacion,
por lo que las URLs duplicadas se eliminan antes de actualizar la caja o guardar
la cuenta en el lote.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q` (`18 passed`)
* `python -m compileall -q src tests`

## v1.25.1 - Patch - Ajustes GUI de lote

Fecha: 2026-07-07

### Modificado

* `src/ig_orchestrator/gui/app.py` inicializa `Batch name` desde el ultimo
  lote ejecutado en SQLite, rellena fechas de lote y cuenta con hoy, y mantiene
  la fecha de cuenta tras `Agregar / Actualizar`.
* `src/ig_orchestrator/gui/batch_draft_service.py` normaliza URLs pegadas con
  comillas, comas y coma final, compartiendo la misma logica entre el boton
  `Normalizar` y el guardado del lote.
* `tasks/task-gui.md` y `README.md` documentan el nuevo comportamiento.
* Version actualizada a `1.25.1`.

### Resumen

La GUI arranca con datos mas utiles para el flujo diario y acepta listados de
URLs copiados tanto como lista limpia por lineas como en formato con comillas y
comas.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_package_smoke.py -q` (`16 passed`)
* `python -m compileall -q src tests`
* `python -m pytest -q` (`150 passed`)

## v1.25.0 - Tarea GUI 1 - Editor de lote y persistencia SQLite

Fecha: 2026-07-06

### Creado

* `src/ig_orchestrator/input/batch_creation_service.py` como servicio comun
  para crear lotes SQLite desde JSON o GUI.
* Paquete `src/ig_orchestrator/gui/` con borradores de lote, validacion,
  catalogo de cuentas, ventana Tkinter y placeholder de runner.
* `tests/test_gui_services.py` con cobertura de persistencia del borrador,
  catalogo desde `account_history`, catalogo desde `config/batch.json`,
  cuenta vacia invalida y batch duplicado.

### Modificado

* `src/ig_orchestrator/input/batch_importer.py` delega la persistencia en el
  servicio comun sin cambiar el contrato CLI existente.
* `src/ig_orchestrator/main.py` agrega `python -m ig_orchestrator gui`.
* `src/ig_orchestrator/input/__init__.py` expone los DTOs de creacion comun.
* Version actualizada a `1.25.0`.

### Resumen

La aplicacion puede abrir una GUI de escritorio con Tkinter para crear un lote,
seleccionar cuentas frecuentes desde SQLite o `config/batch.json`, editar filas
del borrador, validar URLs de Instagram y guardar el batch en SQLite sin tocar
`config/batch.json`. La ejecucion desde la ventana queda reservada para la
Tarea GUI 2.

### Pruebas ejecutadas

* `python -m pytest tests/test_gui_services.py tests/test_batch_importer.py tests/test_package_smoke.py tests/test_main_batch_modes.py -q` (`17 passed`)
* `python -m compileall -q src tests`
* `python -m pytest -q` (`144 passed`)
* `git diff --check` (solo avisos de normalizacion LF/CRLF)

## v1.24.5 - Patch - Post-proceso Manual Rename Files

Fecha: 2026-07-05

### Creado

* `src/ig_orchestrator/orchestration/post_processing.py` para ejecutar un
  comando externo opcional tras batch y reporte correctos.
* `D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat` como wrapper externo
  de automatizacion equivalente a `MRF.bat`, pero sin `pause`.
* `tests/test_post_processing.py` con pruebas de comando deshabilitado,
  configuracion incompleta, exito y fallo de `.cmd`.

### Modificado

* `src/ig_orchestrator/main.py` ejecuta el post-proceso solo despues de generar
  los reportes y solo si no hubo fallo de infraestructura en el batch.
* `src/ig_orchestrator/settings.py`, `.env.example` y `config/app.example.json`
  agregan `POST_PROCESS_ENABLED` y `POST_PROCESS_COMMAND`.
* `README.md` documenta que el wrapper recomendado es
  `D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat` y que `batch.json`
  no recibe parametros especificos del renombrador.
* Version actualizada a `1.24.5`.

### Pruebas ejecutadas

* `python -m pytest tests/test_settings.py tests/test_post_processing.py tests/test_package_smoke.py tests/test_main_batch_modes.py -q` (`14 passed`)
* `python -m pytest -q` (`139 passed`)
* `python -m compileall -q src tests`

## v1.24.4 - Patch - Prioridad de cuentas por stories y volumen

Fecha: 2026-06-24

### Modificado

* La importacion ordena las cuentas en memoria antes de persistirlas.
* Las cuentas con `download_stories = true` y sin URLs se insertan y procesan
  primero para anticiparse a la desaparicion de stories.
* Las cuentas restantes se ordenan de menor a mayor numero de URLs procesables;
  los empates conservan el orden original del JSON.
* No se agregaron campos, consultas de orden especiales ni migraciones SQLite.
* `README.md`, `PLAN.md`, `Agents.md` y `tasks/Tarea6.md` documentan el orden.
* Se agrego una prueba de importacion que verifica prioridad, orden estable y
  conteo de URLs deduplicadas.
* Version actualizada a `1.24.4`.

### Pruebas ejecutadas

* `python -m pytest tests/test_batch_importer.py tests/test_batch_json_parser.py tests/test_batch_orchestrator.py tests/test_main_batch_modes.py -q` (`19 passed`)
* `python -m pytest -q` (`134 passed`)
* `python -m compileall -q src tests`
* `git diff --check`

## v1.24.3 - Patch - Previews duplicados en posts de fotos

Fecha: 2026-06-24

### Modificado

* Las respuestas que contienen exclusivamente documentos de imagen con nombre
  original descartan los previews comprimidos sin nombre antes de persistirlos.
* Los previews siguen conservandose cuando son la unica media disponible.
* Las respuestas mixtas con video y fotos sin nombre mantienen todas las fotos,
  preservando el comportamiento requerido para stories.
* Se agrego una prueba de regresion basada en el caso real que generaba archivos
  `telegram_media_*` junto a los JPG numericos.
* Version actualizada a `1.24.3`.

### Pruebas ejecutadas

* `python -m pytest` (`133 passed`)
* `python -m compileall -q src tests`
* `git diff --check`

## v1.24.2 - Patch - Stories sin reintento y media mixta completa

Fecha: 2026-06-21

### Modificado

* El parser reconoce mediante expresion regular
  `Stories for {username} not found` como error definitivo
  `STORIES_NOT_FOUND`.
* Las respuestas mixtas de stories conservan simultaneamente documentos con
  nombre, videos y fotos sin nombre original.
* Las fotos de stories se renombran como
  `username-YYYYMMDD_HHMMSS.jpg`, usando sufijo numerico si coinciden.
* Se agregaron pruebas para el caso real de username dinamico y una respuesta
  de cinco stories formada por un video y cuatro fotos.
* Version actualizada a `1.24.2`.

### Pruebas ejecutadas

* `python -m pytest` (`132 passed`)
* `python -m compileall -q src tests`
* `git diff --check`

## v1.24.1 - Patch - Carpeta de logs unica por ejecucion

Fecha: 2026-06-21

### Modificado

* `main.py` fija un unico timestamp al inicio de `--run`, `run_continue` y
  `--dry-run`.
* `AccountOrchestratorConfig` transporta el inicio y la carpeta de logs de la
  ejecucion completa.
* Los logs de todas las cuentas, batches unidos y reintentos se escriben bajo
  una sola carpeta `logs/YYYYMMDD_HHMMSS`.
* Si un username se procesa mas de una vez en la misma ejecucion, se agrega
  contenido al mismo archivo en lugar de crear otra carpeta.
* `README.md` y `Agents.md` documentan la regla.

### Pruebas ejecutadas

* `python -m pytest`

## v1.24.0 - Tarea 24 - Lotes unicos, join e historico de cuentas

Fecha: 2026-06-21

### Creado

* `tasks/Tarea24.md`.
* `src/ig_orchestrator/models/account_history.py`.
* `src/ig_orchestrator/db/account_history_repository.py`.
* `src/ig_orchestrator/input/batch_file_service.py`.
* Tests de backup/limpieza, modos join, historico global, unicidad y progreso.

### Modificado

* Parser e importador para ignorar entradas vacias, rechazar `batch_name`
  repetidos y poblar `account_history`.
* Schema/migracion SQLite con `account_history` e indice unico para
  `input_batches.batch_name`.
* CLI para `--join-after-pending-batch-id` y
  `--join-before-pending-batch-id`.
* Orquestador de batch para mostrar avance por cuenta.
* `README.md`, `PLAN.md` y `Agents.md` con el nuevo contrato operativo.
* Version de paquete actualizada a `1.24.0`.

### Resumen

Cada lote tiene ahora una identidad unica. Un lote interrumpido se continua
desde SQLite y un lote nuevo puede encadenarse antes o despues de pendientes de
otro batch. La importacion real crea un backup, limpia el JSON reutilizable,
mantiene un historico global de usernames y muestra progreso compacto.

### Pruebas ejecutadas

* `python -m pytest` (`125 passed`)

## v1.21.5 - Patch - Resumen de reporte y duplicados persistidos

Fecha: 2026-06-17

### Creado

* Tabla `duplicate_url_jobs` para persistir URLs duplicadas detectadas durante la importacion.
* Tests para migracion/creacion de la tabla de duplicados en SQLite.
* Tests para importar duplicados de forma idempotente y reconstruirlos en reportes.

### Modificado

* `src/ig_orchestrator/db/schema.sql` para crear `duplicate_url_jobs` e indices relacionados con `batch_id`, `account_id`, `run_id` y `duplicate_of_url_job_id`.
* `src/ig_orchestrator/input/batch_json_parser.py` para conservar ocurrencias duplicadas ademas de las URLs unicas procesables.
* `src/ig_orchestrator/input/batch_importer.py` para guardar duplicados y enlazarlos al `url_job` original.
* `src/ig_orchestrator/db/url_job_repository.py` para asociar duplicados sin `run_id` a la ejecucion actual.
* `src/ig_orchestrator/reports/markdown_report_builder.py` para agregar resumen por username y tabla final de URLs duplicadas.
* `src/ig_orchestrator/reports/__init__.py` y `src/ig_orchestrator/input/__init__.py` para exponer los nuevos DTOs.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.5`.

### Resumen

El reporte de ejecucion incluye ahora un resumen superior por username con URLs
analizadas, URLs no procesadas, URLs duplicadas y archivos descargados. Las
URLs duplicadas quedan persistidas en SQLite y se muestran al final del reporte
en una tabla separada, de forma reconstruible aunque una ejecucion se corte y se
reanude.

### Pruebas ejecutadas

* `python -m pytest tests\test_markdown_report_builder.py tests\test_batch_importer.py tests\test_batch_json_parser.py tests\test_db_repositories.py tests\test_account_orchestrator.py tests\test_batch_orchestrator.py`

## v1.21.4 - Patch - Trazabilidad de run_id y reporte con id de job

Fecha: 2026-06-17

### Creado

* Tests para verificar que los `url_jobs` quedan asociados al run de cuenta y al run de batch.

### Modificado

* `src/ig_orchestrator/reports/markdown_report_builder.py` para agregar las columnas `N` e `Id Job` al reporte Markdown.
* `src/ig_orchestrator/db/url_job_repository.py` para asociar jobs sin `run_id` a una ejecucion.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` y `src/ig_orchestrator/orchestration/batch_orchestrator.py` para registrar `run_id` al iniciar una ejecucion sin sobrescribir jobs ya asociados.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.4`.

### Resumen

Los reportes de ejecucion incluyen ahora una correlacion secuencial `N` y el
identificador real de `url_jobs.id`. Al iniciar un run, los `url_jobs` que aun
no tienen `run_id` quedan vinculados a la ejecucion actual, preservando
asociaciones previas.

### Pruebas ejecutadas

* `python -m pytest tests\test_markdown_report_builder.py tests\test_account_orchestrator.py tests\test_batch_orchestrator.py tests\test_batch_importer.py tests\test_batch_json_parser.py`

## v1.21.3 - Patch - Modo run_continue y deduplicacion de descargas

Fecha: 2026-06-16

### Creado

* Test para localizar batches con trabajo reanudable desde SQLite.
* Test de `run_continue` sin importar JSON.
* Test para descartar descargas duplicadas exactas tipo `archivo.mp4` y `archivo_1.mp4`.

### Modificado

* `src/ig_orchestrator/main.py` para agregar el subcomando `run_continue`, que procesa batches existentes desde SQLite sin leer `batch.json`.
* `src/ig_orchestrator/db/batch_repository.py` para listar batches con cuentas y URLs en estados reanudables.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` para eliminar duplicados exactos antes de crear registros `download_files`.
* `.vscode/launch.json` para agregar `Ejecutar: run_continue` y `Depurar: run_continue`.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.3`.

### Resumen

El proceso puede reanudarse con `python -m ig_orchestrator run_continue`, leyendo
solo SQLite y procesando batches que tengan cuentas `PENDING`, `PROCESSING` o
`PARTIAL` con URLs en `PENDING`, `SENT_TO_BOT`, `WAITING_DOWNLOAD`,
`RETRY_PENDING` o `FAILED_TEMPORARY`. Las descargas duplicadas exactas con
sufijo numerico se filtran antes de persistir y mover archivos.

### Pruebas ejecutadas

* `python -m pytest tests\test_db_repositories.py tests\test_bot_conversation_service.py tests\test_package_smoke.py -q`
* `python -m json.tool .vscode\launch.json`
* `python -m pytest -q`

## v1.21.2 - Patch - Descarga directa de media de Telegram

Fecha: 2026-06-16

### Creado

* Tests para descarga directa desde mensajes del bot con documento y para previews sin nombre original.
* Tests para reanudar cuentas `PROCESSING` y URLs interrumpidas en `WAITING_DOWNLOAD`.

### Modificado

* `src/ig_orchestrator/telegram/telegram_client.py` para exponer `download_message_media` usando Telethon.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` para descargar media del bot directamente con Telethon, conservar documentos con nombre original y promover previews solo cuando no hay documentos finales.
* `src/ig_orchestrator/orchestration/account_orchestrator.py` para reintentar URLs interrumpidas en `SENT_TO_BOT` o `WAITING_DOWNLOAD`.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` para reanudar cuentas `PROCESSING` o `PARTIAL`.
* `src/ig_orchestrator/reports/markdown_report_builder.py` para agregar la columna `Cantidad`.
* `pyproject.toml`, `src/ig_orchestrator/__init__.py` y `tests/test_package_smoke.py` para actualizar la version a `1.21.2`.

### Resumen

La descarga ya no depende de tener Telegram Desktop abierto: Telethon descarga
directamente los media recibidos desde el bot. Los posts/reels con documentos
usan el nombre original enviado por el bot, mientras que las stories que solo
llegan como previews se guardan con nombre fallback por id de mensaje. Las
ejecuciones cortadas pueden retomarse procesando cuentas y URLs que quedaron a
medio camino.

### Pruebas ejecutadas

* `pytest tests\test_account_orchestrator.py tests\test_batch_orchestrator.py tests\test_bot_conversation_service.py tests\test_markdown_report_builder.py`
* `pytest`

## v1.21.1 - Ejecucion real con Telegram

Fecha: 2026-06-16

### Creado

* Test de smoke para el modo real usando servicio de Telegram simulado, archivo descargado falso, movimiento a carpeta de cuenta y reporte Markdown.

### Modificado

* `src/ig_orchestrator/main.py` para conectar el flujo real de `--input`: inicializa SQLite, importa JSON, arranca Telethon, procesa el batch con `BotConversationService`, mueve archivos con `UrlJobProcessor` y genera reporte Markdown.
* `.vscode/launch.json` para que `Ejecutar: ig_orchestrator` y `Depurar: ig_orchestrator` usen `config/batch.json --run` en lugar de `--dry-run`.
* `README.md` para documentar la ejecucion real, el modo `--run`, el uso de Telegram/Telethon y las salidas esperadas.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.1`.

### Resumen

La aplicacion ya puede lanzarse con datos reales desde CLI o VS Code usando `config/batch.json`: crea o reutiliza SQLite, importa el lote, conecta con Telegram mediante Telethon, envia cada URL al bot, detecta descargas, mueve archivos a las carpetas correspondientes de la cuenta, aplica reintentos y escribe reporte Markdown. El modo `--dry-run` queda como validacion sin efectos externos.

### Pruebas ejecutadas

* `python -m pytest -q`
* `python -m ig_orchestrator --input config\batch.json --dry-run`

## Documentacion README operativa

Fecha: 2026-06-16

### Modificado

* `README.md` para documentar configuracion, entorno, ejecucion por CLI y VS Code, flujo dry-run, flujo real previsto, SQLite, logs, descargas, reportes, errores, reintentos y responsabilidades por modulo.

### Resumen

El README ahora explica como preparar `.venv`, `.env`, `pyproject.toml`, batches JSON y sesiones Telethon, ademas de aclarar que el entrypoint actual soporta `--dry-run` y que la ejecucion real completa aun no esta cableada desde `main.py`.

### Pruebas ejecutadas

* `python -m ig_orchestrator --input config\batch.json --dry-run`
* `python -m pytest -q`

## v1.21.0 - Tarea 21 - Tests minimos obligatorios

Fecha: 2026-06-15

### Creado

* No se crearon modulos productivos nuevos; la suite obligatoria ya estaba cubierta por tests existentes.

### Modificado

* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.21.0`.
* `CHANGELOG.md` para documentar el cierre de la cobertura minima obligatoria.

### Resumen

Se verifico que la suite minima obligatoria cubre `settings`, `batch_json_parser`,
`batch_importer`, `url_classifier`, `retry_policy`, `bot_response_parser`,
`file_watcher`, `file_classifier`, `folder_service`, `file_mover`, repositorios
SQLite, `markdown_report_builder`, y los orquestadores de cuenta y lote en
modo dry-run. La suite usa mocks, SQLite temporal y filesystem temporal, sin
depender de Telegram real ni de rutas de produccion.

### Pruebas ejecutadas

* `pytest`

## v1.20.0 - Tarea 20 - Modo dry-run

Fecha: 2026-06-15

### Creado

* Tests de dry-run en `tests/test_account_orchestrator.py`, `tests/test_batch_orchestrator.py` y `tests/test_package_smoke.py`.

### Modificado

* `src/ig_orchestrator/orchestration/account_orchestrator.py` para simular el procesamiento de una cuenta sin invocar Telegram, sin mover archivos y sin crear carpetas por defecto.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` para simular el procesamiento de un lote y crear un run/resumen claro de dry-run.
* `src/ig_orchestrator/main.py` para aceptar `--input ... --dry-run`, inicializar SQLite, importar el JSON y procesar el lote en modo simulacion.
* `src/ig_orchestrator/orchestration/__init__.py`, `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para exponer la configuracion de dry-run y actualizar la version a `1.20.0`.

### Resumen

El flujo principal puede ejecutarse como `python -m ig_orchestrator --input config\batch.example.json --dry-run`.
El modo dry-run valida settings, rutas, JSON e importacion a SQLite, crea runs
simulados con resumen explicito y lista lo que habria procesado sin enviar
mensajes a Telegram, sin mover archivos y sin crear la estructura de carpetas
real por defecto.

### Pruebas ejecutadas

* `python -m pytest tests\test_account_orchestrator.py tests\test_batch_orchestrator.py tests\test_package_smoke.py -q`
* `python -m compileall -q src`
* `python -m pytest`

## v1.19.0 - Tarea 19 - Logs

Fecha: 2026-06-15

### Creado

* `src/ig_orchestrator/logging_config.py` con configuracion de `logs/app.log`, logs por ejecucion/cuenta en `logs/YYYYMMDD_HHMMSS/username.log`, contexto de ejecucion y redaccion basica de secretos.
* `tests/test_logging_config.py` con pruebas de escritura de logs globales, logs por cuenta/run y redaccion de valores sensibles.

### Modificado

* `src/ig_orchestrator/orchestration/account_orchestrator.py` para registrar inicio/cierre de cuenta, carpetas, URLs procesadas, decisiones de reintento y fallos de infraestructura.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` para registrar inicio/cierre de lote y cuentas procesadas.
* `src/ig_orchestrator/orchestration/url_job_processor.py` para registrar procesamiento de URL, correcciones de tipo, movimiento de archivos y errores de movimiento.
* `src/ig_orchestrator/telegram/bot_conversation_service.py` para registrar mensaje enviado al bot, respuesta del bot, errores clasificados y archivos detectados.
* `src/ig_orchestrator/reports/markdown_report_builder.py` para registrar el reporte Markdown generado.
* `src/ig_orchestrator/__init__.py`, `pyproject.toml` y `tests/test_package_smoke.py` para actualizar la version a `1.19.0`.

### Resumen

La aplicacion genera un log global en `logs/app.log` para trazas generales,
warnings y errores, y un log por username dentro de la carpeta de ejecucion
`logs/YYYYMMDD_HHMMSS/username.log`. Los eventos principales de lote, cuenta,
URL, Telegram, archivos, errores, reintentos y reportes quedan trazados con
`run_id` y `account_username`, sin registrar claves sensibles ni valores
evidentes de secretos.

### Pruebas ejecutadas

* `python -m pytest tests\test_logging_config.py -q`
* `python -m compileall -q src`
* `python -m pytest`

## Planificacion - CLI opcional y renumeracion de tareas

Fecha: 2026-06-15

### Creado

* `tasks/Tarea_Post01.md` para conservar la CLI completa con Typer como tarea opcional posterior.

### Modificado

* `tasks/Tarea19.md` a `tasks/Tarea23.md` para compactar la secuencia principal tras sacar la CLI.
* `PLAN.md` para reemplazar la CLI obligatoria por ejecucion desde `.bat` llamando al punto de entrada principal con JSON.
* `Agents.md` para ajustar la convencion principal hasta `Tarea 23 => v1.23.0`.
* `requirements.txt` para retirar `typer` y `rich` del camino principal.

### Resumen

La CLI completa deja de bloquear `v1.0.1`. El flujo principal queda orientado a
ejecutar `python -m ig_orchestrator --input config\batch.example.json` desde un
`.bat`, inicializando SQLite, importando el JSON, procesando desde SQLite y
generando reportes.

### Pruebas ejecutadas

* `python -m pytest tests\test_package_smoke.py`

## v1.18.0 - Tarea 18 - Reporte Markdown

Fecha: 2026-06-15

### Creado

* `src/ig_orchestrator/reports/__init__.py` para exponer el builder de reportes.
* `src/ig_orchestrator/reports/markdown_report_builder.py` con construccion del reporte desde SQLite, render Markdown y escritura en disco.
* `tests/test_markdown_report_builder.py` con pruebas del render y de reconstruccion desde SQLite con URLs sin archivos y con multiples archivos.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.18.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.18.0`.
* `tests/test_package_smoke.py` para esperar la version `1.18.0`.
* `CHANGELOG.md` para documentar la tarea.

### Resumen

La aplicacion puede reconstruir un reporte Markdown desde SQLite para un run de
cuenta o batch, incluyendo fecha de ejecucion, tabla con username, tipo, URL,
ficheros, estado y directorio. Las URLs sin descargas muestran `0 files`, las
URLs con varios ficheros los agrupan en la misma celda y la ruta generada queda
persistida en `runs.report_path`.

### Pruebas ejecutadas

* `python -m pytest tests\test_markdown_report_builder.py`
* `python -m pytest`

## v1.17.0 - Tarea 17 - Orquestador de cuenta y lote

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/orchestration/account_orchestrator.py` con el flujo de cuenta: creacion de carpetas, procesamiento de stories generadas antes de URLs manuales, cola FIFO de reintentos y cierre de estado de cuenta/run.
* `src/ig_orchestrator/orchestration/batch_orchestrator.py` con el flujo de batch: carga del lote, procesamiento de cuentas pendientes y resumen final.
* `tests/test_account_orchestrator.py` con pruebas de orden de URLs, reintentos FIFO, cuenta parcial e infraestructura fallida.
* `tests/test_batch_orchestrator.py` con pruebas de procesamiento de cuentas pendientes y estado parcial de lote.

### Modificado

* `src/ig_orchestrator/orchestration/__init__.py` para exponer los orquestadores.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.17.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.17.0`.
* `tests/test_package_smoke.py` para esperar la version `1.17.0`.
* `CHANGELOG.md` para documentar la tarea.

### Resumen

La aplicacion puede coordinar una cuenta completa desde SQLite usando el
procesador de URL existente, crear las carpetas de trabajo, ejecutar primero
stories generadas, luego URLs manuales, enviar fallos temporales a una cola FIFO
de reintentos y marcar la cuenta como `COMPLETED`, `PARTIAL` o `FAILED`. El
orquestador de batch procesa solo cuentas pendientes y consolida el estado final
del lote sin ejecutar renombrador, limpiar duplicados ni mover a destino final.

### Pruebas ejecutadas

* `python -m pytest tests\test_account_orchestrator.py tests\test_batch_orchestrator.py`
* `python -m pytest`
* `python -m ig_orchestrator`

## v1.16.0 - Tarea 16 - Procesador de URL job

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/orchestration/url_job_processor.py` con la capa de aplicacion para procesar un `url_job_id`, delegar en Telegram, mover archivos descargados y persistir el resultado.
* `tests/test_url_job_processor.py` con pruebas usando conversacion falsa, SQLite temporal y movimiento real en carpetas temporales.

### Modificado

* `src/ig_orchestrator/db/download_repository.py` para actualizar metadatos completos de archivos movidos.
* `src/ig_orchestrator/db/url_job_repository.py` para corregir `publication_type` tras inspeccionar archivos descargados.
* `src/ig_orchestrator/orchestration/__init__.py` para exponer el procesador.
* `.vscode/launch.json` para agregar una tercera configuracion `Tests: pytest`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.16.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.16.0`.
* `tests/test_package_smoke.py` para esperar la version `1.16.0`.

### Resumen

La aplicacion puede procesar una URL por id desde SQLite: obtiene el job y la
cuenta, usa el servicio de conversacion con el bot, conserva errores
definitivos o temporales ya clasificados, mueve archivos descargados a la
estructura de cuenta, actualiza los `DownloadFile` con `working_path` y estado,
corrige reels con solo imagenes a `POST` y marca el job como `COMPLETED`.

### Pruebas ejecutadas

* `python -m pytest tests\test_url_job_processor.py tests\test_db_repositories.py`
* `python -m json.tool .vscode\launch.json`
* `python -m pytest`
* `python -m ig_orchestrator`

## v1.15.0 - Tarea 15 - Servicio de conversacion con bot

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/telegram/bot_conversation_service.py` con el flujo de conversacion para procesar una URL contra el bot de Telegram.
* `tests/test_bot_conversation_service.py` con pruebas usando mocks de Telegram y watcher, mas SQLite temporal para persistencia.

### Modificado

* `src/ig_orchestrator/db/url_job_repository.py` para guardar `sent_message_id`.
* `src/ig_orchestrator/telegram/__init__.py` para exponer el servicio de conversacion.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.15.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.15.0`.
* `tests/test_package_smoke.py` para esperar la version `1.15.0`.

### Resumen

La aplicacion puede procesar un `UrlJob` completo contra el bot: marcarlo como
enviado, enviar la URL, guardar el mensaje enviado, leer respuestas del bot,
clasificar errores reintentables y definitivos, activar el watcher si no hay
error, asociar archivos detectados en SQLite y terminar como `DOWNLOADED` o
`RETRY_PENDING` cuando no aparecen archivos. El servicio usa un lock asincrono
por instancia para evitar procesar dos URLs simultaneamente en `v1.0.1`.

### Pruebas ejecutadas

* `python -m pytest tests\test_bot_conversation_service.py`
* `python -m pytest tests\test_db_repositories.py`
* `python -m pytest`
* `python -m ig_orchestrator`

## v1.14.0 - Tarea 14 - Movimiento de archivos por tipo

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/file_mover.py` con movimiento de archivos descargados a carpetas de cuenta segun tipo de publicacion y medio.
* `tests/test_file_mover.py` con pruebas usando carpeta temporal para reels, posts, stories, highlights, sufijos seguros y reclasificacion de reels con solo imagenes.

### Modificado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer el movimiento de archivos y la resolucion de tipo final.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.14.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.14.0`.
* `tests/test_package_smoke.py` para esperar la version `1.14.0`.

### Resumen

La aplicacion puede mover archivos descargados a la estructura temporal de la
cuenta: reels a `reels`, stories a `story`, highlights a `highlights` y posts a
la raiz del usuario. El movimiento devuelve modelos `DownloadFile` actualizados
con `working_path`, estado clasificable para SQLite y tamano final. Si el
destino ya existe, se conserva el archivo previo y se usa un sufijo numerico
seguro. Los reels que descargan solo imagenes se resuelven como posts.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.13.0 - Tarea 13 - Clasificador de archivos

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/file_classifier.py` con clasificacion de archivos descargados por extension.
* `tests/test_file_classifier.py` con pruebas unitarias para imagenes, videos, extensiones en mayusculas y tipos desconocidos.

### Modificado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer el clasificador y los conjuntos de extensiones.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.13.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.13.0`.
* `tests/test_package_smoke.py` para esperar la version `1.13.0`.

### Resumen

La aplicacion puede clasificar archivos descargados como `IMAGE`, `VIDEO` o
`UNKNOWN` a partir de su extension, sin distinguir mayusculas/minusculas y sin
tocar el sistema de archivos real.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.12.0 - Tarea 12 - Watcher de descargas

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/file_watcher.py` con un watcher pasivo para detectar archivos nuevos o modificados tras un instante de inicio, ignorar temporales y directorios, y esperar estabilidad de tamano.
* `tests/test_file_watcher.py` con pruebas usando carpeta temporal para archivos nuevos, temporales, directorios, timeout y estabilizacion de tamano.

### Modificado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer `watch_downloaded_files`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.12.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.12.0`.
* `tests/test_package_smoke.py` para esperar la version `1.12.0`.

### Resumen

La aplicacion puede observar una carpeta de descargas y devolver solo archivos
creados o modificados despues de `start_time`, sin moverlos ni depender de
Telegram real. El watcher espera a que no haya cambios durante
`stable_seconds`, filtra extensiones temporales comunes y devuelve una lista de
`Path` ordenada.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.11.0 - Tarea 11 - Politica de reintentos por ronda

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/orchestration/__init__.py` para exponer la politica de reintentos.
* `src/ig_orchestrator/orchestration/retry_policy.py` con decisiones explicitas de retry, fallo final y no reintento, calculo de backoff y cola FIFO.
* `tests/test_retry_policy.py` con pruebas unitarias de backoff, errores no reintentables, max retries, cola FIFO y validaciones.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.11.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.11.0`.
* `tests/test_package_smoke.py` para esperar la version `1.11.0`.

### Resumen

La aplicacion puede calcular la siguiente accion para una URL fallida sin dormir
ni tocar Telegram: reintentar con backoff exponencial limitado, marcar fallo
final al agotar reintentos o por error no reintentable, y mantener una cola FIFO
para reintentos al final de la pasada principal.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.10.0 - Tarea 10 - Parser de respuestas del bot

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/telegram/bot_response_parser.py` con clasificacion de respuestas del bot, errores reintentables y no reintentables.
* `tests/test_bot_response_parser.py` con pruebas unitarias para cada error conocido, respuestas OK y respuestas vacias.

### Modificado

* `src/ig_orchestrator/telegram/__init__.py` para exponer el parser y sus enums.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.10.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.10.0`.
* `tests/test_package_smoke.py` para esperar la version `1.10.0`.

### Resumen

La aplicacion puede clasificar textos de respuesta del bot sin depender de
Telegram real. Los errores conocidos se detectan sin distinguir
mayusculas/minusculas, el mensaje original se conserva como `last_error` y el
tipo de error queda disponible en `last_error_type` para la futura politica de
reintentos y persistencia.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.9.0 - Tarea 9 - Cliente Telegram con Telethon

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/telegram/__init__.py` para exponer el wrapper de Telegram.
* `src/ig_orchestrator/telegram/telegram_client.py` con configuracion segura, arranque de Telethon, envio al bot y lectura de mensajes.
* `tests/test_telegram_client.py` con pruebas unitarias basadas en mocks sin conexion real a Telegram.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.9.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.9.0` y declarar Telethon como dependencia runtime.
* `tests/test_package_smoke.py` para esperar la version `1.9.0`.

### Resumen

La aplicacion cuenta con un wrapper asincrono para Telethon que crea el cliente
con la sesion configurada, reutiliza la instancia durante la ejecucion, permite
enviar mensajes al bot configurado, leer mensajes recientes y filtrar mensajes
nuevos posteriores a un timestamp. La configuracion oculta `api_hash` en su
representacion y los tests no dependen de Telegram real.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.8.0 - Tarea 8 - Servicio de carpetas

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/filesystem/__init__.py` para exponer el servicio de carpetas.
* `src/ig_orchestrator/filesystem/folder_service.py` con `ensure_account_folders` y la estructura `AccountFolderPaths`.
* `tests/test_folder_service.py` con pruebas unitarias usando carpeta temporal.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.8.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.8.0`.
* `tests/test_package_smoke.py` para esperar la version `1.8.0`.

### Resumen

La aplicacion puede crear de forma idempotente la estructura temporal de una
cuenta dentro de la carpeta de trabajo: raiz del usuario, `story`, `reels` y
`highlights`. Si las carpetas ya existen, se conservan sus contenidos y solo se
crean las subcarpetas faltantes.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.7.0 - Tarea 7 - Clasificador de URLs

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/input/url_classifier.py` con clasificacion inicial de URLs de Instagram y error explicito para entradas invalidas.
* `tests/test_url_classifier.py` con pruebas unitarias para posts, reels, stories, highlights, URLs desconocidas de Instagram y URLs no Instagram.

### Modificado

* `src/ig_orchestrator/input/batch_importer.py` para usar el clasificador dedicado.
* `src/ig_orchestrator/input/__init__.py` para exponer `UrlClassifierError` y `classify_instagram_url`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.7.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.7.0`.
* `tests/test_package_smoke.py` para esperar la version `1.7.0`.

### Resumen

La clasificacion inicial de URLs queda aislada en un modulo testeable. Las URLs
de highlights, stories, reels y posts se clasifican segun las reglas de la
tarea, los posts sin `img_index` siguen entrando inicialmente como `REEL`, las
rutas desconocidas de Instagram se mantienen como `UNKNOWN` y las URLs fuera
del dominio de Instagram fallan con `UrlClassifierError`.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.6.0 - Tarea 6 - Importador JSON a SQLite

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/input/batch_importer.py` con importacion de JSON validado a `input_batches`, `accounts` y `url_jobs`.
* `tests/test_batch_importer.py` con pruebas de importacion, stories generadas, clasificacion inicial e idempotencia.

### Modificado

* `src/ig_orchestrator/input/__init__.py` para exponer el importador.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.6.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.6.0`.
* `tests/test_package_smoke.py` para esperar la version `1.6.0`.

### Resumen

La aplicacion puede importar un lote parseado o un JSON directamente a SQLite,
reutilizando el batch y las cuentas existentes al reimportar el mismo lote para
evitar duplicados razonables. Si `download_stories` es verdadero, se genera la
URL de stories y se guarda como `url_job` con `source = GENERATED_STORY`. Las
URLs manuales se guardan con `source = INPUT_URL` y clasificacion inicial de
stories, highlights, reels y posts. Cuando el importador recibe `Settings`,
persiste configuracion operativa no sensible en `app_config`.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.5.0 - Tarea 5 - Parser de JSON por lotes

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/input/__init__.py` para exponer el parser de lotes.
* `src/ig_orchestrator/input/batch_json_parser.py` con `parse_batch_json`, DTOs de lote parseado y errores de validacion claros.
* `tests/test_batch_json_parser.py` con pruebas unitarias del contrato de entrada JSON.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.5.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.5.0`.
* `tests/test_package_smoke.py` para esperar la version `1.5.0`.

### Resumen

La aplicacion puede leer un JSON de lotes, validar campos obligatorios,
heredar defaults por cuenta, limpiar espacios, deduplicar URLs dentro de la
misma cuenta, validar fechas `YYYY-MM-DD` y restringir URLs al dominio de
Instagram. Los errores incluyen contexto de cuenta y campo problematico.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `parse_batch_json("config/batch.example.json")`

## v1.4.0 - Tarea 4 - SQLite schema, migraciones y repositorios

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/db/schema.sql` con las tablas `app_config`, `input_batches`, `accounts`, `runs`, `url_jobs` y `download_files`.
* `src/ig_orchestrator/db/connection.py` para abrir conexiones SQLite con `row_factory` y claves foraneas activas.
* `src/ig_orchestrator/db/migrations.py` con inicializacion idempotente de la base de datos.
* `src/ig_orchestrator/db/config_repository.py` para persistir configuracion operativa.
* `src/ig_orchestrator/db/batch_repository.py` para crear, consultar y actualizar lotes.
* `src/ig_orchestrator/db/account_repository.py` para crear, consultar y actualizar cuentas.
* `src/ig_orchestrator/db/url_job_repository.py` para crear, consultar y actualizar trabajos de URL.
* `src/ig_orchestrator/db/download_repository.py` para crear, consultar y actualizar archivos descargados.
* `src/ig_orchestrator/db/run_repository.py` para crear y actualizar ejecuciones.
* `tests/test_db_repositories.py` con pruebas de integracion usando SQLite temporal.

### Modificado

* `src/ig_orchestrator/db/__init__.py` para exponer conexion, migraciones y repositorios.
* `src/ig_orchestrator/main.py` con un comando minimo `init-db`.
* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.4.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.4.0`.
* `tests/test_package_smoke.py` para esperar la version `1.4.0`.

### Resumen

La aplicacion puede inicializar SQLite sin borrar datos existentes, crear las
tablas de persistencia definidas en el plan y operar sobre batches, cuentas,
URL jobs, archivos descargados, runs y configuracion mediante repositorios
testeables.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `python -m ig_orchestrator init-db --db-path <sqlite-temporal>`

## v1.3.0 - Tarea 3 - Modelos de dominio

Fecha: 2026-06-14

### Creado

* `src/ig_orchestrator/models/account.py` con `Account` y `AccountStatus`.
* `src/ig_orchestrator/models/app_config.py` con `AppConfig` y `ConfigValueType`.
* `src/ig_orchestrator/models/input_batch.py` con `InputBatch` y `InputBatchStatus`.
* `src/ig_orchestrator/models/url_job.py` con `UrlJob`, `PublicationType`, `UrlSource` y `UrlJobStatus`.
* `src/ig_orchestrator/models/download_file.py` con `DownloadFile`, `MediaType` y `DownloadFileStatus`.
* `src/ig_orchestrator/models/run_summary.py` con `RunSummary` y `RunStatus`.
* `src/ig_orchestrator/models/__init__.py` para exponer los modelos de dominio.
* `tests/test_models.py` con pruebas unitarias de creacion y validaciones minimas.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.3.0`.
* `pyproject.toml` para actualizar la version del paquete a `1.3.0`.
* `tests/test_package_smoke.py` para esperar la version `1.3.0`.

### Resumen

La aplicacion cuenta con modelos de dominio ligeros basados en `dataclasses`,
enums para estados y tipos definidos en el plan, y validaciones minimas para
identificadores, textos obligatorios, fechas, rutas, contadores y metadatos de
archivos.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.2.0 - Tarea 2 - Settings y configuracion

Fecha: 2026-06-13

### Creado

* `src/ig_orchestrator/settings.py` con `Settings`, `SettingsError` y `load_settings`.
* `tests/test_settings.py` con pruebas unitarias de carga, variables faltantes y variables reservadas opcionales.

### Modificado

* `src/ig_orchestrator/__init__.py` para actualizar la version del paquete a `1.2.0`.
* `pyproject.toml` para actualizar la version y declarar dependencias runtime de configuracion.
* `tests/test_package_smoke.py` para esperar la version `1.2.0`.

### Resumen

La aplicacion puede cargar configuracion desde `.env` y variables de entorno,
validando campos obligatorios con mensajes claros, convirtiendo rutas a
`pathlib.Path` y manteniendo la configuracion futura de renombrado/movimiento
final como opcional.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`

## v1.1.0 - Tarea 1 - Estructura base del proyecto

Fecha: 2026-06-13

### Creado

* `pyproject.toml` para empaquetar el proyecto con layout `src`.
* `.env.example` con las variables previstas para la serie `v1.x`.
* `src/ig_orchestrator/__init__.py`.
* `src/ig_orchestrator/__main__.py`.
* `src/ig_orchestrator/main.py`.
* `tests/test_package_smoke.py`.
* `data/.gitkeep`, `logs/.gitkeep` y `reports/.gitkeep`.
* `.vscode/launch.json` con configuraciones para depurar `ig_orchestrator` y ejecutar `pytest`.

### Modificado

* `README.md` con uso inicial.
* `requirements.txt` con dependencias base documentadas en el plan.
* `.gitignore` para proteger `.env`, sesiones de Telethon, SQLite y logs sin bloquear carpetas base.
* `tasks/Tarea1.md` para incluir `launch.json` en el alcance de la tarea.

### Resumen

El paquete se puede importar y ejecutar con `python -m ig_orchestrator`, mostrando
una salida minima sin implementar todavia logica de Telegram ni negocio. Tambien
queda disponible una configuracion compartida de VS Code para ejecutar y depurar
la aplicacion o los tests.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `python -m json.tool .vscode\launch.json`

## Planificacion - Versionado por tarea

Fecha: 2026-06-13

### Modificado

* `tasks/Tarea1.md` a `tasks/Tarea24.md`: cada tarea ahora apunta a su minor propio, de `v1.1.0` a `v1.24.0`.
* `PLAN.md`: agregada convencion de versionado minor por tarea y patch por correccion.
* `Agents.md`: agregada instruccion para responder con comandos sugeridos de commit y tag.
* `.github/copilot-instructions.md`: agregada convencion de versionado por tarea.

## v1.0.1 - Planificacion inicial

Fecha: 2026-06-13

### Creado

* `Agents.md` con instrucciones base para IA.
* `.github/copilot-instructions.md` con instrucciones resumidas para Copilot.
* `tasks/Tarea1.md` a `tasks/Tarea24.md`.
* `config/batch.example.json` como ejemplo de entrada por lotes.
* `config/app.example.json` como ejemplo de configuracion operativa persistible en SQLite.

### Modificado

* `PLAN.md` reestructurado para `v1.0.1`.

### Notas

`v1.0.1` queda centrada en descarga, SQLite, reintentos y reportes. Renombrado, duplicados del renombrador y movimiento final quedan documentados como backlog posterior.
