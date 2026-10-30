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

### Estado Actual (v4.17.0; serie v3 cerrada en v3.26.0)

- Serie v3 cerrada en `v3.26.0` (rama `v3/integration`, PR a `master`). Rama de trabajo nueva: `v4/main` (serie v4; hasta que el usuario defina su versionado, seguir las reglas de este documento con `v4.x`). Detalle y limitaciones: `docs/arquitectura-v3.md`.
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

### Reglas de Arquitectura (de AGENTS.md)

- Usar Python 3.11+
- Renew (v4.17.0): casilla del editor (`AccountDraft.is_renew`) que pide solo la fecha del primer post; el renombrado (`renaming/planner.py: process_renew_tree`, estado `RENEW`) une los ficheros solo-id de `G:` con los descargados y los renombra como cuenta nueva (los de `G:` en sitio); ignora cualquier otro nombre; necesita `G:` y el Owner Id del catálogo; sin columna nueva (se infiere de `rename_start_init_date`)
- Pausa entre URLs y bot sin respuesta (v4.16.0): `run.bot.between_urls_seconds` (2 s) espacia los envíos; tras una URL sin respuesta, la siguiente espera `run.bot.stall_probe_delay_seconds` (10 s) y, si tampoco responde, modo espera sin enviar más (barra de estado de la GUI, marcador `[GUI_BOT_STATUS]`) hasta que el bot conteste y se recogen las dos respuestas (`BotConversationResult.late_results`, atribución por `reply_to`); `run.bot.stall_enabled` lo desactiva. Código en `telegram/bot_conversation_service.py` y `orchestration/url_job_processor.py`
- Descarga de Telegram (v4.4.1): una descarga por `(nombre, tamaño)`, miniaturas solo como respaldo, paralelo (`TELEGRAM_PARALLEL_DOWNLOADS`), carpeta propia opcional (`TELEGRAM_DOWNLOAD_TEMP_FOLDER`), vigilante off por defecto (`TELEGRAM_WATCHER_FALLBACK`)
- Reels > 50 MB (v4.5.0): el bot responde `error_file_too_large_link` + URL; se descarga directo como `<media_id>.mp4` (`telegram/large_file.py`); fallo → `FILE_TOO_LARGE_DOWNLOAD_FAILED`, reintentable
- Versionado (desde v4.13.1): feat nuevo = minor (`v4.14.0`); ajuste pequeño de algo ya entregado = patch (`v4.13.1`), con commit y tag igualmente.
- Estado de cuentas, reutilización (v4.14.0): un análisis nuevo copia las respuestas de otros análisis de las últimas `accountcheck.reuse_hours` (48 h, *Configuración > Catálogo*) con `source_run_id` y no las consulta; casilla *Re-analizar…* para forzar
- Estado de cuentas (v4.13.2; modal también desde *Catálogo > Revisar análisis de estado…*; el disco nunca se toca en el hilo de Tk): clic derecho en carpeta > *Comprobar estado de las cuentas…* (`account_status/` + `gui/library/account_status_dialog.py`); `profile_id` en `instagram.com/<cuenta>/`; espera `run.accountcheck.interval_seconds`; para solo en el primer 429; análisis guardados en `account_check_runs/results`; mover con `plan_move_accounts`
- Stories (v4.11.0): el bot responde con miniaturas y, si hay 1-2 items, con un 2.º mensaje con los adjuntos; con 3+ solo miniaturas. En `STORY` solo las miniaturas sin nombre cuentan como items y se esperan los adjuntos (`run.bot.story_attachment_wait_seconds`). Reinicio de lote: `gui/batches/restart.py` (Lote > Reiniciar desde cero… y botón/clic derecho **Reiniciar…** en el modal de lotes, v4.12.0, cualquier estado salvo GUARDADO)
- Informe de ejecución (v4.10.0): `telemetry/report.py` + modal `gui/batches/execution_report.py` (Lote > Informe de ejecución…, clic derecho en el modal de lotes); botón de purga en *Ejecución*
- Reintentos (v4.9.0): cola global al final del lote (`run.retry.global_queue`, ordenada por `next_retry_at`); `NO_BOT_RESPONSE` máx. 3 (`run.retry.no_response_max`)
- Fin de la espera (v4.8.0): `EXPECTED_COUNT` (nombres únicos ≥ items anunciados, descripción, o silencio breve 2,5 s) en vez de 10 s de silencio; primera respuesta 30 s (reel/post/story/error) o 75 s (carrusel, `/p/`, highlights), luego plazo de 120 s renovado por mensaje. Se ignoran mensajes del bot con id < el enviado
- Ajustes de ejecución (v4.7.0): `run.*` en `app_settings`, editables en *Configuración > Ejecución*; precedencia GUI > `.env` > defecto (`orchestration/run_settings.py`). Una opción nueva de la descarga debe añadirse a `RUN_SETTING_SPECS` y a los locales
- Telemetría (v4.6.0): `telemetry/` mide cada intento en la base de la GUI (`url_job_attempts`, `bot_message_events`, `run_wait_events`); solo observa, nunca debe romper el lote; no guarda textos de descripciones. Consultar esas tablas para analizar rendimiento
- Dependencia `cryptg` obligatoria en el rendimiento de Telegram (v4.4.0); las respuestas del bot llegan por eventos, con sondeo de respaldo
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
Media not found or unavailable   # máx. 3 reintentos (tope propio) y solo si el post sigue existiendo
NO_BOT_RESPONSE                   # sin mensaje ni archivo antes del timeout
```

Política:
- Reintentos no son inmediatos mientras queden URLs nuevas
- Stories generadas se procesan primero
- URLs manuales se procesan después
- Cola FIFO de reintentos al final
- `Media not found or unavailable`: máx. 3 reintentos aunque `MAX_RETRIES > 1`. Antes de reintentar se consulta la página pública del post en Instagram (sin login): si es la página de error (`PolarisErrorRoot` + `httpErrorPage`) el post ya no existe → `FAILED_FINAL` con tipo `MEDIA_REMOVED`, sin reintentos; si la página es normal (`og:title`) o no se puede saber (muro de login, 429, red caída), se reintenta. Solo posts/reels (no stories/highlights). Código: `orchestration/post_availability.py`, usado por `UrlJobProcessor`
- Tras `MAX_RETRIES`, se marca `FAILED_FINAL`
- Backoff por defecto: 90, 180, 360, 720, 900 segundos
- Las stories (`STORY`) tienen como máximo **2 reintentos** (si `MAX_RETRIES` es menor, manda el menor)

### Orden de procesamiento del lote (v4.3.0, `processing.stories_first`)

Orden con `processing.stories_first` (v4.3.0):
1. **Barrida de stories:** todas las cuentas con stories pendientes; primero las que tienen *prioridad* (rango 1, 2…), después el orden en que se añadieron al lote. Las stories tienen como máximo **2 reintentos**.
2. **Barrida de posts/reels/highlights:** de la cuenta con menos URLs pendientes a la que más; empate → más reels; empate → menos posts; empate → cuenta ya existente antes que nueva; empate → orden del lote.

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

## Seguridad

**No commitear**:
- `.env`
- `*.session`, `*.session-journal`
- Bases SQLite reales en `data/`
- `api_hash`, códigos de login ni secretos en logs

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
