# Instagram Manual Download Orchestrator

## 1. Descripción general

Este proyecto automatiza un proceso manual de descarga, clasificación, renombrado y organización de publicaciones de Instagram descargadas mediante un bot de Telegram.

La primera versión del sistema parte de tres inputs manuales:

```text
username
url_list
start_now_date
```

El objetivo es automatizar todo lo posterior:

1. Crear estructura temporal de trabajo para el usuario.
2. Registrar URLs en una cola persistente.
3. Enviar URLs al bot de Telegram usando la cuenta personal del usuario.
4. Detectar respuestas del bot.
5. Detectar archivos descargados en la carpeta de Telegram_Desktop.
6. Asociar archivos descargados con cada URL.
7. Clasificar archivos en `reels`, `posts` o `story`.
8. Ejecutar el proceso actual de renombrado.
9. Detectar duplicados.
10. Mover duplicados a una carpeta separada o eliminarlos según configuración.
11. Mover la carpeta final del usuario a su destino definitivo en `G:\4K Stogram`.

El sistema debe estar diseñado de forma modular, para que cada tarea pueda implementarse, probarse y evolucionarse de manera independiente.

---

## 2. Objetivo de la primera versión

La primera versión no automatiza la navegación por Instagram ni la extracción automática de URLs desde el navegador.

El usuario introduce manualmente:

```text
username = "example_user"
start_now_date = "2026-06-04"
url_list = [
    "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
    "https://www.instagram.com/reel/ABC123xyz/"
]
```

A partir de esos datos, el sistema debe procesar la cuenta completa.

---

## 3. Principios de diseño

### 3.1 Modularidad

Cada módulo debe tener una responsabilidad clara.

No debe existir un script gigante que haga todo.

Cada componente debe poder probarse de manera independiente.

### 3.2 Persistencia

Todo el estado debe guardarse en SQLite.

El proceso debe poder interrumpirse y reanudarse.

### 3.3 Trazabilidad

Cada URL debe tener un estado individual.

El sistema debe saber:

* cuándo fue enviada al bot;
* qué respuesta recibió;
* cuántos reintentos lleva;
* qué archivos se descargaron después;
* si terminó correctamente;
* si falló definitivamente;
* si produjo archivos duplicados.

### 3.4 Seguridad

Las credenciales no deben estar en el código.

Los datos sensibles deben ir en `.env`.

El archivo de sesión de Telethon no debe subirse al repositorio.

### 3.5 Compatibilidad Windows

El proyecto está pensado para Windows 11.

Debe soportar rutas como:

```text
C:\Users\eduba\Downloads\DW\Telegram_Desktop
G:\4K Stogram\00.FAVORITES
```

---

## 4. Stack técnico recomendado

### 4.1 Lenguaje

```text
Python 3.11+
```

### 4.2 Librerías principales

```text
telethon
python-dotenv
pydantic
watchdog
typer
rich
loguru
pytest
pytest-asyncio
```

### 4.3 Librerías estándar de Python

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
│
├── README.md
├── PLAN.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   ├── app.example.json
│   └── rename.example.json
│
├── data/
│   └── .gitkeep
│
├── logs/
│   └── .gitkeep
│
├── scripts/
│   ├── init_db.py
│   ├── run_account.py
│   ├── retry_failed.py
│   ├── inspect_queue.py
│   └── clean_duplicates.py
│
├── src/
│   └── ig_orchestrator/
│       │
│       ├── __init__.py
│       │
│       ├── main.py
│       │
│       ├── settings.py
│       │
│       ├── constants.py
│       │
│       ├── exceptions.py
│       │
│       ├── logging_config.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── account.py
│       │   ├── url_job.py
│       │   ├── download_file.py
│       │   └── run_summary.py
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── schema.sql
│       │   ├── migrations.py
│       │   ├── account_repository.py
│       │   ├── url_job_repository.py
│       │   ├── download_repository.py
│       │   └── run_repository.py
│       │
│       ├── input/
│       │   ├── __init__.py
│       │   ├── manual_input_parser.py
│       │   └── url_classifier.py
│       │
│       ├── filesystem/
│       │   ├── __init__.py
│       │   ├── folder_service.py
│       │   ├── file_watcher.py
│       │   ├── file_classifier.py
│       │   ├── file_mover.py
│       │   └── duplicate_cleaner.py
│       │
│       ├── telegram/
│       │   ├── __init__.py
│       │   ├── telegram_client.py
│       │   ├── bot_conversation_service.py
│       │   ├── bot_response_parser.py
│       │   └── telegram_download_tracker.py
│       │
│       ├── rename/
│       │   ├── __init__.py
│       │   ├── rename_config_builder.py
│       │   ├── manual_rename_runner.py
│       │   └── rename_result_parser.py
│       │
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── account_orchestrator.py
│       │   ├── url_job_processor.py
│       │   ├── retry_policy.py
│       │   └── run_summary_builder.py
│       │
│       └── cli/
│           ├── __init__.py
│           └── commands.py
│
└── tests/
    ├── unit/
    │   ├── test_url_classifier.py
    │   ├── test_bot_response_parser.py
    │   ├── test_retry_policy.py
    │   ├── test_file_classifier.py
    │   ├── test_folder_service.py
    │   └── test_rename_config_builder.py
    │
    └── integration/
        ├── test_sqlite_repositories.py
        └── test_account_orchestrator_dry_run.py
```

---

## 6. Archivo `.env.example`

```env
# Telegram API credentials
# Obtener desde Telegram API Development Tools.
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# Nombre del archivo de sesión local de Telethon.
# No subir este archivo al repositorio.
TELETHON_SESSION_NAME=telegram_user_session

# Username o identificador del bot de Telegram usado para descargar publicaciones.
TELEGRAM_DOWNLOAD_BOT_USERNAME=@example_bot

# Carpetas locales
TELEGRAM_DESKTOP_DOWNLOAD_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop
WORKING_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop
FINAL_BASE_FOLDER=G:\4K Stogram\00.FAVORITES

# Script actual de renombrado
MANUAL_RENAME_BAT_PATH=C:\path\to\ManualRenameFiles.bat
MANUAL_RENAME_CONFIG_PATH=C:\path\to\config.json

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

---

## 7. `requirements.txt`
Actualizar este archivo en caso de que ya exista.

```txt
telethon>=1.34.0
python-dotenv>=1.0.0
pydantic>=2.0.0
watchdog>=4.0.0
typer>=0.12.0
rich>=13.0.0
loguru>=0.7.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 8. Base de datos SQLite

### 8.1 Tabla `accounts`

Representa una cuenta de Instagram que se va a procesar.

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    start_now_date TEXT NOT NULL,
    final_destination_folder TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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

---

### 8.2 Tabla `url_jobs`

Representa cada URL individual a descargar.

```sql
CREATE TABLE IF NOT EXISTS url_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    publication_type TEXT NOT NULL,
    status TEXT NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    sent_message_id INTEGER,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
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
RENAMED
DUPLICATED
COMPLETED
```

---

### 8.3 Tabla `download_files`

Representa cada archivo detectado después de enviar una URL al bot.

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

Valores posibles de `status`:

```text
DETECTED
MOVED_TO_WORKING_FOLDER
CLASSIFIED_AS_REEL
CLASSIFIED_AS_POST
RENAMED
DUPLICATED
DELETED
FINALIZED
```

---

### 8.4 Tabla `runs`

Representa una ejecución completa.

```sql
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    total_urls INTEGER NOT NULL DEFAULT 0,
    completed_urls INTEGER NOT NULL DEFAULT 0,
    failed_urls INTEGER NOT NULL DEFAULT 0,
    duplicated_files INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);
```

---

## 9. Clasificación de URLs de Instagram

### 9.1 Regla inicial

Dada una URL de Instagram:

```text
https://www.instagram.com/p/DZPjwEjitxx/?img_index=1
```

Si la URL contiene `img_index`, se clasifica como:

```text
POST
```

Si la URL no contiene `img_index`, se clasifica inicialmente como:

```text
REEL
```

Pero esta clasificación inicial puede corregirse después según el tipo de archivo descargado.

---

### 9.2 Corrección posterior según archivo descargado

Si una URL fue clasificada inicialmente como `REEL`, pero el bot descarga únicamente archivos `.jpg`, `.jpeg`, `.png` o `.webp`, entonces debe reclasificarse como:

```text
POST
```

Si descarga `.mp4`, `.mov` o similar, se mantiene como:

```text
REEL
```

Si descarga mezcla de vídeos e imágenes, se mantiene como:

```text
POST para imagenes y REEL para el video
```

---

## 10. Estructura temporal por cuenta

Dado:

```text
username = example_user
```

El sistema debe crear:

```text
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\story\
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\reels\
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\highlights\
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\_duplicated\
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\_errors\
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user\_logs\
```

Reglas:

* Los vídeos de reels deben ir a `reels`.
* Las stories deben ir a `story`.
* Las highlights deben ir a `highlights`.
* Las fotos de posts deben quedar en la carpeta raíz del usuario.
* Los duplicados deben moverse a `_duplicated`, salvo que la configuración indique eliminación automática.
* Los errores deben registrarse en `_errors`.

---

## 11. Integración con Telegram mediante Telethon

### 11.1 Por qué Telethon

El bot de Telegram usado para descargar publicaciones es de pago y responde a la cuenta personal del usuario.

Por tanto, el sistema debe conectarse a Telegram como usuario real, no como bot propio.

Telethon permite crear un cliente de Telegram usando:

```text
api_id
api_hash
phone number
session file
```

En la primera ejecución, Telethon pedirá iniciar sesión.

Después se guardará una sesión local, por ejemplo:

```text
telegram_user_session.session
```

Ese archivo permite reutilizar la sesión sin introducir el código cada vez.

---

### 11.2 Importante

No subir nunca al repositorio:

```text
*.session
*.session-journal
.env
```

Añadir a `.gitignore`:

```gitignore
.env
*.session
*.session-journal
data/*.db
logs/*.log
```

---

### 11.3 Flujo esperado con el bot

Para cada URL:

1. Enviar URL al bot.
2. Guardar `sent_message_id`.
3. Esperar respuesta del bot.
4. Detectar si la respuesta contiene error.
5. Esperar archivos nuevos en la carpeta de Telegram Desktop.
6. Asociar los archivos nuevos con esa URL.
7. Marcar la URL como descargada o fallida.

---

## 12. Errores conocidos del bot de Telegram

El bot puede responder con errores.

Errores conocidos:

```text
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable
```

### 12.1 Errores reintentables

Estos errores deben considerarse temporales:

```text
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable
```

Aunque algunos puedan parecer definitivos, en la práctica se deben reintentar varias veces porque el bot o el servicio remoto puede fallar temporalmente.

---

### 12.2 Política de reintentos

Configuración inicial:

```text
MAX_RETRIES = 5
RETRY_BASE_SECONDS = 90
RETRY_MAX_SECONDS = 900
```

Estrategia:

```text
retry_1 = 90 segundos
retry_2 = 180 segundos
retry_3 = 360 segundos
retry_4 = 720 segundos
retry_5 = 900 segundos
```

Después de `MAX_RETRIES`, marcar como:

```text
FAILED_FINAL
```

---

## 13. Watcher de carpeta Telegram Desktop

### 13.1 Objetivo

Detectar qué archivos aparecen después de enviar una URL al bot.

### 13.2 Regla de asociación

Antes de enviar una URL:

```text
download_start_time = now()
```

Después de enviar la URL:

1. Observar la carpeta `Telegram_Desktop`.
2. Detectar archivos creados después de `download_start_time`.
3. Esperar hasta que no aparezcan archivos nuevos durante `DOWNLOAD_STABLE_SECONDS`.
4. Asociar esos archivos al `url_job`.

---

### 13.3 Precauciones

No mover un archivo mientras todavía se está descargando.

Un archivo se considera estable cuando:

* existe;
* su tamaño no cambia durante varios segundos;
* no tiene extensión temporal;
* no está bloqueado por otro proceso.

---

## 14. Clasificación de archivos

### 14.1 Extensiones de imagen

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

### 14.2 Extensiones de vídeo

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

### 14.3 Reglas de movimiento

Si `publication_type = REEL` y archivo es vídeo:

```text
example_user\reels\
```

Si `publication_type = POST` y archivo es imagen:

```text
example_user\
```

Si `publication_type = REEL` pero todos los archivos son imágenes:

```text
corregir publication_type a POST
mover imágenes a example_user\
```

Si son stories:

```text
example_user\story\
```

Si son hightlights:

```text
example_user\highlights\
```

En la primera versión, las stories pueden quedar fuera del flujo principal y procesarse manualmente o como tarea separada.

---

## 15. Integración con script actual de renombrado

El proyecto debe reutilizar el proceso actual de renombrado.

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

El módulo `rename_config_builder.py` debe generar o modificar dinámicamente este archivo.

Inputs:

```text
username
start_now_date
manual_folder
consult_folders
flag_new
new_user.start_init_date
new_user.user_id
```

Output:

```text
config.json actualizado
```

Después se ejecuta:

```text
ManualRenameFiles.bat
```

mediante `subprocess`.

---

## 16. Detección de duplicados

Después de ejecutar el renombrador, el sistema debe buscar archivos cuyo nombre contenga:

```text
_duplicated
```

Acciones posibles según configuración:

```text
MOVE_TO_DUPLICATED_FOLDER
DELETE
KEEP
```

Configuración recomendada inicial:

```text
MOVE_TO_DUPLICATED_FOLDER
```

Destino:

```text
example_user\_duplicated\
```

La eliminación automática puede añadirse más adelante.

---

## 17. Movimiento final

Cuando la cuenta termina correctamente o parcialmente, la carpeta:

```text
C:\Users\eduba\Downloads\DW\Telegram Desktop\example_user
```

debe moverse a:

```text
G:\4K Stogram\00.FAVORITES\Jhon Lennon\example_user
```

La primera versión puede pedir el destino explícitamente como input:

```text
--destination "G:\4K Stogram\00.FAVORITES\Jhon Lennon"
```

Resultado:

```text
G:\4K Stogram\00.FAVORITES\Jhon Lennon\example_user
```

Si ya existe una carpeta con ese nombre, aplicar una estrategia configurable:

```text
FAIL
MERGE
RENAME_WITH_TIMESTAMP
```

Recomendación inicial:

```text
FAIL
```

---

## 18. CLI esperada

El sistema debe exponer comandos mediante Typer.

### 18.1 Inicializar base de datos

```bash
python -m ig_orchestrator init-db
```

### 18.2 Crear cuenta y registrar URLs

```bash
python -m ig_orchestrator create-account \
  --username example_user \
  --start-now-date 2026-06-04 \
  --destination "G:\4K Stogram\00.FAVORITES\Jhon Lennon" \
  --urls-file urls.txt
```

### 18.3 Procesar cuenta

```bash
python -m ig_orchestrator process-account \
  --username example_user
```

### 18.4 Reintentar errores

```bash
python -m ig_orchestrator retry-failed \
  --username example_user
```

### 18.5 Ver estado

```bash
python -m ig_orchestrator inspect \
  --username example_user
```

### 18.6 Ejecutar solo renombrado

```bash
python -m ig_orchestrator rename \
  --username example_user \
  --start-now-date 2026-06-04
```

### 18.7 Limpiar duplicados

```bash
python -m ig_orchestrator clean-duplicates \
  --username example_user
```

### 18.8 Mover a destino final

```bash
python -m ig_orchestrator move-final \
  --username example_user
```

---

## 19. Tareas de implementación para IA

Las siguientes tareas deben implementarse una a una.

Cada tarea debe ser independiente.

---

# Tarea 1 — Crear estructura base del proyecto

## Objetivo

Crear la estructura inicial del proyecto Python.

## Inputs

Ninguno.

## Outputs

Estructura de carpetas creada.

Archivos mínimos:

```text
README.md
PLAN.md
requirements.txt
.env.example
.gitignore
src/ig_orchestrator/__init__.py
src/ig_orchestrator/main.py
```

## Criterios de aceptación

* El proyecto instala dependencias.
* Se puede ejecutar `python -m ig_orchestrator`.
* `.env`, `.session` y base de datos SQLite están en `.gitignore`.

---

# Tarea 2 — Settings y configuración

## Objetivo

Crear un módulo de configuración que lea `.env`.

## Archivos

```text
src/ig_orchestrator/settings.py
```

## Inputs

Variables de entorno.

## Outputs

Objeto `Settings`.

## Campos requeridos

```text
telegram_api_id
telegram_api_hash
telethon_session_name
telegram_download_bot_username
telegram_desktop_download_folder
working_folder
final_base_folder
manual_rename_bat_path
manual_rename_config_path
sqlite_db_path
max_retries
retry_base_seconds
retry_max_seconds
download_wait_timeout_seconds
download_stable_seconds
```

## Criterios de aceptación

* Si falta una variable obligatoria, mostrar error claro.
* Las rutas deben manejarse con `pathlib.Path`.
* Añadir tests unitarios.

---

# Tarea 3 — Modelo de dominio

## Objetivo

Crear modelos de dominio con Pydantic o dataclasses.

## Archivos

```text
src/ig_orchestrator/models/account.py
src/ig_orchestrator/models/url_job.py
src/ig_orchestrator/models/download_file.py
src/ig_orchestrator/models/run_summary.py
```

## Entidades

```text
Account
UrlJob
DownloadFile
RunSummary
```

## Criterios de aceptación

* Los modelos validan datos mínimos.
* Los estados deben representarse con Enum.
* Añadir tests unitarios.

---

# Tarea 4 — Clasificador de URLs

## Objetivo

Implementar clasificación inicial de URLs.

## Archivo

```text
src/ig_orchestrator/input/url_classifier.py
```

## Reglas

```text
Si contiene "img_index" => POST
Si no contiene "img_index" => REEL
Si URL no es Instagram => error
```

## Inputs

```text
url: str
```

## Output

```text
PublicationType.POST
PublicationType.REEL
```

## Tests mínimos

```text
https://www.instagram.com/p/DZPjwEjitxx/?img_index=1 => POST
https://www.instagram.com/reel/ABC123xyz/ => REEL
https://www.instagram.com/p/DZPjwEjitxx/ => REEL inicialmente
https://example.com/foo => error
```

---

# Tarea 5 — Parser de input manual

## Objetivo

Leer un archivo `urls.txt` y registrar URLs limpias.

## Archivo

```text
src/ig_orchestrator/input/manual_input_parser.py
```

## Inputs

```text
username
start_now_date
urls_file
destination
```

## Output

```text
Account
List[UrlJob]
```

## Reglas

* Ignorar líneas vacías.
* Eliminar espacios.
* No duplicar URLs dentro del mismo input.
* Validar formato de fecha `YYYY-MM-DD`.

---

# Tarea 6 — SQLite schema y repositorios

## Objetivo

Crear la base de datos y repositorios.

## Archivos

```text
src/ig_orchestrator/db/schema.sql
src/ig_orchestrator/db/connection.py
src/ig_orchestrator/db/migrations.py
src/ig_orchestrator/db/account_repository.py
src/ig_orchestrator/db/url_job_repository.py
src/ig_orchestrator/db/download_repository.py
src/ig_orchestrator/db/run_repository.py
```

## Criterios de aceptación

* Comando `init-db` crea tablas.
* Se puede crear una cuenta.
* Se pueden insertar URLs.
* Se puede actualizar el estado de una URL.
* Se puede consultar URLs por estado.
* Tests de integración con SQLite temporal.

---

# Tarea 7 — Servicio de carpetas

## Objetivo

Crear estructura temporal de trabajo para una cuenta.

## Archivo

```text
src/ig_orchestrator/filesystem/folder_service.py
```

## Input

```text
username
working_folder
```

## Output

```text
AccountFolderStructure
```

## Carpetas creadas

```text
username/
username/story/
username/reels/
username/_duplicated/
username/_errors/
username/_logs/
```

## Criterios de aceptación

* Si la carpeta existe, no destruir contenido.
* Si falta una subcarpeta, crearla.
* Tests unitarios con carpeta temporal.

---

# Tarea 8 — Cliente Telegram con Telethon

## Objetivo

Crear wrapper para Telethon.

## Archivo

```text
src/ig_orchestrator/telegram/telegram_client.py
```

## Responsabilidades

* Inicializar cliente Telethon.
* Iniciar sesión si no existe sesión.
* Enviar mensaje a bot.
* Leer últimos mensajes del bot.
* Obtener mensajes nuevos después de un timestamp.

## Inputs

```text
api_id
api_hash
session_name
bot_username
```

## Outputs

```text
sent_message_id
bot_messages
```

## Criterios de aceptación

* La primera ejecución debe pedir login si no hay sesión.
* Las siguientes ejecuciones deben reutilizar sesión.
* No loguear credenciales.
* Tests unitarios con mocks.

---

# Tarea 9 — Parser de respuestas del bot

## Objetivo

Detectar errores conocidos y respuestas útiles del bot.

## Archivo

```text
src/ig_orchestrator/telegram/bot_response_parser.py
```

## Errores conocidos

```text
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable
```

## Output esperado

```text
BotResponseStatus.OK
BotResponseStatus.RETRYABLE_ERROR
BotResponseStatus.UNKNOWN
```

## Criterios de aceptación

* Detectar errores aunque cambien mayúsculas/minúsculas.
* Guardar mensaje original como `last_error`.
* Tests unitarios.

---

# Tarea 10 — Política de reintentos

## Objetivo

Calcular cuándo reintentar una URL fallida.

## Archivo

```text
src/ig_orchestrator/orchestration/retry_policy.py
```

## Inputs

```text
retries
max_retries
base_seconds
max_seconds
```

## Output

```text
RetryDecision
```

## Reglas

```text
0 retries => esperar 90 segundos
1 retry => esperar 180 segundos
2 retries => esperar 360 segundos
3 retries => esperar 720 segundos
4 retries => esperar 900 segundos
>= max_retries => FAILED_FINAL
```

## Criterios de aceptación

* Tests unitarios.
* No dormir dentro de la política.
* La política solo calcula.

---

# Tarea 11 — Watcher de descargas

## Objetivo

Detectar archivos nuevos descargados por Telegram Desktop.

## Archivo

```text
src/ig_orchestrator/filesystem/file_watcher.py
```

## Inputs

```text
folder
start_time
timeout_seconds
stable_seconds
```

## Output

```text
List[Path]
```

## Reglas

* Solo devolver archivos creados o modificados después de `start_time`.
* Esperar a que el tamaño del archivo sea estable.
* Ignorar directorios.
* Ignorar archivos temporales.

## Criterios de aceptación

* Tests unitarios o de integración con carpeta temporal.
* No mover archivos.
* Solo detectar.

---

# Tarea 12 — Clasificador de archivos

## Objetivo

Clasificar archivos descargados.

## Archivo

```text
src/ig_orchestrator/filesystem/file_classifier.py
```

## Inputs

```text
Path
```

## Output

```text
MediaType.IMAGE
MediaType.VIDEO
MediaType.UNKNOWN
```

## Reglas

```text
.jpg, .jpeg, .png, .webp => IMAGE
.mp4, .mov, .mkv, .webm => VIDEO
otro => UNKNOWN
```

## Criterios de aceptación

* Tests unitarios.
* Extensiones case-insensitive.

---

# Tarea 13 — Movimiento de archivos por tipo

## Objetivo

Mover archivos descargados a la carpeta correcta del usuario.

## Archivo

```text
src/ig_orchestrator/filesystem/file_mover.py
```

## Inputs

```text
url_job
downloaded_files
account_folder_structure
```

## Output

```text
List[DownloadFile]
```

## Reglas

* Si archivo es vídeo, mover a `reels`.
* Si archivo es imagen, mover a raíz de `username`.
* Si una URL inicialmente `REEL` descarga solo imágenes, reclasificar como `POST`.
* Evitar sobrescritura accidental.
* Si el destino existe, añadir sufijo seguro.

---

# Tarea 14 — Servicio de conversación con bot

## Objetivo

Procesar una URL completa contra el bot.

## Archivo

```text
src/ig_orchestrator/telegram/bot_conversation_service.py
```

## Flujo

1. Marcar URL como `SENT_TO_BOT`.
2. Enviar URL al bot.
3. Guardar `sent_message_id`.
4. Esperar respuesta.
5. Si hay error reintentable, marcar `RETRY_PENDING`.
6. Si no hay error, activar watcher.
7. Asociar archivos detectados.
8. Marcar como `DOWNLOADED`.

## Criterios de aceptación

* No procesar dos URLs al mismo tiempo en la primera versión.
* Una URL debe tener logs propios.
* Tests con mocks.

---

# Tarea 15 — Procesador de URL job

## Objetivo

Coordinar Telegram, watcher, clasificación y repositorios para una URL.

## Archivo

```text
src/ig_orchestrator/orchestration/url_job_processor.py
```

## Input

```text
url_job_id
```

## Output

```text
UrlJob actualizado
DownloadFiles registrados
```

## Criterios de aceptación

* Si Telegram devuelve error, aplicar política de reintentos.
* Si se descargan archivos, registrar cada archivo.
* Si no se descarga nada dentro del timeout, marcar error temporal.
* Tests con mocks.

---

# Tarea 16 — Generador de config para renombrado

## Objetivo

Crear o actualizar `config.json` para el script actual.

## Archivo

```text
src/ig_orchestrator/rename/rename_config_builder.py
```

## Inputs

```text
manual_folder
consult_folders
start_now_date
flag_new
new_user
```

## Output

```text
config.json
```

## Criterios de aceptación

* Mantener formato JSON válido.
* No perder otras claves existentes si el config original contiene más información.
* Tests unitarios.

---

# Tarea 17 — Runner del renombrador actual

## Objetivo

Ejecutar `ManualRenameFiles.bat`.

## Archivo

```text
src/ig_orchestrator/rename/manual_rename_runner.py
```

## Inputs

```text
bat_path
working_directory
```

## Output

```text
RenameExecutionResult
```

## Criterios de aceptación

* Capturar stdout.
* Capturar stderr.
* Capturar exit code.
* Si falla, marcar proceso como `FAILED`.
* Tests con mock de subprocess.

---

# Tarea 18 — Limpieza de duplicados

## Objetivo

Detectar archivos renombrados como duplicados.

## Archivo

```text
src/ig_orchestrator/filesystem/duplicate_cleaner.py
```

## Input

```text
account_folder
strategy
```

## Strategies

```text
MOVE_TO_DUPLICATED_FOLDER
DELETE
KEEP
```

## Primera versión

Usar:

```text
MOVE_TO_DUPLICATED_FOLDER
```

## Criterios de aceptación

* Buscar archivos que contengan `_duplicated`.
* Moverlos a `_duplicated`.
* No borrar nada en la primera versión.
* Tests unitarios.

---

# Tarea 19 — Movimiento final de carpeta

## Objetivo

Mover la carpeta procesada al destino final.

## Archivo

```text
src/ig_orchestrator/filesystem/file_mover.py
```

## Input

```text
source_account_folder
destination_parent_folder
username
```

## Output

```text
final_account_folder
```

## Regla inicial

Si destino existe:

```text
FAIL
```

No mezclar carpetas automáticamente en la primera versión.

---

# Tarea 20 — Orquestador de cuenta

## Objetivo

Coordinar todo el proceso para un username.

## Archivo

```text
src/ig_orchestrator/orchestration/account_orchestrator.py
```

## Flujo completo

1. Cargar cuenta.
2. Crear carpetas.
3. Obtener URLs pendientes.
4. Procesar URLs una por una.
5. Reintentar URLs con errores temporales según política.
6. Ejecutar renombrado.
7. Limpiar duplicados.
8. Generar resumen.
9. Mover a destino final si no hay errores finales.
10. Marcar cuenta como `COMPLETED`, `PARTIAL` o `FAILED`.

## Criterios de aceptación

* Si algunas URLs fallan definitivamente, marcar cuenta como `PARTIAL`.
* Si todas completan, marcar `COMPLETED`.
* Si falla infraestructura, marcar `FAILED`.
* Generar resumen legible.

---

# Tarea 21 — CLI

## Objetivo

Crear comandos CLI con Typer.

## Archivo

```text
src/ig_orchestrator/cli/commands.py
```

## Comandos

```text
init-db
create-account
process-account
retry-failed
inspect
rename
clean-duplicates
move-final
```

## Criterios de aceptación

* Cada comando debe tener ayuda.
* Cada comando debe mostrar salida clara con Rich.
* Los errores deben ser comprensibles.

---

# Tarea 22 — Logs

## Objetivo

Crear logs por ejecución y por cuenta.

## Archivo

```text
src/ig_orchestrator/logging_config.py
```

## Salidas

```text
logs/app.log
username/_logs/run_YYYYMMDD_HHMMSS.log
```

## Debe registrar

* cuenta procesada;
* URL procesada;
* mensaje enviado al bot;
* respuesta del bot;
* archivos detectados;
* errores;
* reintentos;
* duplicados;
* movimiento final.

No registrar:

* api_hash;
* códigos de login;
* contenido sensible de `.env`.

---

# Tarea 23 — Modo dry-run

## Objetivo

Permitir probar sin enviar mensajes reales al bot ni mover archivos.

## Flag CLI

```bash
--dry-run
```

## Comportamiento

* No enviar mensajes a Telegram.
* No mover archivos.
* No ejecutar BAT.
* Sí mostrar qué habría hecho.
* Sí validar URLs, rutas y configuración.

---

# Tarea 24 — Tests mínimos obligatorios

Antes de considerar la versión 1 terminada, deben existir tests para:

```text
url_classifier
manual_input_parser
retry_policy
bot_response_parser
file_classifier
folder_service
rename_config_builder
duplicate_cleaner
sqlite repositories
account_orchestrator dry-run
```

---

## 20. Flujo esperado de uso en versión 1

### 20.1 Preparación inicial

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Editar `.env`.

Inicializar base de datos:

```bash
python -m ig_orchestrator init-db
```

---

### 20.2 Crear archivo de URLs

```text
urls.txt
```

Contenido:

```text
https://www.instagram.com/p/DZPjwEjitxx/?img_index=1
https://www.instagram.com/reel/ABC123xyz/
https://www.instagram.com/p/XYZ789abc/
```

---

### 20.3 Crear cuenta

```bash
python -m ig_orchestrator create-account ^
  --username example_user ^
  --start-now-date 2026-06-04 ^
  --destination "G:\4K Stogram\00.FAVORITES\Jhon Lennon" ^
  --urls-file urls.txt
```

---

### 20.4 Procesar cuenta

```bash
python -m ig_orchestrator process-account --username example_user
```

---

### 20.5 Reintentar fallos

```bash
python -m ig_orchestrator retry-failed --username example_user
```

---

### 20.6 Inspeccionar estado

```bash
python -m ig_orchestrator inspect --username example_user
```

Salida esperada:

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
- duplicated: 3

Final folder:
G:\4K Stogram\00.FAVORITES\Jhon Lennon\example_user
```

---

## 21. Posibles mejoras futuras

No implementar en versión 1.

### 21.1 Integración Tampermonkey

Crear endpoint local:

```text
POST http://localhost:8765/accounts/{username}/urls
```

Para que Tampermonkey envíe URLs directamente a la cola.

### 21.2 Interfaz web local

Crear UI local con Streamlit o FastAPI.

### 21.3 Descarga directa alternativa

Añadir Instaloader como primer intento para stories o posts públicos.

### 21.4 Procesamiento paralelo

Procesar varias cuentas en paralelo, pero no varias URLs contra el mismo bot en la primera versión.

### 21.5 Detección más avanzada de posts/reels

Analizar HTML, metadata o respuesta del bot para mejorar la clasificación.

### 21.6 Integración con 4K Stogram

Consultar directamente la estructura de carpetas existentes para sugerir destino final.

---

## 22. Notas importantes para la IA que implemente

1. No implementar todo de golpe.
2. Implementar una tarea cada vez.
3. Cada tarea debe incluir tests.
4. No cambiar el comportamiento del renombrador actual salvo que se pida expresamente.
5. No borrar archivos automáticamente en la primera versión.
6. No subir `.env`, sesiones de Telegram ni bases de datos reales.
7. Priorizar fiabilidad sobre velocidad.
8. El proceso puede ser lento, pero debe ser reanudable.
9. Cada URL debe tener trazabilidad propia.
10. El usuario debe poder saber exactamente qué URL falló y por qué.

---

## 23. Definición de versión 1 terminada

La versión 1 se considera terminada cuando:

1. El usuario puede crear una cuenta desde CLI.
2. El usuario puede cargar una lista de URLs.
3. El sistema clasifica URLs inicialmente.
4. El sistema envía URLs al bot de Telegram usando la cuenta personal.
5. El sistema detecta errores del bot.
6. El sistema reintenta errores temporales.
7. El sistema detecta archivos descargados.
8. El sistema mueve archivos a carpetas correctas.
9. El sistema ejecuta el renombrador actual.
10. El sistema mueve duplicados a `_duplicated`.
11. El sistema genera resumen.
12. El sistema puede reanudarse si se corta.
13. El sistema puede mostrar qué URLs fallaron.
14. El sistema puede mover la carpeta final al destino configurado.
