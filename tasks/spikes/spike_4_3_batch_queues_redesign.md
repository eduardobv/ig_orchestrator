# Spike 4.3: Rediseño de Sistema de Colas de Batches

## Objetivo
Analizar si el sistema actual de colas de batches (`join_batches`) es viable y útil, o si requiere un rediseño completo con su propio modal, modelo de datos, y flujo de ejecución separado del batch individual.

## Contexto Actual

**Estado (v2.1.0):**
- Tabla `batch_joins` permite agrupar múltiples batches
- Ejecutar `run --batch-join-id 5` procesa batches secuencialmente
- UI: checkbox "Join with others" en batches_view
- Problema: confuso, acoplado a batches, no está claro qué pasa

**Estructura actual:**
```
batch_joins (join_id, join_name, created_at, status)
  └─ url_ids referenciadas de múltiples batches
     (sin tabla explícita, solo flag en batch)
```

**Flujo actual:**
```
User: Crea batch A, batch B, batch C
User: Check "Join" en A y B
System: Join AB en batch_joins.5
User: Execute join → procesa A, luego B secuencialmente
```

## Análisis de Viabilidad

### 1. Problemas Identificados con Diseño Actual

| Problema | Impacto | Evidencia |
|----------|---------|-----------|
| **Confuso:** "Join" es verb ambiguo | UX | Usuario no sabe si es temporal o permanente |
| **Acoplado:** checkbox en batches | Arquitectura | Batch no debería conocer joins |
| **Ejecuta linealmente:** A→B→C sin pausa | Flujo | No hay forma de pausar entre batches |
| **Post-process:** "Acoplado a lote" | Funcionalidad | Renombrado MRF solo funciona después de todo |
| **BD:** No hay tabla explícita `batch_queue_items` | Persistencia | Auditoría débil, no sabe orden de ejecución |
| **Sin prioridades:** Ejecuta en orden de creación | Control | Usuario no puede reordenar |
| **Sin cancelación:** Cancel cancela TODO | Control | Imposible parar en batch N de 5 |

### 2. ¿Es Viable el Sistema Actual?

**Técnicamente:** ✅ SÍ, funciona

**Pero:**
- ❌ No es intuitivo (usuarios preguntan qué significa)
- ❌ No escala (muchos batches = confuso)
- ❌ No soporta cambios en runtime (agregar batch a cola activa)
- ❌ Post-process forzado al final de TODO (problema para renombrado)

**Veredicto: Viable técnicamente, pero POBRE UX**

### 3. Opciones de Rediseño

**Opción A: Descartar joins, mantener solo batches individuales**
- ✅ Simplifica UI
- ✅ Usuario ejecuta batch individual, luego siguiente manual
- ❌ No hay automatización de múltiples batches
- ❌ No hay coordección con post-process
- ⚠️ Ideal si solo quieren procesar 1-2 batches

**Opción B: Rediseñar como "Execution Queue" independiente**
- ✅ Interfaz clara: queue de batches (como playlist)
- ✅ Botones: add batch, remove, reorder, preview
- ✅ Post-process entre batches configurable
- ✅ Pause en cualquier batch, resume desde mismo punto
- ✅ Cada batch es entidad independiente (desacoplado)
- ⚠️ Nueva tabla `execution_queues` + items
- ⚠️ Cambios en signature de orchestrator
- Complejidad: MEDIA

**Opción C: Híbrido - Queue + Templates**
- ✅ Guardar colas como templates reutilizables
- ✅ "Quick queue" vs "Named queue"
- ❌ Sobre-engineered
- ⚠️ Complejidad: ALTA

**Veredicto: Opción B es ideal balance**

### 4. Diseño de Opción B: Execution Queues

**Nueva tabla:**
```sql
CREATE TABLE execution_queues (
  id INTEGER PRIMARY KEY,
  queue_name TEXT UNIQUE NOT NULL,
  created_at TIMESTAMP,
  status TEXT,  -- DRAFT, ACTIVE, PAUSED, COMPLETED, FAILED
  post_process_config TEXT  -- JSON: {enabled: bool, command: str, run_after_each: bool, run_after_all: bool}
);

CREATE TABLE queue_items (
  id INTEGER PRIMARY KEY,
  queue_id INTEGER,
  batch_id INTEGER,
  position INTEGER,  -- orden en queue
  status TEXT,       -- PENDING, EXECUTING, COMPLETED, SKIPPED, FAILED
  added_at TIMESTAMP,
  started_at TIMESTAMP NULL,
  completed_at TIMESTAMP NULL,
  error TEXT NULL
);
```

**Modelo:**
```
ExecutionQueue (id, name, status)
  ├─ QueueItem 1: Batch A (position=1, status=COMPLETED)
  ├─ QueueItem 2: Batch B (position=2, status=EXECUTING)
  ├─ QueueItem 3: Batch C (position=3, status=PENDING)
  └─ PostProcessConfig (enabled=true, run_after_each=false, run_after_all=true)
```

**UI:**
```
┌─ Execution Queues ─────────────────────┐
├─────────────────────────────────────────┤
│ Queue: "Descargas Octubre"              │ ← dropdown de queues
│ Status: PAUSED                          │
├─────────────────────────────────────────┤
│ [1] Batch A (10 URLs)      ✓ COMPLETE  │
│ [2] Batch B (5 URLs)       ⊙ EXECUTING │
│ [3] Batch C (8 URLs)       ○ PENDING   │
│ [4] + Add Batch...                     │
├─────────────────────────────────────────┤
│ [↑] [↓] [Delete] [Reorder]             │  ← drag to reorder
├─────────────────────────────────────────┤
│ Pause Between Batches: [ON]             │
│ Run Post-Process After Each: [OFF]      │
│ Run Post-Process After All: [ON]        │
│ Command: D:\...MRF_auto.bat             │
├─────────────────────────────────────────┤
│ [Play] [Pause] [Cancel] [Save Queue]    │
└─────────────────────────────────────────┘
```

### 5. Flujo de Ejecución Nuevo

```
User: Crea Queue "Oct Downloads"
User: Agrega Batch A, B, C a queue
User: Configura: pause between=true, post-process after each=false
User: Click Play
  → Ejecuta Batch A
  → PAUSA (usuario click resume)
  → Ejecuta Batch B
  → Ejecuta Batch C
  → Run post-process MRF_auto.bat
  → Queue = COMPLETED
```

### 6. Cambios Arquitectónicos

**En BD:**
- Nueva tabla `execution_queues` + `queue_items`
- Remover flag `join_id` de batches (desacoplar)
- Migración de datos: queues existentes → nuevas tablas

**En Orchestrator:**
- New: `QueueRunner` que coordina múltiples batches
- Each batch sigue siendo `Orchestrator.run(batch_id)`
- Entre batches: sleep, post-process, log

**En GUI:**
- New: `ExecutionQueuesView` (tab nueva)
- New: `QueueModal` (crear/editar queues)
- Modify: `BatchesView` (remover join checkbox)
- Modify: `toolbar` (agregar "Queues" tab)

**Compatibilidad:**
- ✅ Batch individual sigue funcionando
- ✅ Colas son optional
- ✅ Post-process ahora configurable

### 7. Riesgos y Mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Migración de joins existentes a queues | Script de migración bidireccional |
| Queue execution muy lenta (espera user) | Timeout configurável, opción auto-resume |
| Reordenar durante ejecución | Lock BD temporalmente |
| Post-process falla, siguiente batch no ejecuta | Opción skip-on-error configurable |

## Conclusión

✅ **VIABLE Y RECOMENDADO** - Opción B (Execution Queues) es mejor que acoplamiento actual.

**Razones:**
- Desacopla batches de colas
- Interfaz intuitiva y controlable
- Soporta post-process flexible
- Escalable a muchos batches
- BD bien definida

**NO recomendado:** Mantener joins actuales (confuso)

**Complejidad: MEDIA-ALTA**
- ~15-20 horas
- Nueva tabla + migración
- Nuevo tab en GUI
- Testing de reordenamiento y pause/resume en queue

## Recomendación

**Fase 1:** Implementar tablas + backend `QueueRunner`
**Fase 2:** Implementar UI `ExecutionQueuesView` + modal
**Fase 3:** Migración de joins existentes
**Fase 4:** Deprecar y remover `batch_joins`
**Testing:** Ejecutar múltiples batches con pause, reorder, post-process

## Prompt para Implementación

```
Rediseñar colas de batches como "Execution Queues" independientes:

1. Migración BD:
   - Crear tabla execution_queues (id, queue_name, status, post_process_config)
   - Crear tabla queue_items (id, queue_id, batch_id, position, status, timestamps)
   - Script para migrar joins existentes a queues
   - Remover flag join_id de batches (en v2.1)

2. Crear `src/ig_orchestrator/orchestration/queue_runner.py`
   - Clase QueueRunner(queue_id)
   - Método run() que:
     - Itera queue_items en orden
     - Llama orchestrator.run(batch_id) para cada
     - Entre batches: aplica post-process si configured
     - Respeta pause_between_batches
     - Maneja cancel/pause de queue completa
   - Logging por queue (queue_YYYYMMDD_HHMMSS.log)

3. Crear `src/ig_orchestrator/gui/execution_queues_view.py`
   - Tab nueva en Notebook
   - Tabla de queues con dropdown selector
   - Queue details: lista items con status/reorder
   - Botones: play, pause, cancel, add batch, remove, save queue
   - Post-process config editor (checkboxes + input para command)
   - Drag-to-reorder items (si posible en Tkinter, o botones ↑↓)

4. Crear `src/ig_orchestrator/gui/queue_modal.py`
   - Modal para crear queue nueva
   - Input: queue_name
   - Add batches button (abre selector)
   - Save / Cancel

5. Modificar `BatchesView`
   - Remover checkbox "Join with others"
   - Agregar botón "Add to Queue..." que abre selector
   - Desacoplar batches de joins

6. Actualizar CLI
   - Deprecar --batch-join-id
   - Agregar --queue-id para ejecutar queue
   - Ejemplo: `python -m ig_orchestrator run --queue-id 5`

7. Tests:
   - test_queue_executes_batches_sequentially()
   - test_queue_pause_between_batches()
   - test_queue_post_process_after_each()
   - test_queue_reorder_items()
   - test_queue_cancel_current()
   - test_migration_joins_to_queues()

8. Documentación:
   - Actualizar CHANGELOG.md
   - Agregar guía de queues en README.md
   - Deprecar joins en CLAUDE.md
   - Actualizar flujo en docs/
```
