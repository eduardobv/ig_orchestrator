# Spike 4.1: Ejecutar Batch en Background sin Bloquear GUI

## Objetivo
Analizar la viabilidad de ejecutar un batch en una modal separada o pestaña nueva, permitiendo que el usuario continúe editando/creando nuevos batches en la GUI principal mientras uno se ejecuta.

## Contexto Actual

**Estado:**
- Ejecución de batch está acoplada al thread principal (GUI)
- `shell/app.py` → `batches_view` → `execute_batch()` bloquea la interfaz
- Toda interacción se congela hasta que termina el batch o se pausa
- No hay aislamiento de threads de ejecución vs. GUI

**Flujo actual:**
```
Usuario click "Execute" 
  → BatchesView.execute_batch() 
  → Orchestrator.run() (BLOQUEA main thread)
  → GUI no responde
```

## Análisis de Viabilidad

### 1. Threading / Async
**Opción A: Threading (separar en hilo)**
- ✅ Python threading permite ejecutar orchestration en `Thread(daemon=False)`
- ✅ Telethon soporta ejecutación en background
- ✅ Logs y SQLite pueden escribirse desde hilo separado (sqlite3 es thread-safe con modo WAL)
- ⚠️ Requiere sincronización: estado de batch, pausa, cancelación
- ⚠️ Necesita comunicación thread-safe (Queue, Event)

**Opción B: Async/await**
- ✅ Más limpio que threading
- ❌ Telethon en Haiku no es 100% async-friendly (usa `asyncio.run()` bajo el capó)
- ❌ Tkinter no tiene integración nativa con asyncio
- ❌ Requerirá refactor importante de `orchestrator.run()`

**Veredicto: Threading es viable y menos invasivo**

### 2. Modal vs. Pestaña Nueva

**Modal en ventana separada (Toplevel Tkinter):**
- ✅ Interfaz limpia, enfoque en ejecución
- ✅ Permite ver logs en tiempo real
- ✅ Botones pausa/resume/cancel en la modal
- ✅ Usuario puede minimizar y volver a GUI principal
- ✅ No requiere redesign de tabs existentes

**Pestaña nueva (Notebook Tkinter):**
- ✅ Menos intrusivo que modal
- ✅ Usuario ve progreso sin cambiar ventana
- ❌ Pestaña "activa" oculta la anterior
- ❌ Menos enfoque visual en la ejecución

**Veredicto: Modal separada es mejor opción (UX)**

### 3. Cambios Arquitectónicos Necesarios

**En `orchestrator.run()`:**
- Refactor para aceptar `stop_event`, `pause_event` como parámetros
- Callbacks para actualizar UI (progreso, logs)
- Manejo de interrupciones (pause/resume/cancel) sin corruption de BD

**En `BatchesView`:**
- Quitar lógica de orchestration del thread principal
- Crear `ExecutionThread` que maneja ejecución y comunicación con UI

**New Module: `gui/execution_modal.py`**
```
ExecutionModal
  ├─ show(batch_id, orchestrator_config)
  ├─ update_progress(account, url_count)
  ├─ append_log(text)
  ├─ pause() → event.set()
  ├─ resume() → event.clear()
  ├─ cancel() → stop_event.set()
  └─ sync with ExecutionThread via Queue
```

### 4. Persistencia (SQLite v2)

**Sin cambios:**
- `input_batches`, `urls`, `account_history` ya soportan writes concurrentes
- WAL mode en sqlite3 permite lectura mientras se escribe
- Versioning en v2.0.0 ya maneja múltiples runs

**Con cambios:**
- Nueva tabla opcional `batch_executions` para registrar sesiones paralelas (para audit)
- Transacciones atómicas por URL

### 5. Riesgos Identificados

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| Race condition en SQLite | Media | Usar `thread_factory` de sqlite3, WAL habilitado |
| Telethon state corruption | Alta | Sincronizar acceso a `TelegramClient`, un solo thread activo |
| Logs entrelazados | Baja | Usar Queue thread-safe para logging |
| Usuario ejecuta 2 batches con mismo bot | Media | Validar 1 ejecución activa por bot (check en SQLite) |
| Modal cerrada abruptamente | Media | Graceful shutdown en destructor |

### 6. Cambios en Base de Datos

**Tablas existentes:** Sin cambios, solo WAL mode asegurado

**Nueva tabla (opcional):**
```sql
CREATE TABLE execution_sessions (
  id INTEGER PRIMARY KEY,
  batch_id INTEGER,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  thread_id TEXT,
  status TEXT  -- RUNNING, PAUSED, COMPLETED, CANCELLED
);
```

## Conclusión

✅ **VIABLE** - Técnicamente es posible con threading, sin necesidad de refactor destructivo.

**Razón:**
- Python threading + SQLite WAL = seguro
- Modal Tkinter es patrón probado
- Cambios localizados en `batches_view` y orquestador
- No afecta flujo crítico (importación, clasificación)

**Complejidad: MEDIA**
- ~8-10 horas de implementación
- Testing de concurrencia (pausas, cancelaciones)
- Documentación de nuevos eventos de threads

## Recomendación

1. Implementar `ExecutionThread` que envuelve `orchestrator.run()`
2. Crear `ExecutionModal` con logs, progreso, botones pausa/cancel
3. Usar `threading.Event` para stop/pause
4. Asegurar SQLite con WAL mode (ya debe estarlo en v2)
5. Tests: verifica pause/resume, cancel limpio, sin corruption BD

## Prompt para Implementación

```
Implementar ejecución de batch en background sin bloquear GUI:

1. Crear nuevo módulo `src/ig_orchestrator/gui/execution_modal.py`
   - Clase ExecutionModal(tk.Toplevel) con:
     - Frame de logs con scrollbar
     - ProgressBar por cuenta
     - Botones: Pause, Resume, Cancel
     - Métodos: update_progress(), append_log(), show()
   - Usar Queue(thread_safe=True) para comunicación desde thread worker

2. Crear `src/ig_orchestrator/gui/execution_thread.py`
   - Clase ExecutionThread(Thread) que:
     - Toma batch_id, orchestrator_config, GUI_queue
     - Llama a orchestrator.run() con stop_event, pause_event
     - Captura logs y progreso
     - Envia updates a GUI_queue
     - Maneja interrupciones limpiamente (finally block para cleanup)

3. Modificar `orchestrator.run()` en `src/ig_orchestrator/orchestration/main.py`
   - Agregar parámetros: stop_event=None, pause_event=None, progress_callback=None
   - En loops, verificar stop_event.is_set() y pause_event.wait()
   - Llamar progress_callback(account, processed, total)
   - Mantener atomicidad de transacciones SQLite

4. Modificar `BatchesView.execute_batch()`
   - Crear ExecutionThread
   - Mostrar ExecutionModal
   - Conectar Queue de thread con update_progress/append_log de modal
   - No bloquear main thread

5. Asegurar SQLite:
   - Verificar WAL mode en init-db
   - Transacciones por URL con rollback en error

6. Tests:
   - test_execution_thread_pause_resume()
   - test_execution_thread_cancel()
   - test_batch_state_consistency_with_concurrent_execution()
   - test_logs_not_corrupted_during_parallel_batch()

Documentar cambios en CHANGELOG.md y actualizar spike.
```
