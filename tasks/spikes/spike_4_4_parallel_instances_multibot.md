# Spike 4.4: Ejecutar Múltiples Instancias en Paralelo (Multi-Bot)

## Objetivo
Analizar la viabilidad de ejecutar 2+ instancias de ig_orchestrator simultáneamente (en diferentes PCs o mismo PC) con diferentes bots de Telegram, permitiendo procesar batches en paralelo sin que se dupliquen descargas o se causen conflictos de estado.

## Contexto Actual

**Estado:**
- Una sola sesión Telethon por instancia (`TELETHON_SESSION_NAME`)
- Un solo bot (`TELEGRAM_DOWNLOAD_BOT_USERNAME`)
- Archivo lock implícito en BD (SQLite)
- Logs y rutas hardcodeadas por PC

**Intento anterior (fallido):**
- Usuario intentó 2 PC, mismo bot → respuestas se solapaban
- Bot enviaba archivos a ambas carpetas de Telegram Desktop
- Conflictos: archivos duplicados, perdidos, o asignados a cuenta equivocada

**Arquitectura actual:**
```
PC1:
  ├─ TELEGRAM_DESKTOP_DOWNLOAD_FOLDER: C:\Users\eduba\Downloads\DW\Telegram_Desktop
  ├─ TELETHON_SESSION: telegram_user_session
  └─ BOT: @example_bot

PC2:
  ├─ TELEGRAM_DESKTOP_DOWNLOAD_FOLDER: C:\Users\otro\Downloads\...  (otro bot)
  ├─ TELETHON_SESSION: otro_session (MISMO BOT DESDE AQUÍ)
  └─ BOT: @example_bot  ← CONFLICTO

DB (Shared?):
  ├─ SQLite v1: local a cada PC
  └─ SQLite v2: ¿podría sincronizarse?
```

## Análisis de Viabilidad

### 1. Root Causes del Fallo Anterior

| Problema | Razón |
|----------|-------|
| **Respuestas solapadas** | Mismo bot recibe requests de 2 orchestrators sin identificación |
| **Archivos duplicados** | Descargados a ambos `TELEGRAM_DESKTOP_DOWNLOAD_FOLDER` |
| **Estado inconsistente** | Cada PC tiene SQLite local, sin sincronización |
| **Watcher conflictado** | Ambos watched carpeta de Telegram, movieron simultáneamente |

### 2. Requisitos para Multi-Bot Paralelo

Para que funcione, **NECESITA:**

**A. Identificación en mensajes al bot**
```
Request actual:
  /search URL
  
Request mejorado:
  /search URL [instance_id:pc1_batch_7]  ← Bot sabe quién pide
```
- Bot valida que respuesta vaya a PC1, no PC2
- Requiere cambio en bot externo (❌ fuera de alcance)

**B. BD centralizada**
```
Opción 1: PostgreSQL/MySQL central
  ✅ Sincronización en tiempo real
  ✅ Múltiples PCs leen/escriben
  ✅ Transacciones ACID
  ❌ Setup complejo, requiere servidor
  
Opción 2: SQLite + rsync/Dropbox
  ✅ Sin servidor extra
  ❌ Race conditions, eventual consistency
  ❌ Conflictos de locks

Opción 3: SQLite + HTTP API
  ✅ Centralizado
  ✅ Control de concurrencia
  ✅ Queries seguras
  ⚠️ Requiere API server
```

**C. Carpeta compartida con locking**
```
Opción 1: Carpeta Telegram Desktop = RED
  ✅ Un bot descarga a una carpeta central
  ✅ Un watcher procesa
  ❌ Latencia de red, bottleneck
  ❌ Conflictos de locks
  
Opción 2: Cada PC su carpeta + post-process central
  ✅ Descarga local rápida
  ✅ Post-process en central (MRF)
  ⚠️ Requiere orquestración
```

**D. Coordinator central**
```
- PC1 notifica: "Procesando batch_7, URLs 100-150"
- PC2 notifica: "Procesando batch_8, URLs 200-250"
- Coordinator valida: sin overlap
- Si overlap: uno espera, retry, o falla
```

### 3. Arquitecturas Posibles

**Arquitectura 1: Mismo Bot, múltiples sessions (NO VIABLE)**
```
PC1: Telethon session A → Bot → Response A
PC2: Telethon session B → Bot → Response B
                       ↓
                 ¿A o B? → CONFLICTO
```
❌ Bot no sabe a quién responder

---

**Arquitectura 2: Diferentes Bots (VIABLE pero caro)**
```
PC1: Bot A
PC2: Bot B
PC3: Bot C

Cada PC con su bot de Telegram
✅ Sin conflictos
✅ Paralelo real
❌ Requiere N bots (caro/complejo)
⚠️ Mejor para escala grande
```

---

**Arquitectura 3: Coordinator Central + Lockfile (VIABLE con esfuerzo)**
```
PC1 ─┐
PC2 ─┼─→ Coordinator (API) + BD Central + Watcher Central
PC3 ─┘

1. PC1 reserva batch_7 en coordinator
2. PC2 intenta batch_7 → rechazado, elige batch_8
3. PC1 descarga a carpeta local
4. Coordinator notifica watcher central
5. Watcher central procesa archivos (NFS/Samba)
6. Todos actualizan BD central

✅ Un solo bot
✅ Paralelo controlado
❌ Latencia de red
❌ Complejidad ALTA (API server)
```

---

**Arquitectura 4: Shared Cloud BD + Local Bot (VIABLE con límites)**
```
PC1 ┐
PC2 ┤─→ PostgreSQL Cloud + File Storage
PC3 ┘     (AWS RDS / Supabase / Firebase)

1. BD central en Postgres
2. Cada PC sync datos para evitar conflictos
3. File uploads a S3/GCS
4. Mismo bot pero Coordinator smart

✅ Escalable
❌ Cloud cost
❌ Latencia
```

### 4. Análisis: ¿Cuál es Viable Para Este Proyecto?

| Opción | Viabilidad | Esfuerzo | Costo | Recomendación |
|--------|-----------|----------|-------|---------------|
| Mismo bot, multi-session | ❌ NO | - | - | No funciona |
| Multi-bot (N bots) | ✅ SÍ | BAJO | ALTO | Si dinero no importa |
| Coordinator local | ✅ SÍ | ALTO | BAJO | Si es hobby/homelab |
| Cloud BD + Coordinator | ✅ SÍ | MEDIO | MEDIO | Si escalas |
| **Límite: 1 instancia por bot** | ✅ SÍ | BAJO | BAJO | **RECOMENDADO** |

### 5. Recomendación: "1 Instancia por Bot"

**La solución más simple y viable:**

```
Bot A (@bot_a) → PC1 ejecuta batch A,B,C
Bot B (@bot_b) → PC2 ejecuta batch D,E,F
Bot C (@bot_c) → PC3 ejecuta batch G,H,I

Cada bot en su PC
Sin coordinación necesaria
Logs y BD locales
Post-process después en central (opcional)
```

**Implementación:**
1. Configurar `.env` diferente por PC (bot_a, bot_b, bot_c)
2. Cada PC corre instance con su bot
3. BD distribuidas (o sync manual post-process)
4. Reportes consolidados si needed

**Validaciones en código:**
```python
# En init
if another_instance_running_with_same_bot():
  raise Exception("Ya hay instancia con este bot")
```

### 6. Alternativa Coordinada (Si Usuario Insiste)

Si quiere múltiples PCs con MISMO bot:

1. **Crear Coordinator API** (FastAPI)
   - Lock distribuido (redis o sqlite)
   - Endpoint: `POST /reserve_batch`
   - Endpoint: `GET /status`

2. **Cambiar Orchestrator**
   - Llamar `/reserve_batch` antes de ejecutar
   - Release al terminar

3. **BD Central**
   - PostgreSQL en servidor
   - Cada PC: `DB_URL=postgres://server/...`

4. **File Watcher Central**
   - Script separado que mira Telegram Desktop en red
   - Procesa para todos los batches

**Estimado: 40-50 horas + setup de servidor**

### 7. Cambios en Código para "1 Instancia por Bot"

**BD:**
- ✅ Sin cambios
- Cada PC su SQLite local

**Orchestrator:**
```python
# Validación al iniciar
def check_single_instance():
  existing_lock = sqlite.query("SELECT pid FROM app_lock WHERE bot_username = ?")
  if existing_lock:
    raise RuntimeError("Instancia ya corriendo con este bot")
  sqlite.insert("app_lock", bot_username=X, pid=os.getpid(), timestamp=now())
```

**ENV:**
```env
# PC1
TELEGRAM_DOWNLOAD_BOT_USERNAME=@bot_a
TELETHON_SESSION_NAME=session_pc1

# PC2
TELEGRAM_DOWNLOAD_BOT_USERNAME=@bot_b
TELETHON_SESSION_NAME=session_pc2
```

**Riesgo:** Mínimo, solo validación de locks

## Conclusión

❌ **NO VIABLE** ejecutar 2+ instancias en paralelo con MISMO bot sin refactor mayor.

✅ **VIABLE** si:
1. Usas N bots diferentes (1 por PC)
2. O implementas Coordinator central (40+ horas)
3. O usas BD cloud + API

**Recomendación:**
- **Para ahora:** "1 instancia por bot" con validación de locks
- **Para futuro:** Si escala a muchos PCs, migrar a Coordinator + PostgreSQL

**Complejidad de "1 por bot": BAJA**
- Solo validación en BD
- 2-3 horas

**Complejidad de Coordinator:** ALTA
- 40-50 horas
- Setup extra de servidor

## Prompt para Implementación (Opción Simple: 1 Por Bot)

```
Implementar validación de "1 instancia por bot":

1. Crear tabla app_locks:
   ```sql
   CREATE TABLE IF NOT EXISTS app_locks (
     id INTEGER PRIMARY KEY,
     bot_username TEXT UNIQUE,
     instance_id TEXT,
     started_at TIMESTAMP,
     pid INTEGER
   );
   ```

2. En main.py, agregar check al inicio:
   ```python
   def validate_single_instance(bot_username):
     existing = db.query_one(
       "SELECT * FROM app_locks WHERE bot_username = ?", (bot_username,)
     )
     if existing:
       raise RuntimeError(f"Ya hay instancia ejecutando con bot {bot_username}")
     
     instance_id = f"{socket.gethostname()}_{os.getpid()}_{timestamp()}"
     db.insert("app_locks", 
       bot_username=bot_username,
       instance_id=instance_id,
       started_at=now(),
       pid=os.getpid()
     )
     return instance_id
   ```

3. En exit (finally block):
   ```python
   db.delete("app_locks WHERE bot_username = ?", (bot_username,))
   ```

4. Documentar en CLAUDE.md:
   - 1 instancia por bot
   - Para multi-PC: usar N bots diferentes
   - Si necesita Coordinator: referencia a spike 4.4

5. Tests:
   - test_second_instance_same_bot_rejected()
   - test_lock_released_on_exit()

Documentar en CHANGELOG.md como prevención de conflictos.
```

## Prompt para Implementación (Opción Avanzada: Coordinator)

```
[Solo si usuario autoriza 40+ horas y setup de servidor]

Implementar Coordinator Central para ejecutar múltiples instancias 
con mismo bot sin conflictos...
[Incluiría API en FastAPI, Redis, cambios en orchestrator, etc.]
```
