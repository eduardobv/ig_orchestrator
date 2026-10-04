# Spike 4.2: Agregar Cuentas a Batch en Ejecución

## Objetivo
Analizar la viabilidad de agregar nuevas cuentas (o importar cuentas de otros batches) a un batch que ya está siendo procesado, sin interrumpir la ejecución en progreso.

## Contexto Actual

**Estado:**
- Batch se importa de JSON una sola vez (regla: `batch_name` es único)
- URLs se procesa en orden de memoria (ordenadas por tipo y volumen)
- No hay mecánica para inyectar URLs dinámicamente
- Orchestrator toma snapshot de URLs al inicio de `run()`
- Si adds URLs, deben quedar pending en BD pero no se procesan en ejecución actual

**Tablas actuales:**
```
input_batches (batch_id, batch_name, status)
  ├─ urls (url_id, batch_id, url, status, account_id)
  └─ account_history (account_id, username, status)
```

## Análisis de Viabilidad

### 1. Flujo de Ejecución Actual

```
run() {
  urls_queue = fetch_urls_from_db(batch_id)  ← SNAPSHOT aquí
  for account in order_accounts(urls_queue):
    for url in urls_queue[account]:
      send_to_bot(url)
      wait_download()
      process_file()
}
```

**Problema:** `urls_queue` es inmutable en memoria. URLs nuevas en BD no se ven.

### 2. Opciones Técnicas

**Opción A: Polling dinámico (sin refactor)**
- ✅ Orchestrator revisa BD cada N segundos
- ✅ Detecta nuevas URLs con status PENDING
- ✅ Las agrega a cola de procesamiento in-memory
- ❌ Race condition si URL se procesa justo después de detectarse
- ❌ Overhead de queries constantemente
- ⚠️ Débil para lotes grandes (100+ URLs)

**Opción B: Event-driven (refactor medio)**
- ✅ GUI envia evento cuando agrega URLs
- ✅ Orchestrator mantiene cola thread-safe (Queue)
- ✅ Nuevo detector de URLs inyecta en tiempo real
- ✅ Limpio y escalable
- ⚠️ Requiere cambiar signature de `run()`
- ⚠️ Requiere comunicación thread <-> orchestrator

**Opción C: Reordenamiento dinámico (refactor alto)**
- ✅ URLs nuevas se insertan en orden óptimo
- ✅ Mantiene estrategia de procesamiento
- ❌ Muy complejo, cambios en política de reintentos
- ❌ Risk de inconsistencia si se pausa/resume

**Veredicto: Opción B es la mejor relación viabilidad/impacto**

### 3. Arquitectura Propuesta

**Cambios en BD:**
```sql
-- Nueva relación muchos-a-muchos para soporte de "agregar cuenta a batch"
CREATE TABLE batch_account_additions (
  id INTEGER PRIMARY KEY,
  batch_id INTEGER,
  added_account_id INTEGER,      -- cuenta a agregar
  source_batch_id INTEGER NULL,  -- NULL si es nueva, senó de otro batch
  added_at TIMESTAMP,
  status TEXT  -- PENDING, IMPORTED, PROCESSING
);

-- URL pueden venir de múltiples origen
ALTER TABLE urls ADD COLUMN source_batch_id INTEGER NULL;  
```

**En Orchestrator:**
```python
class DynamicBatchRunner:
  def run(self, batch_id, queue_new_accounts=None):
    self.batch_id = batch_id
    self.queue_new_accounts = queue_new_accounts or Queue()
    
    # Thread monitor de nuevas URLs
    monitor = Thread(target=self._monitor_new_accounts, daemon=True)
    monitor.start()
    
    # Procesamiento normal
    while True:
      account = self._next_account()
      if account is None:
        break
      self._process_account(account)
      self._check_new_accounts()  # Reorder si hay nuevas
```

### 4. Casos de Uso

**Caso 1: Agregar cuenta nueva (jamás descargada)**
- Usuario abre "Add Account" modal desde batch en ejecución
- Selecciona cuenta del catálogo + URLs
- Valida contra BD (¿ya está importada para este batch?)
- Inserta en `urls` con `batch_id` actual
- Orchestrator las detecta y procesa tras cuentas actuales

**Caso 2: Copiar cuentas de otro batch**
- Usuario selecciona batch Y, elige 2-3 cuentas
- Sistema busca URLs de esas cuentas en batch Y
- Las copia a batch X en ejecución
- Orchestrator las procesa

**Caso 3: Pedir a usuario "subir URLs"**
- Modal pequeño: "¿Más URLs para esta cuenta?"
- Usuario pega JSON o lista
- Se importan dinámicamente

### 5. Riesgos y Mitigaciones

| Riesgo | Severidad | Mitigación |
|--------|-----------|-----------|
| URL duplicada (ya en BD) | Media | Check `unique(batch_id, url)` |
| Account ya en ejecución actual | Alta | Detectar si está en queue activo |
| Insertar URL durante `send_to_bot()` → fichero asignado a otra | Alta | Lock transaccional en SQLite |
| Reordenamiento cambia estrategia de stories_first | Media | Mantener order invariante (stories primero) |
| Usuario agrega 1000 URLs de golpe | Baja | Limitar por validación UI (max 100/request) |
| Telethon pierde conexión con bot | Alta | **No es este spike**, pero requiere reintentos |

### 6. Cambios en Persistencia

**Tabla nueva:** `batch_account_additions` (tracking de cuando se agregó)

**Tabla alterada:** `urls` necesita columna `source_batch_id` (audit)

**Impacto en catálogo:**
- Ninguno, si se copia bien las relaciones
- Cuidado: no duplicar accounts en `account_history`

### 7. Compatibilidad con Features Existentes

**Stories first:**
- ✅ Si agregas cuenta nueva, sus stories se procesan primero
- Requiere detectar URL type antes de agregar

**Reintentos (FIFO):**
- ✅ URLs nuevas entran en cola de reintentos si necesario
- Requiere atómicidad al insertar

**Pause/Resume:**
- ⚠️ Si pausa y agrega URLs, al resumir se procesan
- Claro en semantica, pero requiere trazabilidad

## Conclusión

✅ **VIABLE** - Con cambios medios en arquitectura, es posible agregar cuentas dinámicamente.

**Razón:**
- BD soporta nuevas columnas sin migration destructiva
- Queue thread-safe permite inyectar URLs
- Orchestrator puede monitorear cambios
- Risk de duplicación es manejable con validaciones

**Complejidad: ALTA**
- ~12-15 horas
- Cambios en signature de `run()`
- Testing de race conditions
- Validaciones complejas

## Recomendación

1. **Fase 1 (Spike 4.1 primero):** Asegurar threading de batch execution
2. **Fase 2:** Implementar tabla `batch_account_additions` + monitor
3. **Fase 3:** Modal UI para "Add Account to Running Batch"
4. **Fase 4:** Copiar cuentas de otro batch
5. **Testing:** Concurrencia de inserts + processing

## Prompt para Implementación

```
Implementar adición de cuentas a batch en ejecución:

1. Migración BD (reversible):
   - Nueva tabla `batch_account_additions` (id, batch_id, added_account_id, source_batch_id, added_at, status)
   - ALTER TABLE urls ADD COLUMN source_batch_id INTEGER NULL
   - CREATE UNIQUE INDEX ON urls(batch_id, url) para evitar duplicados

2. Crear `src/ig_orchestrator/orchestration/dynamic_runner.py`
   - Clase DynamicBatchRunner que extiende orchestrator
   - Método `run(batch_id, queue_new_accounts=None, queue_new_urls=None)`
   - Monitor thread que revisa batch_account_additions cada 5 seg
   - Inyecta URLs nuevas en cola de procesamiento
   - Mantiene invariante: stories primero

3. Crear `src/ig_orchestrator/gui/add_account_modal.py`
   - Modal para agregar cuenta a batch en ejecución
   - Opción 1: Nueva cuenta (select del catálogo + ingresar URLs)
   - Opción 2: Copiar de otro batch (select batch + select cuentas)
   - Validaciones: no duplicados, username válido
   - Botón "Add" que inserta en batch_account_additions

4. Modificar BatchesView
   - Agregar botón "Add Account" durante ejecución
   - Deshabilitar antes de iniciar batch (enable solo durante run)
   - Conectar modal con DynamicBatchRunner

5. Actualizar orchestrator/main.py
   - Cambiar signature: run(batch_id, dynamic_queue=None)
   - En loops, revisar si hay URLs nuevas
   - Reordenar si necesario (stories primero)

6. Tests:
   - test_add_account_during_execution()
   - test_duplicate_url_prevented()
   - test_copy_account_from_other_batch()
   - test_stories_first_maintained_with_dynamic_add()
   - test_race_condition_url_processing_and_add()

7. Documentación:
   - Actualizar CHANGELOG.md
   - Agregar caso de uso a README.md
   - Documentar limite de URLs por request (recomendación: 50)
```
