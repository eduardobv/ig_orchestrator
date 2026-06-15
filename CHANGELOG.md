# Changelog

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
