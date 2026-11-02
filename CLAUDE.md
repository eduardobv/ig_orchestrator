# CLAUDE.md — ig_orchestrator

Este archivo se carga en **cada** conversación: solo lleva lo que aplica siempre. El detalle por área está en los `CLAUDE.md` de cada paquete (se cargan solos cuando se lee o edita un archivo de esa carpeta; ver «Mapa»). Mantén este archivo corto.

## Cómo trabajar en una sesión nueva

No te fíes de la memoria. Antes de responder o cambiar algo, consulta la documentación **por secciones** (los documentos grandes no se leen enteros: usa Grep por feat, versión o nombre de menú y lee solo ese tramo):

1. `docs/arquitectura-v3.md` — guía técnica: módulos, modelo de datos, ajustes, invariantes, limitaciones y §9 «dónde mirar cada cosa». Empieza aquí.
2. `docs/manual-usuario.md` — qué hace cada menú, menú contextual y modal de la GUI.
3. `docs/tutorial-v3.md` — cada feat con campos, ejemplos y cómo probarlo (≈100 KB: solo la sección del feat).
4. `CHANGELOG.md` (≈200 KB: Grep por versión) — qué cambió, cuándo, qué se probó.
5. `tasks/done/v3/feat-*.md` («Resultado de la implementación») y `docs/v3-status.md` — decisiones y qué no se hizo.
6. `MODULE.md` / `CLAUDE.md` del paquete y el código.

Reglas de sesión:
- Preguntas «¿cómo funciona / dónde está / por qué?»: responde desde esos documentos y verifica en código o base si hay duda; si el documento está desactualizado, corrígelo.
- Responde en español; si preguntan «dónde/cómo», con pasos cortos y no técnicos.
- Nada destructivo sobre `G:` real; prueba en copias e informa de lo que no se pudo probar.

## Propósito

Orquestador para preparar, trazar y procesar descargas manuales de Instagram mediante un bot de Telegram. El usuario escribe un lote de cuentas y URLs en JSON (o en la GUI); la app lo importa a SQLite, procesa las URLs en orden con Telethon, detecta los archivos que llegan a la carpeta de Telegram Desktop, los mueve a una estructura por cuenta y deja trazabilidad en base de datos, logs y reportes.

## Estado

- Versión actual **v4.23.x**, rama `v4/main` (serie v4 abierta; sigue las reglas de este documento con `v4.x`). La serie v3 se cerró en `v3.26.0` (rama `v3/integration`). Detalle y limitaciones: `docs/arquitectura-v3.md`.
- Desde v3 la app integra los procesos manuales (sincronización con el disco, renombrado, catálogo = disco, instancias, almacén/volcado, papelera). Python 3.11+.
- **SQLite v2 (`data/orchestrator_gui.sqlite`) es la única fuente de verdad en la GUI.** SQLite v1 (`data/orchestrator.sqlite`) es el rollback y lo usa la CLI; **la GUI nunca escribe en v1**.

## Comandos

```bash
python -m ig_orchestrator --input config\batch.json --dry-run   # valida e importa, simula, sin Telegram ni mover archivos
python -m ig_orchestrator --input config\batch.json --run       # flujo real (importa un batch_name nuevo)
python -m ig_orchestrator run_continue --batch-id 10            # retoma desde SQLite (o --batch-name X)
python -m ig_orchestrator gui                                   # GUI de escritorio
```

Cada `batch_name` se importa una sola vez; una ejecución interrumpida se retoma desde SQLite. Flujo paso a paso, logs y reportes: `src/ig_orchestrator/cli/CLAUDE.md`.

## Reglas de arquitectura

- Módulos pequeños y testeables; separar CLI, servicios de aplicación, repositorios, modelos, Telegram, filesystem y reportes. `pathlib.Path` para rutas.
- SQLite es la fuente de verdad tras importar; el JSON solo carga datos iniciales y la GUI debe poder escribir lo mismo que el importador.
- Toda operación sobre carpetas de la biblioteca pasa por `FsOperationService` (plan → vista previa → ejecutar, con diario y deshacer); nunca se sobrescribe (choque = conflicto o sufijo). Invariantes completos: `docs/arquitectura-v3.md` §4.
- `gui/app.py` es solo un shim; la clase vive en `gui/shell/app.py`. No introducir event-bus.
- Implementar una tarea cada vez; sin refactors grandes mezclados; no cambiar APIs sin actualizar tests y documentación; no añadir comportamiento futuro no pedido.
- Si un feat necesita un paso manual en las instancias, añade entrada a `inst_sync/CAMBIOS.md` (un cambio de datos va en `inst_sync/sql/NNN_*.sql`): ver `inst_sync/CLAUDE.md`.

## Mapa: qué CLAUDE.md se carga al tocar cada área

| Área | Contenido |
|---|---|
| `src/ig_orchestrator/cli/` | Flujo de ejecución (dry-run, real, continuar), logs, reportes |
| `src/ig_orchestrator/orchestration/` | Orden del lote, reintentos, errores definitivos/reintentables, ajustes `run.*` |
| `src/ig_orchestrator/http_fallback/` | Descarga HTTP de posts/reels sin respuesta del bot, bot caído, sesión |
| `src/ig_orchestrator/telegram/` | Conversación con el bot, fin de la espera, descargas, reels grandes, stories, bot mudo |
| `src/ig_orchestrator/input/` | Clasificación de URLs, importación |
| `src/ig_orchestrator/filesystem/` | Clasificación de archivos, rutas de salida, limpieza |
| `src/ig_orchestrator/db/` | SQLite v1/v2, trazabilidad por URL, logs |
| `src/ig_orchestrator/telemetry/` | Métricas por intento |
| `src/ig_orchestrator/account_status/` | Estado de cuentas |
| `src/ig_orchestrator/renaming/` | Renombrado, Renew |
| `src/ig_orchestrator/staging/`, `library/`, `exchange/` | Almacén/volcado, biblioteca, intercambio entre instancias |
| `src/ig_orchestrator/gui/` (+ subpaquetes) | Reglas de GUI, manual, reinicio de lote, informe de ejecución |
| `inst_sync/` | Replicar el código en otra instancia |

Los subpaquetes pequeños de `gui/` y `db/` solo tienen `MODULE.md`; el `CLAUDE.md` de su carpeta padre lo cubre.

## Pruebas

- Cada tarea con lógica nueva lleva tests; prefiere unitarios para parsers, clasificadores y políticas. SQLite temporal en tests de repositorios. **Nunca Telegram real en tests.**
- Suite mínima: settings, batch_json_parser, batch_importer, url_classifier, retry_policy, bot_response_parser, file_watcher, file_classifier, folder_service, file_mover, repositorios SQLite, markdown_report_builder, orquestadores. Se ejecuta con `python -m pytest -q`.

## Tipo de petición → qué hacer (sin que el usuario lo tenga que decir)

Clasifica cada petición al empezar y di la clasificación en una línea («Lo trato como fix → patch»). Lo que el usuario diga explícitamente («trátalo como feat», «sin commit», «versión 4.20.0») manda sobre esta tabla.

| Tipo | Se reconoce por | Toca `src/` | Commit y tag | Versión |
|---|---|---|---|---|
| **consulta** | «¿cómo / dónde / por qué…?» | No | No | — |
| **análisis** | «analiza / revisa / compara / investiga / propón» y entrega un informe o recomendación | No | No | — |
| **spike** | «¿es viable…? / prueba si…»: explorar antes de decidir | No (código desechable en scratchpad o `tasks/spikes/`) | No | — |
| **poc** | «prototipo / demo / poc»: probar que algo funciona | No (aislado en scratchpad o `tasks/spikes/<tema>/`) | No | — |
| **feat** | añade **capacidad nueva** visible: menú, botón, ajuste, flujo o comportamiento nuevo | Sí, con tests | **Sí** (commit + tag al terminar) | **minor** (`v4.19.0`) |
| **fix** | algo ya entregado falla o hay que ajustarlo: error, texto, layout, umbral, retoque pequeño | Sí, con test de regresión | **Sí** (commit + tag) | **patch** (`v4.18.2`) |
| **docs / chore / refactor / test** | solo documentación, mantenimiento o reorganización sin cambio de comportamiento | Según el caso | **No**, salvo que se pida | — (sin versión ni tag) |

**Prefijo del mensaje de commit** (convención del historial; resumen en inglés, imperativo, corto): `feat:` · `fix:` · `docs:` · `chore:` (mantenimiento, cierre de serie) · `refactor:` · `test:`. Elígelo por el tipo de la tabla, no por el archivo tocado: un cambio de solo documentación es `docs:` aunque toque `CLAUDE.md`; si además cambia comportamiento, manda `feat:`/`fix:`. Solo `feat:` y `fix:` llevan versión (formato exacto en la skill `cerrar-cambio`). Un commit = un tipo: no mezcles `docs:` con `feat:` en el mismo commit salvo la documentación propia del feat.

Reglas de desempate:
- Mezcla de tipos (p. ej. «arregla X y añade Y») → manda el mayor: feat > fix.
- feat o fix: ¿añade algo que el usuario antes no podía hacer? → feat; ¿corrige o retoca lo que ya existía? → fix. Una versión mayor (`v5.0.0`) solo si el usuario la pide. Si el usuario indica la versión, se usa esa.
- Si la duda es entre un tipo con commit y uno sin commit → **sin commit** y se avisa. Un commit se puede pedir luego; deshacerlo es más molesto.
- Consulta, análisis, spike y poc **nunca** modifican `src/`, ni suben versión, ni crean tag. Si encuentran un fallo, lo reportan y proponen el fix; no lo aplican sin que se pida.
- Spike: deja la conclusión en `tasks/spikes/spike_<tema>.md`. Poc: el prototipo no entra en el producto. Si el resultado es bueno, se **ofrece** convertirlo en feat; no se hace solo.
- Nunca `push`, merge ni cambio de rama sin petición expresa. «Sin commit», «déjame verlo» o «no commitees» anulan el commit automático: se deja todo en el árbol de trabajo y se espera la orden.

## Cerrar un feat o fix

Al terminar un feat o fix: código + tests (`python -m pytest -q`) + documentación completa en el **mismo** commit + commit + tag. El checklist exacto (archivos de versión, documentos, formato de commit) está en la skill `cerrar-cambio` (`.claude/skills/cerrar-cambio/SKILL.md`); cárgala al empezar a cerrar. Resumen de documentación (revisar siempre, aunque no cambie): `CHANGELOG.md`, `docs/manual-usuario.md` (siempre que cambie un menú, modal, botón o ajuste de la GUI), `docs/tutorial-v3.md`, `docs/arquitectura-v3.md`, `MODULE.md` / `CLAUDE.md` del paquete, `README.md` si cambia lo visible. `AGENTS.md`/`Agents.md` los mantiene el usuario (no editar salvo petición).

Nombres: cada feat es `feat-<área>-<n>` (áreas: `uc1` renombrado, `uc2` catálogo/carpetas, `uc3` sincronización, `uc4` instancias, `uc5` sin G:, `uc6` almacén, `run` ejecución, `gui` interfaz; `problemN` para puntuales), con `n` = siguiente libre del área. Los fix no crean feat nuevo: anotan el cambio en el `feat-*.md` del feat que corrigen.

## Seguridad

No commitear `.env`, `*.session`, `*.session-journal`, bases SQLite reales de `data/`, `api_hash`, códigos de login ni secretos en logs.
