# Changelog

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
