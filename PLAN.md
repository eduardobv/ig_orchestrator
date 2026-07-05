# Instagram Manual Download Orchestrator

## 1. Descripcion general

Este proyecto automatiza un proceso manual de descarga, clasificacion y organizacion de publicaciones de Instagram descargadas mediante un bot de Telegram.

La primera linea de trabajo sera la version `v1.0.1`. Esta version se centra exclusivamente en comprobar y estabilizar el sistema de descarga, trazabilidad, reintentos, persistencia y reportes. La integracion con el script actual de renombrado, la deteccion de duplicados del renombrador y el movimiento final se mantienen documentados, pero quedan fuera de `v1.0.1`.

El sistema parte de un input manual estructurado, inicialmente en JSON, con soporte para lotes:

```text
username
url_list
start_now_date
download_stories
```

El objetivo es que este contrato de entrada sea facil de reutilizar mas adelante desde una interfaz grafica web o standalone. La UI futura no deberia ejecutar logica distinta: solo deberia escribir configuracion y trabajos en SQLite, y el orquestador deberia leer desde la base de datos.

El sistema debe estar disenado de forma modular, para que cada tarea pueda implementarse, probarse y evolucionarse de manera independiente.

---

## 2. Objetivo de la version v1.0.1

La version `v1.0.1` no automatiza la navegacion por Instagram ni la extraccion automatica de URLs desde el navegador.

El usuario prepara un archivo JSON de entrada. La aplicacion:

1. Inicializa SQLite si no existe.
2. Respeta la informacion existente si la base de datos ya existe.
3. Importa el JSON a la base de datos.
4. Guarda configuracion y trabajos en SQLite.
5. Ejecuta el orquestador leyendo la configuracion desde SQLite, no desde el JSON.
6. Genera automaticamente la URL de stories si `download_stories = true`.
7. Procesa primero stories y luego la lista de URLs.
8. Envia cada URL al bot de Telegram.
9. Espera respuesta y archivos descargados.
10. Guarda archivos, estados, errores y motivos de fallo.
11. Reintenta fallos temporales al final de la ronda, no inmediatamente.
12. Genera un reporte Markdown por ejecucion.

Fuera de alcance en `v1.0.1`:

1. Integracion con el script de renombrado.
2. Deteccion de duplicados generados por el renombrador.
3. Movimiento final a `G:\4K Stogram`.

Estos puntos se conservan en el plan como backlog futuro.

---

## 3. Principios de diseno

### 3.1 Modularidad

Cada modulo debe tener una responsabilidad clara.

No debe existir un script gigante que haga todo.

Cada componente debe poder probarse de manera independiente.

### 3.2 Persistencia

Todo el estado operativo debe guardarse en SQLite.

El proceso debe poder interrumpirse y reanudarse.

El JSON de entrada es solo un mecanismo de carga inicial. Tras importarlo, la ejecucion debe cargar cuentas, configuracion, URLs y flags desde SQLite.

### 3.3 Trazabilidad

Cada URL debe tener un estado individual.

El sistema debe saber:

* cuando fue enviada al bot;
* que respuesta recibio;
* si la respuesta fue error definitivo o reintentable;
* cuantos reintentos lleva;
* que archivos se descargaron despues;
* si termino correctamente;
* si fallo definitivamente;
* que directorio recibio los archivos;
* en que reporte aparece.

### 3.4 Seguridad

Las credenciales no deben estar en el codigo.

Los datos sensibles deben ir en `.env`.

El archivo de sesion de Telethon no debe subirse al repositorio.

### 3.5 Compatibilidad Windows

El proyecto esta pensado para Windows 11.

Debe soportar rutas como:

```text
C:\Users\eduba\Downloads\DW\Telegram_Desktop
G:\4K Stogram\00.FAVORITES
```

### 3.6 Preparado para UI futura

La entrada debe modelarse como datos persistidos, no como argumentos sueltos de CLI.

La UI futura deberia poder:

* crear o actualizar una configuracion;
* crear lotes de cuentas;
* marcar `download_stories`;
* anadir URLs;
* lanzar o pausar ejecuciones;
* consultar estados y reportes.

Por eso se recomienda separar:

* capa de importacion JSON;
* capa de repositorios SQLite;
* capa de servicios de aplicacion;
* capa CLI;
* capa futura UI.

---

## 4. Stack tecnico recomendado

### 4.1 Lenguaje

```text
Python 3.11+
```

### 4.2 Librerias principales

```text
telethon
python-dotenv
pydantic
watchdog
loguru
pytest
pytest-asyncio
```

### 4.3 Librerias estandar de Python

```text
sqlite3
pathlib
shutil
datetime
asyncio
json
re
hashlib
uuid
subprocess
```

---

## 5. Estructura de carpetas del proyecto

```text
instagram_manual_orchestrator/
|
|-- README.md
|-- PLAN.md
|-- Agents.md
|-- CHANGELOG.md
|-- pyproject.toml
|-- requirements.txt
|-- .env.example
|-- .gitignore
|
|-- .github/
|   `-- copilot-instructions.md
|
|-- config/
|   |-- app.example.json
|   `-- batch.example.json
|
|-- data/
|   `-- .gitkeep
|
|-- reports/
|   `-- .gitkeep
|
|-- logs/
|   `-- .gitkeep
|
|-- tasks/
|   |-- Tarea1.md
|   |-- Tarea2.md
|   `-- ...
|
|-- scripts/
|   |-- init_db.py
|   |-- import_batch.py
|   |-- run_batch.py
|   |-- run_account.py
|   |-- retry_failed.py
|   `-- inspect_queue.py
|
|-- src/
|   `-- ig_orchestrator/
|       |-- __init__.py
|       |-- __main__.py
|       |-- main.py
|       |-- settings.py
|       |-- constants.py
|       |-- exceptions.py
|       |-- logging_config.py
|       |
|       |-- models/
|       |   |-- __init__.py
|       |   |-- account.py
|       |   |-- app_config.py
|       |   |-- input_batch.py
|       |   |-- url_job.py
|       |   |-- download_file.py
|       |   `-- run_summary.py
|       |
|       |-- db/
|       |   |-- __init__.py
|       |   |-- connection.py
|       |   |-- schema.sql
|       |   |-- migrations.py
|       |   |-- config_repository.py
|       |   |-- batch_repository.py
|       |   |-- account_repository.py
|       |   |-- url_job_repository.py
|       |   |-- download_repository.py
|       |   `-- run_repository.py
|       |
|       |-- input/
|       |   |-- __init__.py
|       |   |-- batch_json_parser.py
|       |   |-- batch_importer.py
|       |   `-- url_classifier.py
|       |
|       |-- filesystem/
|       |   |-- __init__.py
|       |   |-- folder_service.py
|       |   |-- file_watcher.py
|       |   |-- file_classifier.py
|       |   `-- file_mover.py
|       |
|       |-- telegram/
|       |   |-- __init__.py
|       |   |-- telegram_client.py
|       |   |-- bot_conversation_service.py
|       |   |-- bot_response_parser.py
|       |   `-- telegram_download_tracker.py
|       |
|       |-- reports/
|       |   |-- __init__.py
|       |   `-- markdown_report_builder.py
|       |
|       |-- orchestration/
|       |   |-- __init__.py
|       |   |-- account_orchestrator.py
|       |   |-- batch_orchestrator.py
|       |   |-- url_job_processor.py
|       |   |-- retry_policy.py
|       |   `-- run_summary_builder.py
|       |
|       `-- cli/
|           |-- __init__.py
|           `-- commands.py
|
`-- tests/
    |-- unit/
    `-- integration/
```

Los modulos `rename/`, `duplicate_cleaner.py` y movimiento final quedan reservados para versiones posteriores a `v1.0.1`.

---

## 6. Archivo `.env.example`

```env
# Telegram API credentials
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# Nombre del archivo de sesion local de Telethon.
# No subir este archivo al repositorio.
TELETHON_SESSION_NAME=telegram_user_session

# Username o identificador del bot de Telegram usado para descargar publicaciones.
TELEGRAM_DOWNLOAD_BOT_USERNAME=@example_bot

# Carpetas locales
TELEGRAM_DESKTOP_DOWNLOAD_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop
WORKING_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop
REPORTS_FOLDER=reports

# Base de datos SQLite
SQLITE_DB_PATH=data\orchestrator.db

# Reintentos
MAX_RETRIES=5
RETRY_BASE_SECONDS=90
RETRY_MAX_SECONDS=900

# Tiempo de espera por descarga
DOWNLOAD_WAIT_TIMEOUT_SECONDS=300
DOWNLOAD_STABLE_SECONDS=10
```

Variables reservadas para versiones posteriores:

```env
FINAL_BASE_FOLDER=G:\4K Stogram\00.FAVORITES
MANUAL_RENAME_BAT_PATH=C:\path\to\ManualRenameFiles.bat
MANUAL_RENAME_CONFIG_PATH=C:\path\to\config.json
```

---

## 7. `requirements.txt`

Actualizar este archivo en caso de que ya exista.

```txt
telethon>=1.34.0
python-dotenv>=1.0.0
pydantic>=2.0.0
watchdog>=4.0.0
loguru>=0.7.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 8. Input JSON por lotes

### 8.1 Objetivo

El input inicial sera un archivo JSON. Debe ser suficientemente explicito para usarse desde CLI ahora y desde UI en una version posterior.

La importacion del JSON debe validar datos, normalizar URLs y guardar todo en SQLite.

La ejecucion posterior debe leer desde SQLite.

### 8.2 Estructura recomendada

```json
{
  "schema_version": "1.0",
  "batch_name": "descargas_junio_2026",
  "defaults": {
    "download_stories": false,
    "start_now_date": "2026-06-04"
  },
  "accounts": [
    {
      "username": "example_user",
      "start_now_date": "2026-06-04",
      "download_stories": true,
      "urls": [
        "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
        "https://www.instagram.com/reel/ABC123xyz/",
        "https://www.instagram.com/stories/highlights/17851330941375169/"
      ]
    },
    {
      "username": "another_user",
      "download_stories": false,
      "urls": [
        "https://www.instagram.com/p/XYZ789abc/"
      ]
    }
  ]
}
```

### 8.3 Reglas

* `username` es obligatorio por cuenta.
* `start_now_date` es obligatorio, pero puede heredarse de `defaults`.
* `download_stories` es booleano y puede heredarse de `defaults`.
* `urls` puede contener posts, reels, stories e highlights.
* La lista de URLs puede estar vacia si `download_stories = true`.
* No duplicar URLs dentro de la misma cuenta.
* Validar fecha en formato `YYYY-MM-DD`.
* Validar dominio de Instagram.
* La importacion debe ser idempotente tanto como sea razonable: no duplicar cuentas/URLs iguales dentro del mismo batch si se reimporta.
* Antes de insertar las cuentas, ordenarlas en memoria: primero las que tienen
  `download_stories = true` y ninguna URL; despues por cantidad ascendente de
  URLs procesables, manteniendo el orden original cuando haya empate.

### 8.4 Relacion con UI futura

La UI futura deberia escribir los mismos datos en SQLite:

* batch;
* cuenta;
* flag `download_stories`;
* URLs;
* configuracion de ejecucion.

El JSON es una forma temporal de alimentar la misma estructura de datos.

---

## 9. Base de datos SQLite

La primera vez que se ejecuta la aplicacion debe inicializar SQLite.

Si la base de datos ya existe, se debe respetar la informacion existente y aplicar migraciones seguras.

### 9.1 Tabla `app_config`

Configuracion operativa persistida en base de datos.

```sql
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Ejemplos de claves:

```text
telegram_desktop_download_folder
working_folder
reports_folder
max_retries
retry_base_seconds
retry_max_seconds
download_wait_timeout_seconds
download_stable_seconds
```

La configuracion sensible sigue en `.env`.

### 9.2 Tabla `input_batches`

Representa un lote importado desde JSON o creado en una UI futura.

```sql
CREATE TABLE IF NOT EXISTS input_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_file TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Estados posibles:

```text
IMPORTED
PROCESSING
COMPLETED
PARTIAL
FAILED
```

### 9.3 Tabla `accounts`

Representa una cuenta de Instagram que se va a procesar.

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    username TEXT NOT NULL,
    start_now_date TEXT NOT NULL,
    download_stories INTEGER NOT NULL DEFAULT 0,
    generated_story_url TEXT,
    working_folder TEXT,
    final_destination_folder TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES input_batches(id)
);
```

Estados posibles:

```text
PENDING
PROCESSING
COMPLETED
FAILED
PARTIAL
```

### 9.4 Tabla `url_jobs`

Representa cada URL individual a descargar.

```sql
CREATE TABLE IF NOT EXISTS url_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    run_id INTEGER,
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
    updated_at TEXT NOT NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
```

Valores posibles de `publication_type`:

```text
POST
REEL
STORY
HIGHLIGHTS
UNKNOWN
```

Valores posibles de `source`:

```text
GENERATED_STORY
INPUT_URL
```

Valores posibles de `status`:

```text
PENDING
SENT_TO_BOT
WAITING_DOWNLOAD
DOWNLOADED
RETRY_PENDING
FAILED_TEMPORARY
FAILED_FINAL
CLASSIFIED
COMPLETED
```

Los estados `RENAMED` y `DUPLICATED` quedan reservados para versiones posteriores.

### 9.5 Tabla `download_files`

Representa cada archivo detectado despues de enviar una URL al bot.

```sql
CREATE TABLE IF NOT EXISTS download_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_job_id INTEGER NOT NULL,
    original_path TEXT NOT NULL,
    working_path TEXT,
    final_path TEXT,
    media_type TEXT NOT NULL,
    file_extension TEXT NOT NULL,
    file_size INTEGER,
    sha256 TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(url_job_id) REFERENCES url_jobs(id)
);
```

Valores posibles de `media_type`:

```text
IMAGE
VIDEO
UNKNOWN
```

Valores posibles de `status` en `v1.0.1`:

```text
DETECTED
MOVED_TO_WORKING_FOLDER
CLASSIFIED_AS_REEL
CLASSIFIED_AS_POST
CLASSIFIED_AS_STORY
CLASSIFIED_AS_HIGHLIGHTS
FINALIZED
```

Estados reservados para versiones posteriores:

```text
RENAMED
DUPLICATED
DELETED
```

### 9.6 Tabla `runs`

Representa una ejecucion.

```sql
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    account_id INTEGER,
    status TEXT NOT NULL,
    total_urls INTEGER NOT NULL DEFAULT 0,
    completed_urls INTEGER NOT NULL DEFAULT 0,
    failed_urls INTEGER NOT NULL DEFAULT 0,
    downloaded_files INTEGER NOT NULL DEFAULT 0,
    report_path TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT,
    FOREIGN KEY(batch_id) REFERENCES input_batches(id),
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);
```

`account_id` puede ser `NULL` si el run representa un lote completo.

---

## 10. Clasificacion de URLs de Instagram

### 10.1 Reglas iniciales

Si la URL tiene este formato:

```text
https://www.instagram.com/stories/{username}/
```

Clasificar como:

```text
STORY
```

Si la URL tiene este formato:

```text
https://www.instagram.com/stories/highlights/17851330941375169/
```

Clasificar como:

```text
HIGHLIGHTS
```

Si la URL contiene `/reel/`, clasificar como:

```text
REEL
```

Si la URL contiene `/p/` y `img_index`, clasificar como:

```text
POST
```

Si la URL contiene `/p/` y no contiene `img_index`, clasificar inicialmente como:

```text
REEL
```

Esta clasificacion inicial puede corregirse despues segun el tipo de archivo descargado.

### 10.2 URL generada para stories

Si `download_stories = true`, el sistema debe generar automaticamente:

```text
https://www.instagram.com/stories/{username}/
```

Esa URL debe insertarse como un `url_job` de tipo `STORY` con `source = GENERATED_STORY`.

### 10.3 URLs de stories/highlights en la lista manual

La lista `urls` tambien puede incluir URLs de stories o highlights, independientemente de `download_stories`.

Ejemplos validos:

```text
https://www.instagram.com/stories/user_name/
https://www.instagram.com/stories/highlights/17851330941375169/
```

### 10.4 Correccion posterior segun archivo descargado

Si una URL fue clasificada inicialmente como `REEL`, pero el bot descarga unicamente archivos `.jpg`, `.jpeg`, `.png` o `.webp`, entonces debe reclasificarse como:

```text
POST
```

Si descarga `.mp4`, `.mov` o similar, se mantiene como:

```text
REEL
```

Si descarga mezcla de videos e imagenes, se mantiene clasificacion por archivo:

```text
POST para imagenes
REEL para videos
```

---

## 11. Estructura temporal por cuenta

Dado:

```text
username = example_user
```

El sistema debe crear:

```text
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\story\
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\reels\
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\highlights\
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\_errors\
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\_logs\
```

Reservado para versiones posteriores:

```text
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user\_duplicated\
```

Reglas en `v1.0.1`:

* Los videos de reels deben ir a `reels`.
* Las stories deben ir a `story`.
* Las highlights deben ir a `highlights`.
* Las fotos de posts deben quedar en la carpeta raiz del usuario.
* Los errores deben registrarse en SQLite y, si aplica, en `_errors`.

---

## 12. Integracion con Telegram mediante Telethon

### 12.1 Por que Telethon

El bot de Telegram usado para descargar publicaciones es de pago y responde a la cuenta personal del usuario.

Por tanto, el sistema debe conectarse a Telegram como usuario real, no como bot propio.

Telethon permite crear un cliente de Telegram usando:

```text
api_id
api_hash
phone number
session file
```

En la primera ejecucion, Telethon pedira iniciar sesion.

Despues se guardara una sesion local, por ejemplo:

```text
telegram_user_session.session
```

Ese archivo permite reutilizar la sesion sin introducir el codigo cada vez.

### 12.2 Importante

No subir nunca al repositorio:

```text
*.session
*.session-journal
.env
```

Anadir a `.gitignore`:

```gitignore
.env
*.session
*.session-journal
data/*.db
logs/*.log
```

### 12.3 Flujo esperado con el bot

Para cada URL:

1. Enviar URL al bot.
2. Guardar `sent_message_id`.
3. Esperar respuesta del bot.
4. Detectar si la respuesta contiene error.
5. Si el error es definitivo, no reintentar.
6. Si no hay error definitivo, esperar archivos nuevos en la carpeta de Telegram Desktop.
7. Asociar los archivos nuevos con esa URL.
8. Marcar la URL como descargada o fallida.

---

## 13. Errores conocidos del bot de Telegram

El bot puede responder con errores.

### 13.1 Errores reintentables

Estos errores deben considerarse temporales:

```text
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable
```

Aunque algunos puedan parecer definitivos, en la practica se deben reintentar varias veces porque el bot o el servicio remoto puede fallar temporalmente.

### 13.2 Errores no reintentables

Estos errores deben considerarse definitivos. No se deben reintentar:

```text
We're sorry, we couldn't find that.
Stories for user_name not found
We can't get stories from a private account (instagram limit)
```

El mensaje original debe guardarse en SQLite en `last_error`, y una clasificacion del error debe guardarse en `last_error_type`.

### 13.3 Politica de reintentos por ronda

Configuracion inicial:

```text
MAX_RETRIES = 5
RETRY_BASE_SECONDS = 90
RETRY_MAX_SECONDS = 900
```

La version `v1.0.1` debe evitar reintentar una URL justo despues de fallar si todavia quedan URLs nuevas en la cuenta.

Orden:

1. Descargar stories si `download_stories = true`.
2. Descargar una a una la lista de URLs.
3. Si una URL falla por motivo reintentable, no reintentar en ese momento.
4. Guardarla como `RETRY_PENDING`.
5. Continuar con la siguiente URL.
6. Al terminar la primera pasada, procesar la cola de fallos.
7. La cola de fallos se procesa en orden FIFO.
8. Si una URL vuelve a fallar, se vuelve a poner al final de la cola si aun tiene reintentos disponibles.
9. Si una URL funciona, queda completada y sale de la cola.
10. Tras `MAX_RETRIES`, marcar como `FAILED_FINAL`.

Ejemplo:

```text
URLs: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
Fallan en primera pasada: 2 y 6

Despues de la URL 10:
- reintentar 2
- si falla, pasa al final
- reintentar 6
- si va bien, sale de la cola
- reintentar 2
- repetir hasta completar o agotar reintentos
```

La espera entre reintentos se calcula con backoff:

```text
retry_1 = 90 segundos
retry_2 = 180 segundos
retry_3 = 360 segundos
retry_4 = 720 segundos
retry_5 = 900 segundos
```

La politica solo calcula decisiones. El orquestador decide cuando dormir o esperar.

---

## 14. Watcher de carpeta Telegram Desktop

### 14.1 Objetivo

Detectar que archivos aparecen despues de enviar una URL al bot.

### 14.2 Regla de asociacion

Antes de enviar una URL:

```text
download_start_time = now()
```

Despues de enviar la URL:

1. Observar la carpeta `Telegram_Desktop`.
2. Detectar archivos creados o modificados despues de `download_start_time`.
3. Esperar hasta que no aparezcan archivos nuevos durante `DOWNLOAD_STABLE_SECONDS`.
4. Asociar esos archivos al `url_job`.

### 14.3 Precauciones

No mover un archivo mientras todavia se esta descargando.

Un archivo se considera estable cuando:

* existe;
* su tamano no cambia durante varios segundos;
* no tiene extension temporal;
* no esta bloqueado por otro proceso.

---

## 15. Clasificacion y movimiento de archivos

### 15.1 Extensiones de imagen

```text
.jpg
.jpeg
.png
.webp
```

Clasificar como:

```text
IMAGE
```

### 15.2 Extensiones de video

```text
.mp4
.mov
.mkv
.webm
```

Clasificar como:

```text
VIDEO
```

### 15.3 Reglas de movimiento en v1.0.1

Si `publication_type = REEL` y archivo es video:

```text
example_user\reels\
```

Si `publication_type = POST` y archivo es imagen:

```text
example_user\
```

Si una URL inicialmente `REEL` descarga solo imagenes:

```text
corregir publication_type a POST
mover imagenes a example_user\
```

Si son stories:

```text
example_user\story\
```

Si son highlights:

```text
example_user\highlights\
```

Debe evitarse sobrescritura accidental. Si el destino existe, anadir sufijo seguro.

---

## 16. Reporte Markdown por ejecucion

Tras cada ejecucion se debe generar un reporte Markdown.

Ruta recomendada:

```text
reports/run_YYYYMMDD_HHMMSS.md
```

Tambien puede guardarse una copia o enlace en:

```text
example_user\_logs\
```

El reporte debe incluir:

```text
Fecha y hora de ejecucion
```

Y una tabla con estas columnas:

```text
Username
Tipo
Urls
Fichero
Estado
Directory
```

Reglas:

* `Username`: username del usuario.
* `Tipo`: `Story`, `Post`, `Reel`, `Highlights`.
* `Urls`: URL procesada. En stories generadas, usar la URL generada.
* `Fichero`: lista de ficheros descargados para esa URL. Puede tener 0 o N elementos.
* `Estado`: estado final de la URL.
* `Directory`: directorio donde se descargo o movio el fichero.

Cuando una URL tenga varios ficheros, la celda `Fichero` puede contener una lista HTML/Markdown compacta:

```text
<br>- file1.jpg<br>- file2.mp4
```

Si no se descargo nada:

```text
0 files
```

El reporte debe poder reconstruirse desde SQLite.

---

## 17. Punto de entrada esperado para v1.0.1

La version `v1.0.1` no necesita exponer una CLI completa con Typer.

El flujo previsto es ejecutar el punto de entrada principal desde un `.bat`, leyendo un JSON de entrada. Ese punto de entrada debe:

1. Inicializar SQLite si hace falta.
2. Importar el JSON a SQLite.
3. Leer configuracion y trabajos desde SQLite.
4. Procesar el lote.
5. Aplicar reintentos segun la politica.
6. Generar reporte Markdown.

Ejemplo de `.bat`:

```bat
@echo off
python -m ig_orchestrator --input config\batch.example.json
```

El modo dry-run debe poder activarse desde el mismo flujo principal, por argumento simple o por configuracion, sin obligar a crear comandos separados:

```bat
@echo off
python -m ig_orchestrator --input config\batch.example.json --dry-run
```

Comportamiento dry-run:

* No enviar mensajes a Telegram.
* No mover archivos.
* Si mostrar que habria hecho.
* Si validar URLs, rutas y configuracion.

La CLI completa con comandos `init-db`, `import-batch`, `process-batch`, `process-account`, `retry-failed`, `inspect` y `report` queda como tarea opcional posterior en `tasks/Tarea_Post01.md`.

---

## 18. Funcionalidades documentadas pero no implementadas en v1.0.1

### 18.1 Integracion con script actual de renombrado

El proyecto debe reutilizar el proceso actual de renombrado en una version posterior.

Actualmente existe un `config.json` con esta estructura aproximada:

```json
{
  "renameProcess": {
    "manualFolder": "C:\\Users\\eduba\\Downloads\\DW\\Telegram_Desktop",
    "consultFolders": [
      "G:\\4K Stogram\\00.FAVORITES",
      "G:\\4K Stogram\\00.MODELS-A",
      "G:\\4K Stogram\\00.MODELS-B",
      "G:\\4K Stogram\\00.MODELS-D",
      "G:\\4K Stogram\\06.EXCLUDED"
    ],
    "startNowDate": "2026-06-04",
    "flagNew": false,
    "newUser": {
      "startInitDate": "2025-12-04",
      "userId": "78588237171"
    }
  }
}
```

El modulo futuro `rename_config_builder.py` debe generar o modificar dinamicamente este archivo.

Inputs futuros:

```text
username
start_now_date
manual_folder
consult_folders
flag_new
new_user.start_init_date
new_user.user_id
```

Output futuro:

```text
config.json actualizado
```

Despues se ejecutara:

```text
ManualRenameFiles.bat
```

mediante `subprocess`.

### 18.2 Deteccion de duplicados

Despues de ejecutar el renombrador, el sistema debe buscar archivos cuyo nombre contenga:

```text
_duplicated
```

Acciones posibles segun configuracion:

```text
MOVE_TO_DUPLICATED_FOLDER
DELETE
KEEP
```

Configuracion recomendada inicial:

```text
MOVE_TO_DUPLICATED_FOLDER
```

Destino:

```text
example_user\_duplicated\
```

La eliminacion automatica puede anadirse mas adelante.

### 18.3 Movimiento final

Cuando la cuenta termina correctamente o parcialmente, la carpeta:

```text
C:\Users\eduba\Downloads\DW\Telegram_Desktop\example_user
```

podra moverse a:

```text
G:\4K Stogram\00.FAVORITES\Jhon Lennon\example_user
```

En versiones posteriores podra pedirse el destino explicitamente como input:

```text
--destination "G:\4K Stogram\00.FAVORITES\Jhon Lennon"
```

Si ya existe una carpeta con ese nombre, aplicar una estrategia configurable:

```text
FAIL
MERGE
RENAME_WITH_TIMESTAMP
```

Recomendacion inicial:

```text
FAIL
```

---

## 19. Tareas de implementacion para IA

Las tareas se implementan una a una y estan desglosadas en archivos dentro de `tasks/`.

Cada tarea debe:

* respetar `Agents.md`;
* incluir tests acordes al riesgo;
* actualizar `CHANGELOG.md`;
* no implementar funcionalidades de versiones futuras salvo que la tarea lo indique;
* mantener la ejecucion reanudable y trazable.

### Convencion de versiones

Cada tarea principal genera un minor propio:

```text
Tarea 1  => v1.1.0
Tarea 2  => v1.2.0
Tarea 3  => v1.3.0
...
Tarea 23 => v1.23.0
```

Si despues de implementar una tarea hay que corregir o mejorar algo dentro de esa misma tarea, se incrementa el patch:

```text
Tarea 1 correccion 1 => v1.1.1
Tarea 1 correccion 2 => v1.1.2
Tarea 2 correccion 1 => v1.2.1
```

Al finalizar cada ejecucion de implementacion, la IA debe responder con:

* resumen de cambios;
* pruebas ejecutadas;
* instruccion sugerida de `git commit`;
* instruccion sugerida de `git tag`.

Ejemplo:

```bash
git add .
git commit -m "feat: implement tarea 1 base project structure"
git tag v1.1.0
```

Para patches:

```bash
git add .
git commit -m "fix: adjust tarea 1 project structure"
git tag v1.1.1
```

### Serie v1.x - Descarga, persistencia y reportes

| Tarea | Archivo | Version objetivo | Objetivo |
|---|---|---:|---|
| 1 | `tasks/Tarea1.md` | v1.1.0 | Crear estructura base del proyecto |
| 2 | `tasks/Tarea2.md` | v1.2.0 | Settings y configuracion desde `.env` |
| 3 | `tasks/Tarea3.md` | v1.3.0 | Modelos de dominio |
| 4 | `tasks/Tarea4.md` | v1.4.0 | SQLite schema, migraciones y repositorios |
| 5 | `tasks/Tarea5.md` | v1.5.0 | Parser de JSON por lotes |
| 6 | `tasks/Tarea6.md` | v1.6.0 | Importador JSON a SQLite |
| 7 | `tasks/Tarea7.md` | v1.7.0 | Clasificador de URLs |
| 8 | `tasks/Tarea8.md` | v1.8.0 | Servicio de carpetas |
| 9 | `tasks/Tarea9.md` | v1.9.0 | Cliente Telegram con Telethon |
| 10 | `tasks/Tarea10.md` | v1.10.0 | Parser de respuestas del bot |
| 11 | `tasks/Tarea11.md` | v1.11.0 | Politica de reintentos por ronda |
| 12 | `tasks/Tarea12.md` | v1.12.0 | Watcher de descargas |
| 13 | `tasks/Tarea13.md` | v1.13.0 | Clasificador de archivos |
| 14 | `tasks/Tarea14.md` | v1.14.0 | Movimiento de archivos por tipo |
| 15 | `tasks/Tarea15.md` | v1.15.0 | Servicio de conversacion con bot |
| 16 | `tasks/Tarea16.md` | v1.16.0 | Procesador de URL job |
| 17 | `tasks/Tarea17.md` | v1.17.0 | Orquestador de cuenta y lote |
| 18 | `tasks/Tarea18.md` | v1.18.0 | Reporte Markdown |
| 19 | `tasks/Tarea19.md` | v1.19.0 | Logs |
| 20 | `tasks/Tarea20.md` | v1.20.0 | Modo dry-run |
| 21 | `tasks/Tarea21.md` | v1.21.0 | Tests minimos obligatorios |

### Backlog posterior a v1.0.1

| Tarea | Archivo | Version objetivo | Objetivo |
|---|---|---:|---|
| 22 | `tasks/Tarea22.md` | v1.22.0 | Integracion con script actual de renombrado |
| 23 | `tasks/Tarea23.md` | v1.23.0 | Duplicados del renombrador y movimiento final |
| 24 | `tasks/Tarea24.md` | v1.24.0 | Identidad de lotes, join de pendientes, historico y JSON reutilizable |

### Tareas opcionales posteriores

| Tarea | Archivo | Objetivo |
|---|---|---|
| Post01 | `tasks/Tarea_Post01.md` | CLI completa con Typer |

---

## 20. Flujo esperado de uso en v1.0.1

### 20.1 Preparacion inicial

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Editar `.env`.

La ejecucion principal inicializa la base de datos si hace falta.

### 20.2 Crear archivo de lote

```text
config/batch.example.json
```

Contenido:

```json
{
  "schema_version": "1.0",
  "batch_name": "descargas_junio_2026",
  "defaults": {
    "download_stories": false,
    "start_now_date": "2026-06-04"
  },
  "accounts": [
    {
      "username": "example_user",
      "download_stories": true,
      "urls": [
        "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
        "https://www.instagram.com/reel/ABC123xyz/",
        "https://www.instagram.com/stories/highlights/17851330941375169/"
      ]
    }
  ]
}
```

### 20.3 Crear BAT de ejecucion

```bat
@echo off
cd /d d:\Archivos\Scripts\IG\Automatitation\ig_orchestrator
python -m ig_orchestrator --input config\batch.example.json
```

### 20.4 Ejecutar lote

Al ejecutar el `.bat`, la aplicacion importa el JSON a SQLite y procesa el lote leyendo desde SQLite.

### 20.5 Reintentar fallos

Los errores temporales se reintentan dentro del mismo flujo, al final de cada ronda y respetando `MAX_RETRIES`.

### 20.6 Revisar estado

El estado final debe poder revisarse desde SQLite, logs y el ultimo reporte Markdown.

Resumen esperado:

```text
Account: example_user
Status: PARTIAL

URLs:
- total: 25
- completed: 23
- retry_pending: 1
- failed_final: 1

Files:
- images: 84
- videos: 7

Latest report:
reports/run_20260613_120000.md
```

---

## 21. Posibles mejoras futuras

No implementar en `v1.0.1`.

### 21.1 Integracion Tampermonkey

Crear endpoint local:

```text
POST http://localhost:8765/accounts/{username}/urls
```

Para que Tampermonkey envie URLs directamente a la cola.

### 21.2 Interfaz web local

Crear UI local con Streamlit, FastAPI o una app standalone.

### 21.3 Descarga directa alternativa

Anadir Instaloader como primer intento para stories o posts publicos.

### 21.4 Procesamiento paralelo

Procesar varias cuentas en paralelo, pero no varias URLs contra el mismo bot en la primera version.

### 21.5 Deteccion mas avanzada de posts/reels

Analizar HTML, metadata o respuesta del bot para mejorar la clasificacion.

### 21.6 Integracion con 4K Stogram

Consultar directamente la estructura de carpetas existentes para sugerir destino final.

---

## 22. Notas importantes para la IA que implemente

1. No implementar todo de golpe.
2. Implementar una tarea cada vez.
3. Cada tarea debe incluir tests.
4. Cada tarea debe actualizar `CHANGELOG.md`.
5. No cambiar el comportamiento del renombrador actual salvo que se pida expresamente.
6. No integrar el renombrador en `v1.0.1`.
7. No borrar archivos automaticamente en `v1.0.1`.
8. No mover a destino final en `v1.0.1`.
9. No subir `.env`, sesiones de Telegram ni bases de datos reales.
10. Priorizar fiabilidad sobre velocidad.
11. El proceso puede ser lento, pero debe ser reanudable.
12. Cada URL debe tener trazabilidad propia.
13. El usuario debe poder saber exactamente que URL fallo y por que.
14. La configuracion operativa debe terminar en SQLite.
15. El JSON no debe ser la fuente de verdad despues de importarse.

---

## 23. Definicion de v1.0.1 terminada

La version `v1.0.1` se considera terminada cuando:

1. El usuario puede inicializar SQLite sin perder datos existentes.
2. El usuario puede importar un JSON por lotes.
3. El sistema guarda configuracion y trabajos en SQLite.
4. El sistema genera URL de stories cuando `download_stories = true`.
5. El sistema clasifica posts, reels, stories y highlights.
6. El sistema procesa primero stories y despues URLs manuales.
7. El sistema envia URLs al bot de Telegram usando la cuenta personal.
8. El sistema detecta errores reintentables y definitivos del bot.
9. El sistema no reintenta errores definitivos de stories privadas/no encontradas.
10. El sistema reintenta errores temporales al final de la ronda.
11. El sistema detecta archivos descargados.
12. El sistema mueve archivos a carpetas correctas.
13. El sistema genera reporte Markdown por ejecucion.
14. El sistema puede reanudarse si se corta.
15. El sistema puede mostrar que URLs fallaron y por que.

---

## 24. Definicion futura de version 1 terminada

La version 1 completa, posterior a `v1.0.1`, se considera terminada cuando ademas:

1. El sistema ejecuta el renombrador actual.
2. El sistema mueve duplicados a `_duplicated`.
3. El sistema mueve la carpeta final al destino configurado.
4. El sistema mantiene reportes de descarga y de post-procesado.
