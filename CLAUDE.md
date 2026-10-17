# CLAUDE.md — ig_orchestrator

## Cómo trabajar en una sesión nueva (LEER PRIMERO)

Esta sesión puede no tener contexto previo. **Antes de responder una pregunta o de pedir/hacer un cambio, consulta la documentación del proyecto** en este orden y no te fíes de la memoria:

1. `docs/arquitectura-v3.md` — guía técnica: estado, módulos, modelo de datos, ajustes, invariantes, recetas, pruebas, limitaciones y mapa de «dónde mirar cada cosa».
2. `docs/manual-usuario.md` — qué hace cada menú, menú contextual y modal de la GUI, y qué abre.
3. `docs/tutorial-v3.md` — cada feat de v3 con campos, ejemplos y cómo probarlo.
4. `CHANGELOG.md` — qué cambió, cuándo, qué se probó.
5. `tasks/done/v3/feat-*.md` (sección «Resultado de la implementación») y `docs/v3-status.md` — decisiones, qué no se hizo y por qué.
6. `MODULE.md` del paquete afectado y el código.

Reglas de sesión:
- Para preguntas de «¿cómo funciona / dónde está / por qué?», responde desde esos documentos y verifica en el código/base de datos si hay duda; si el documento está desactualizado, corrígelo.
- Para cambios, sigue el proceso de «Changelog y Commits» (más abajo): código + tests + CHANGELOG + manual + (tutorial) + MODULE.md + `docs/arquitectura-v3.md` si cambia la arquitectura, el modelo de datos, los ajustes o las limitaciones.
- Responde en español y, cuando el usuario pregunte «dónde/cómo», con pasos cortos y no técnicos.
- No ejecutes acciones destructivas sobre `G:` real; prueba en copias. Informa de lo que no se pudo probar.

## Propósito del Proyecto

**ig_orchestrator** es un orquestador para preparar, trazar y procesar descargas manuales de Instagram mediante un bot de Telegram.

El usuario escribe un lote de cuentas y URLs en JSON, la aplicación lo importa a SQLite, procesa las URLs en orden, usa Telegram/Telethon para hablar con el bot de descarga, detecta los archivos que aparecen en la carpeta de Telegram Desktop, los mueve a una estructura por cuenta y deja trazabilidad en base de datos, logs y reportes.

## Información Crítica

### Estado Actual (v3.24.0)

- Rama activa: `v3/integration` (tags `v3.2.0`…`v3.24.0`; PR a `master` pendiente). Detalle y limitaciones: `docs/arquitectura-v3.md`.
- v3 integra en la app los procesos manuales (sincronización con el disco en lugar de sc1, renombrado integrado en lugar de sc2, catálogo = disco con operaciones reales, instancias, almacén/volcado, papelera); la base de la app (`orchestrator_gui.sqlite`) es la única fuente de verdad.
- El flujo real se ejecuta con `python -m ig_orchestrator --input config\batch.json` o `--run`
- La GUI de escritorio funciona con `python -m ig_orchestrator gui`
- SQLite v2 (`data/orchestrator_gui.sqlite`) es la fuente de verdad en la GUI
- SQLite v1 (`data/orchestrator.sqlite`) es el rollback y se usa por CLI
- Cada `batch_name` se importa una sola vez; una ejecución interrumpida se retoma desde SQLite
- Tras importar un lote real se crea un backup en `config\bkp` y `batch.json` queda limpio

### Versiones Activas

**Serie v1.x** — CLI y GUI en Tkinter, SQLite v1:
- Objetivo: estabilizar descarga, persistencia, reintentos y reportes
- Última: v1.31.0
- Rollback disponible si GUI v2 falla

**Serie v3.x** — integración de sc1/sc2 y gestión de la biblioteca (rama `v3/integration`): ver `docs/arquitectura-v3.md`, `docs/tutorial-v3.md` y `docs/manual-usuario.md`.

**Serie v2.x** — GUI mejorada con modularización, SQLite v2:
- Rama: `v2/orchestrator` (merged a `master`, tag `v2.0.0`)
- Rama activa: `v2/gui-ux-stories` (en desarrollo, v2.1.0)
- No escribir en SQLite v1 desde la GUI v2
- Cierre esperado: PR a `master` + tag `v2.0.0` (ya hecho, ahora en mejoras GUI)

## Arquitectura y Módulos

### Estructura de Carpetas

```
config/          → batch.example.json, batch.json (entrada)
data/            → orchestrator.db (v1), orchestrator_gui.sqlite (v2)
logs/            → app.log global + YYYYMMDD_HHMMSS/username.log
reports/         → run_YYYYMMDD_HHMMSS.md
src/ig_orchestrator/
  main.py        → Punto de entrada CLI
  cli/main.py    → Entry CLI (main.py es shim)
  settings.py    → Lectura de .env
  input/         → Parser, importador, clasificador de URLs
  db/            → SQLite, schema, repositorios, adaptadores
  gui/           → Shell (app.py shim), editor, catálogo, batches, settings, draft
  orchestration/ → Orquestadores, política de reintentos
  telegram/      → Telethon, parser de respuestas del bot
  filesystem/    → Carpetas, watcher, clasificación, movimiento
  reports/       → Reporte Markdown
  library/       → Catálogo=disco: operaciones de disco con diario, escáner, papelera, ficha, auditoría, importación
  renaming/      → Renombrado integrado (port de sc2), índice como referencia
  staging/       → Almacén de procesadas y volcado a la biblioteca
  exchange/      → Intercambio entre instancias (publicar/traer/importar resultados)
```
(Detalle módulo a módulo en `docs/arquitectura-v3.md`.)

### Reglas de Arquitectura (de AGENTS.md)

- Usar Python 3.11+
- Mantener módulos pequeños y testeables
- Separar CLI, servicios de aplicación, repositorios, modelos, Telegram, filesystem y reportes
- SQLite es la fuente de verdad tras importar el JSON; el JSON solo carga datos iniciales
- La GUI futura debe poder escribir los mismos datos que el importador JSON
- Usar `pathlib.Path` para rutas
- No commitear `.env`, `*.session`, `*.session-journal`, bases SQLite reales

## Flujo de Ejecución

### Modo Dry-Run (validación sin efectos)

```bash
python -m ig_orchestrator --input config\batch.json --dry-run
```

- Lee `.env`
- Inicializa SQLite si falta
- Parsea y valida batch JSON
- Importa batch a SQLite
- Simula el procesamiento sin enviar a Telegram
- No mueve archivos
- No crea carpetas por defecto
- Genera run simulado en SQLite

### Modo Real (--run o sin --dry-run)

```bash
python -m ig_orchestrator --input config\batch.json --run
```

1. Carga `.env`, inicializa SQLite, valida JSON
2. Rechaza JSON si `batch_name` ya existe (sugerir `run_continue`)
3. Importa batch nuevo y registra usernames en `account_history`
4. Ordena en memoria: cuentas solo-stories primero; resto por volumen de URLs
5. Arranca Telethon con sesión `TELETHON_SESSION_NAME`
6. Procesa batch:
   - **Si `processing.stories_first` activo** (default): dos barridas
     - Barrida 1: todos los jobs `STORY` → cuentas mixtas → `INCOMPLETE`
     - Barrida 2: reels/posts/highlights → `COMPLETED`
   - **Si legado**: cuenta entera y siguiente
7. Envia URLs al bot, espera descargas, mueve archivos
8. Aplica reintentos FIFO para errores temporales
9. Genera reporte Markdown
10. Si `POST_PROCESS_ENABLED=true` y sin fallo infraestructura, ejecuta post-proceso

### Continuar Lote Interrumpido

```bash
python -m ig_orchestrator run_continue --batch-id 10
python -m ig_orchestrator run_continue --batch-name descargas_21_junio
```

Procesa desde SQLite sin reimportar JSON.

### GUI (v2.1.0)

```bash
python -m ig_orchestrator gui
```

Características:
- Catálogo de cuentas (favoritas, activas, inactivas, desactivadas)
- Editor de lote con soporte para cuentas nuevas y actualización
- Tabla de cuentas del lote actual con filtrado y reordenamiento
- Ejecución en segundo plano con progreso por item
- Logs en tiempo real con timestamp
- Renombrado manual integrado
- Almacenamiento de lotes como DRAFT, import/export portátil
- **Nuevas en v2.1**: Priority, Catalog paste, Stories inbox, Rename tone configs

## Persistencia y Trazabilidad

### Reglas de SQLite y Logs

- Cada invocación usa una sola carpeta `logs/YYYYMMDD_HHMMSS`, fijada al inicio
- Todas las cuentas, batches unidos y reintentos escriben en esa carpeta
- `input_batches.batch_name` es único y no se reutiliza
- `--run` siempre importa lote nuevo; `run_continue` o joins reutilizan existentes
- Tras importar lote real, respaldar JSON en `config/bkp` y limpiar URLs sin perder metadata
- `account_history` conserva usernames globales sin repetir entre lotes

### Cada URL Debe Guardar

- URL original
- Tipo clasificado (POST, REEL, STORY, HIGHLIGHTS, UNKNOWN)
- Origen (GENERATED_STORY o INPUT_URL)
- Estado (PENDING, SENT_TO_BOT, WAITING_DOWNLOAD, COMPLETED, FAILED_FINAL, etc.)
- Mensaje enviado al bot si aplica
- Error original si falla
- Tipo de error
- Contador de reintentos
- Archivos asociados
- Timestamps

## Reglas de Desarrollo (de AGENTS.md)

### Implementación

- Implementar una tarea cada vez
- No mezclar refactors grandes con la tarea
- No cambiar APIs existentes sin actualizar tests y documentación
- No introducir comportamiento futuro salvo que esté explícitamente pedido
- La IA debe implementar solo la tarea solicitada, salvo que sea imprescindible tocar soporte común

### Para Tareas GUI, Persistencia v2 o Tests

Leer primero:
1. `tasks/done/PLAN.md` (plan inicial, histórico)
2. `AGENTS.md`
3. `tasks/TareaX.md`
4. El código existente relacionado
5. `docs/modularizacion_v2.md` (GUI, persistencia v2, tests)
6. `MODULE.md` del paquete afectado (ej: `src/ig_orchestrator/gui/catalog/MODULE.md`)

**Nota**: No abrir `gui/app.py` salvo el shim; la clase vive en `gui/shell/app.py`

### Testing

- Cada tarea debe incluir tests cuando toque lógica nueva
- Preferir tests unitarios para parsers, clasificadores y políticas
- Usar SQLite temporal en tests de repositorios
- No depender de Telegram real en tests automatizados
- Suite mínima obligatoria: settings, batch_json_parser, batch_importer, url_classifier, retry_policy, bot_response_parser, file_watcher, file_classifier, folder_service, file_mover, repositorios SQLite, markdown_report_builder, orquestadores

### Cada petición del usuario = documentación completa + versión incremental

**Regla permanente (no hace falta que el usuario la repita):**

1. **Toda petición que cambie algo** (nueva función, mejora, ajuste de interfaz, corrección) debe cerrar con **toda la documentación actualizada en el mismo commit**: `CHANGELOG.md`, `docs/manual-usuario.md`, `docs/tutorial-v3.md` (sección del feat), `docs/arquitectura-v3.md` (si cambia arquitectura, modelo de datos, ajustes o limitaciones), `MODULE.md` del paquete, `README.md` si cambia lo visible, `AGENTS.md`/`Agents.md` y este `CLAUDE.md` si cambian reglas, y el `tasks/done/v3/feat-*.md` correspondiente con su «Resultado de la implementación». Si algún documento no requiere cambios, se revisa igualmente.
2. **Versionado incremental dentro de la serie activa** (hoy v3.x en `v3/integration`): una mejora o función nueva pedida se trata como un **feat incremental** de la serie, **sin abrir serie nueva**: sube el **minor** (`v3.13.0`, `v3.14.0`…) y se nombra `feat-<área>-<n>` con el siguiente número (áreas: `uc1` renombrado, `uc2` catálogo/carpetas, `uc3` sincronización, `uc4` instancias, `uc5` sin G:, `uc6` almacén; `problemN` para problemas puntuales). Una corrección de algo ya entregado sube el **patch** (`v3.13.1`). Se hace commit y tag `vX.Y.Z`.
3. Cada feat nuevo lleva su especificación breve en `tasks/done/v3/feat-<área>-<n>.md` (objetivo, qué se hizo, qué no) y una fila en `docs/plan-v3-features.md`.
4. Una serie nueva (v4) solo se abre si el usuario lo pide explícitamente.

### Changelog y Commits

**REGLA OBLIGATORIA**: Cada tarea que modifique código o archivos debe:
1. Actualizar `CHANGELOG.md` con:
   - Versión/tarea
   - Fecha
   - Archivos creados
   - Archivos modificados
   - Resumen de comportamiento agregado
   - Pruebas ejecutadas

2. Actualizar documentación afectada:
   - `CLAUDE.md`: si cambian reglas, arquitectura o guías de desarrollo
   - `MODULE.md` correspondiente: si cambian interfaces o responsabilidades de módulo
   - `tasks/Tarea_X.md` o directorio `tasks/done/`: registrar estado de las tareas
   - `README.md`: si cambia comportamiento visible al usuario o flujos operativos
   - `docs/manual-usuario.md`: **siempre** que se añada, cambie o elimine un menú, menú contextual, modal, botón o ajuste de la GUI (qué hace y qué abre); el manual debe estar siempre al día
   - `docs/tutorial-v3.md`: sección del feat si la serie v3 sigue en curso
   - `AGENTS.md` (`Agents.md`): si cambian las instrucciones base para IA o este proceso

   `CHANGELOG.md`, `docs/manual-usuario.md` y `AGENTS.md` se revisan en **cada** cambio, aunque solo sea para confirmar que no requieren edición.

3. Las tareas completadas se mueven de `tasks/` a `tasks/done/`

Formato de commit al terminar:

```bash
git add .
git commit -m "feat: implement tarea X ..."
git tag v1.X.0
```

Para arreglos:

```bash
git commit -m "fix: adjust tarea X ..."
git tag v1.X.1
```

## Configuración de Entorno

### `.env` Obligatorio

```env
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELETHON_SESSION_NAME=telegram_user_session
TELEGRAM_DOWNLOAD_BOT_USERNAME=@example_bot

TELEGRAM_DESKTOP_DOWNLOAD_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop
WORKING_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop
REPORTS_FOLDER=reports
SQLITE_DB_PATH=data\orchestrator.db

MAX_RETRIES=5
RETRY_BASE_SECONDS=90
RETRY_MAX_SECONDS=900
DOWNLOAD_WAIT_TIMEOUT_SECONDS=300
DOWNLOAD_STABLE_SECONDS=10
```

### `.env` Opcional

```env
POST_PROCESS_ENABLED=false
POST_PROCESS_COMMAND=D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat
SQLITE_GUI_DB_PATH=data\orchestrator_gui.sqlite
```

## Errores Definitivos (No Reintentar)

```
We're sorry, we couldn't find that.
Stories for {username} not found
We can't get stories from a private account (instagram limit)
```

El error de stories se detecta por patrón porque `{username}` cambia. En respuestas mixtas se conservan todos los videos y fotos; la presencia de un documento sin nombre no invalida fotos sin nombre.

## Errores Reintentables

```
The service is overloaded, please try again later.
geoblock_required
Media not found or unavailable   # solo 1 reintento (tope propio)
NO_BOT_RESPONSE                   # sin mensaje ni archivo antes del timeout
```

Política:
- Reintentos no son inmediatos mientras queden URLs nuevas
- Stories generadas se procesan primero
- URLs manuales se procesan después
- Cola FIFO de reintentos al final
- `Media not found or unavailable` solo 1 reintento, aunque `MAX_RETRIES > 1`
- Tras `MAX_RETRIES`, se marca `FAILED_FINAL`
- Backoff por defecto: 90, 180, 360, 720, 900 segundos

## Clasificación de URLs y Archivos

### URLs

- `/stories/highlights/...` → `HIGHLIGHTS`
- `/stories/{username}/` → `STORY`
- `/reel/...` → `REEL`
- `/p/...?...img_index=...` → `POST`
- `/p/...` sin `img_index` → inicialmente `REEL` → corregir a `POST` si solo imágenes

### Archivos

- Imagen: `.jpg`, `.jpeg`, `.png`, `.webp`
- Video: `.mp4`, `.mov`, `.mkv`, `.webm`
- Otro: `UNKNOWN`

**Corrección posterior**: Si URL `REEL` descarga solo imágenes, cambiar a `POST`.

## Rutas de Salida

### Logs

```
logs\app.log                          # Global
logs\YYYYMMDD_HHMMSS\username.log     # Por cuenta/run (una sola vez por ejecución)
```

### Descargas y Movimiento

```
TELEGRAM_DESKTOP_DOWNLOAD_FOLDER/    # Inicial (Telegram Desktop)
  ↓
WORKING_FOLDER\username\             # Raíz cuenta
  ├─ story\                           # STORY
  ├─ reels\                           # REEL con video
  └─ highlights\                      # HIGHLIGHTS
```

**Reglas**:
- `STORY` → `username\story\`
- `HIGHLIGHTS` → `username\highlights\`
- `REEL` con video → `username\reels\`
- `POST` con imagen → `username\` (raíz)
- Si destino existe: sufijo numérico `archivo_1.jpg`, `archivo_2.jpg`, etc.
- Al finalizar lote real: limpiar `telegram_media*` en raíz y `*_1.mp4` duplicados en `reels\`

### Almacén (v3.11)

Opcional: `app_settings['staging.root']`. Las carpetas renombradas pueden dejarse en `STAGING\<categoria>\<grupo>\<carpeta>` (`staged_accounts`) y volcarse a la biblioteca con `Lote > Pendiente de volcar a G:` (`staging/service.py`).

### Reportes

```
REPORTS_FOLDER\run_YYYYMMDD_HHMMSS.md
```

## Tareas Principales (Versioning)

Cada tarea genera un minor:

```
Tarea 1  ⟹ v1.1.0
Tarea 2  ⟹ v1.2.0
...
Tarea 23 ⟹ v1.23.0
Tarea GUI 1 ⟹ v1.25.0
...
Tarea v2 release ⟹ v2.0.0
Tarea v2.1 GUI UX ⟹ v2.1.0 (rama: v2/gui-ux-stories)
```

Arreglos incrementan patch: `v1.X.1`, `v1.X.2`, etc.

## No Implementar en v1.0.1

- Integración con el script de renombrado
- Limpieza de duplicados generados por el renombrador
- Movimiento final a `G:\4K Stogram`
- UI web o standalone

Estos siguen perteneciendo al script externo Manual Rename Files.

## Seguridad

**No commitear**:
- `.env`
- `*.session`, `*.session-journal`
- Bases SQLite reales en `data/`
- `api_hash`, códigos de login ni secretos en logs

## Ejecutar Tests

```bash
python -m pytest                  # Todos
python -m pytest -q              # Silencioso
python -m pytest tests/test_gui_services.py  # Específico
```

Desde VS Code: configuración `Tests: pytest`

## Inicializar SQLite

```bash
python -m ig_orchestrator init-db
python -m ig_orchestrator init-db --db-path data\orchestrator.db
```

## Referencias

- **docs/arquitectura-v3.md**: Guía técnica de la arquitectura v3 (empezar por aquí)
- **docs/README.md**: Índice de la documentación
- **AGENTS.md**: Instrucciones base para cualquier IA
- **tasks/done/PLAN.md**: Plan general inicial del proyecto (histórico, archivado)
- **CHANGELOG.md**: Historial de versiones y cambios
- **README.md**: Guía operativa completa
- **tasks/TareaX.md**: Descripción de cada tarea
- **docs/modularizacion_v2.md**: Arquitectura de modularización v2
- **docs/v3-status.md**, **docs/plan-v3-features.md**, **docs/feat-*.md**: Análisis, plan y propuestas de la serie v3 (integración de `sc1`/`sc2`, catálogo = disco, renombrado sin G:)
- **docs/tutorial-v3.md**: Tutorial de uso feat a feat (opciones, campos, ejemplos y cómo probar); se amplía en cada feat de v3
- **docs/manual-usuario.md**: Manual de uso por menú, menú contextual y modal (qué hace cada opción y qué abre); actualizar al añadir o cambiar opciones de GUI
- **MODULE.md** en cada paquete: Documentación interna del módulo
