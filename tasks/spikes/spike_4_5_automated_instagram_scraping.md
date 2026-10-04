# Spike 4.5: Automatizar Búsqueda de URLs de Instagram

## Objetivo
Analizar la viabilidad de automatizar la detección de nuevas publicaciones (stories + posts) de Instagram para cuentas en catálogo, permitiendo que la app genere y ejecute batches sin intervención manual prolongada.

## Workflow Actual del Usuario

**Cómo el usuario marca "ya descargué esto":**
- Da LIKE a cada publicación descargada en Instagram
- Tampermonkey (script adjunto) extrae URLs mientras navega
- Usa botones del script: Copy URLs, Clear, etc.
- Pega JSON en app, crea batch, ejecuta

**Contexto crítico:**
- El "like" en Instagram = marcador de "ya procesada"
- Stories = detectables por **borde rojo en foto de perfil** (solo con sesión autenticada)
- Cuenta puede tener 5-200+ publicaciones
- Usuario quiere delays largos (10s entre cuentas, 2s entre posts) para no disparar bans
- **Objetivo:** No ocupar horas del usuario, solo 5-10 minutos de intervención ligera

**Caso ideal:**
```
Usuario: Abre carpeta catálogo, click "Buscar actualizaciones"
  ↓
App: Empieza búsqueda en background MIENTRAS inicia descargas
  ↓
App: Por cada cuenta:
  - Detecta si hay stories (borde rojo)
  - Escanea posts recientes
  - Identifica cuáles ya tienen like (ya procesadas)
  - Agrega URLs nuevas (sin like)
  ↓
App: Mientras escanea cuenta N, descarga cuenta N-1
  ↓
Usuario: Puede pausar, ver avance, agregar cuentas
  ↓
Usuario: Batch se auto-completa y ejecuta en background
```

## Análisis de Viabilidad: 2 Opciones Principales

### Opción A: Selenium Automatizado (App controla todo)

**Flujo:**
```
1. Usuario abre app, click "Buscar Actualizaciones" en carpeta catálogo
2. App arranca Selenium en background
3. Para cada cuenta en carpeta:
   - Abre Instagram (ya logeado con sesión guardada)
   - Detecta si hay stories (borde rojo en pfp)
   - Scanea posts recientes (scrollea, pausa 2s entre posts)
   - Compara cada post: ¿tiene like? → Si = ya procesada, No = URL nueva
   - Agrega URLs nuevas al batch
   - Pausa 10s antes de siguiente cuenta
4. Mientras Selenium trabaja:
   - Orchestrator puede descargar cuentas anteriores
   - Nuevo batch se va completando dinámicamente
5. Usuario ve progreso en vivo (logs, contador de URLs)
```

**Técnicamente:**
```python
class SeleniumInstagramScraper:
  def __init__(self, instagram_session_file):
    # Restaura sesión para no re-hacer login
    self.driver = webdriver.Chrome()
    self.driver.get("instagram.com")
    self.restore_cookies(instagram_session_file)
  
  def fetch_account(self, username):
    # 1. Detecta stories: busca <img> con style borde rojo
    has_stories = self.detect_red_border_profile_pic(username)
    
    # 2. Scanea posts
    posts = []
    for post_element in self.scroll_and_detect_posts(limit=20):
      url = self.extract_post_url(post_element)
      has_like = self.detect_like_on_post(post_element)
      if not has_like:
        posts.append({
          'url': url,
          'type': self.classify_url(url),
          'has_story': has_stories
        })
      time.sleep(2)  # Pausa entre posts
    
    time.sleep(10)  # Pausa antes de siguiente cuenta
    return posts
```

**Ventajas:**
- ✅ Todo controlado por app
- ✅ Simultáneo: scrapea + descarga en paralelo
- ✅ User indica cuando empezar, app se autogestiona
- ✅ Usa sesión guardada (no re-login cada vez)
- ✅ Detecta stories por borde rojo (100% fiable con login)
- ✅ Detecta "ya procesada" por like (método del usuario)
- ✅ Bajo riesgo de ban (delays largos, sesión humana)

**Desventajas:**
- ❌ Requiere Selenium running constantemente
- ❌ Requiere sesión guardada + cookies válidas
- ❌ Requiere archivos de chromedriver
- ❌ Si Instagram cambia HTML, quebrado
- ❌ Complejidad media-alta (XPath, wait strategies)

**Risk de Ban:** BAJO (sesión real, delays de 2-10s)

**Complejidad de implementación:** MEDIA-ALTA (8-12h)

---

### Opción B: Tampermonkey (Usuario semi-manual, app acumula)

**Análisis del script adjunto:**
Tu Tampermonkey ya hace 80% del trabajo:
- ✅ Detecta stories (cuando user navega)
- ✅ Captura URLs (localStorage)
- ✅ Tiene botones para copiar, limpiar, ver URLs
- ✅ Marca automáticamente el like (botón "Like Next")
- ✅ Interfaz compacta (controles en esquina)

**Flujo mejorado:**

**Fase 1: Preparación (app)**
```
App: Genera lista de cuentas a verificar
   ├─ Usuario selecciona carpeta catálogo
   └─ App muestra: "Verificar: @account1, @account2, ... @account50"
   └─ Usuario copia lista
```

**Fase 2: Automatización en Tampermonkey (SIN intervención del user)**
```
User: Abre Instagram en Chrome (con Tampermonkey)
User: Click modal "Batch Scan" en Tampermonkey
  ├─ Pega lista: @account1, @account2, ... @account50
  └─ Click "Start Automation"

Tampermonkey automático:
  ├─ Para @account1:
  │   ├─ Navega a instagram.com/account1
  │   ├─ Detecta stories (borde rojo)
  │   ├─ Scanea posts (scrollea, detecta likes)
  │   ├─ Acumula URLs nuevas (sin like)
  │   └─ Pausa 5 segundos
  │
  ├─ Para @account2:
  │   └─ Repite (idem)
  │
  └─ Cuando termina todas:
     ├─ Genera JSON automático
     ├─ Descarga archivo .json
     └─ Muestra toast: "✅ Scanned 50 accounts, 247 URLs found"

User: Ve progreso en vivo (contador de cuentas, URLs por cuenta)
User: Mientras Tampermonkey trabaja, user puede tomar café ☕
```

**Tampermonkey maneja todo:**
- Navegación automática entre cuentas
- Detección de stories
- Escaneo de posts
- Acumulación de URLs
- Generación JSON
- Descarga
- Progress tracking

**Fase 3: Importación (app)**
```
App: Usuario pega JSON en modal "Import from Tampermonkey"
   ├─ Valida estructura
   ├─ Crea batch automático: "Auto_FECHA_browser"
   ├─ Importa cuentas + URLs
   └─ Auto-marca: si username tiene punto → `has_stories=false` (ignora story)
App: Genera batch listo para ejecutar
User: Click "Execute"
```

**Código Tampermonkey necesario (nuevo):**
```javascript
// Agregar botón "Export JSON" al panel actual
function exportAsJSON() {
  const urls = JSON.parse(localStorage.getItem('instagram_urls') || '[]');
  const username = extraerUsername();  // Ya existe en script
  
  let allExports = JSON.parse(localStorage.getItem('tm_all_accounts') || '[]');
  
  const account = {
    username: username,
    has_stories: detectRedBorder(),  // User debe indicar
    urls: urls,
    timestamp: new Date().toISOString()
  };
  
  allExports.push(account);
  localStorage.setItem('tm_all_accounts', JSON.stringify(allExports));
  
  console.log('Cuenta exportada:', account);
  
  // Mostrar preview
  alert(`Exportadas ${urls.length} URLs de ${username}`);
}

function downloadJSON() {
  const allExports = JSON.parse(localStorage.getItem('tm_all_accounts') || '[]');
  const json = JSON.stringify({ accounts: allExports }, null, 2);
  
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `instagram_urls_${new Date().toISOString().split('T')[0]}.json`;
  link.click();
  URL.revokeObjectURL(url);
  
  localStorage.removeItem('tm_all_accounts');
  alert('JSON descargado y almacenamiento limpiado');
}
```

**Ventajas:**
- ✅ User controla el ritmo (navega a su velocidad)
- ✅ Tu script ya hace 90% del trabajo
- ✅ Mínima intervención: solo navegar + copiar JSON
- ✅ Timing natural (user no se aburre esperando)
- ✅ Menos código nuevo (extiende script existente)
- ✅ Bajo riesgo de ban (user es humano)
- ✅ No requiere Selenium
- ✅ Si Instagram cambia HTML, user solo actualiza script

**Desventajas:**
- ⚠️ Requiere presencia del user durante escaneo
- ⚠️ No simultáneo con descargas (user espera)
- ❌ No automatizado, pero **semi-manual ligero**
- ⚠️ User debe indicar manualmente si hay stories (o auto-detectar con botón)

**Risk de Ban:** MUY BAJO (solo user, navegación normal)

**Complejidad de implementación:** BAJA-MEDIA (4-6h)
- Agregar modal "Import JSON" en app
- Parser del JSON
- Auto-validar usernames + stories check

---

## Comparativa Detallada

| Aspecto | Opción A: Selenium | Opción B Mejorada: Tampermonkey Batch |
|--------|-------------------|--------------------------------------|
| **Automatización** | 100% automática | 95% automática (pega lista + wait) |
| **Time to implement** | 8-12h | 6-8h |
| **Risk de ban** | BAJO | MUY BAJO (browser real) |
| **Requiere sesión** | Sí (guardada en BD) | Sí (Chrome ya logeado) |
| **Simultáneo scrape+download** | Sí ✅ (2 threads) | Sí ✅ (Tampermonkey + app) |
| **Intervención user** | Click botón = done | Pega lista → Click "Start" → Espera ☕ |
| **Robusto a cambios IG** | No (XPath breaks) | Sí (navega visual, tolera cambios) |
| **Dependency nuevo** | selenium, chromedriver | Ninguno (extends tu script) |
| **Ideal para** | 100+ cuentas, 24/7 | 5-100 cuentas, usuario presente durante scan |
| **Escalabilidad** | Media (session issues) | Alta (simple, extensible) |
| **Costo** | Chromedriver (gratis) | Ninguno |
| **Mantenimiento** | Frágil (IG cambios) | Fácil (solo actualizar script) |

---

## Recomendación: **Opción B Mejorada (Tampermonkey Batch Automation)**

**v2.1 (Fase 1 - AHORA):** Opción B MEJORADA ⭐
```
User: App genera lista de cuentas → User copia
User: Abre Instagram, abre modal Tampermonkey "Batch Scan"
User: Pega lista → Click "Start Automation"
User: VE PROGRESO EN VIVO mientras Tampermonkey:
  - Navega automáticamente cada cuenta
  - Detecta stories (borde rojo)
  - Escanea posts (detecta likes)
  - Acumula URLs nuevas
  - Genera JSON al final
User: Descarga JSON → Pega en app → Batch creado → Execute
```

**Características:**
- ✅ 95% automático (user solo espera)
- ✅ 6-8 horas implementación
- ✅ Zero nuevo dependencies (extends tu script)
- ✅ Muy bajo riesgo ban (delays 5s, browser real)
- ✅ **Mientras Tampermonkey trabaja, app puede descargar cuentas anteriores** (si Spike 4.1 hecho)

**v2.2 (Fase 2 - FUTURO):** Opción A opcional
- Solo si usuario quiere 100% automatización sin presencia
- Para 100+ cuentas diarias
- Selenium en background 24/7
- Premium feature

## Arquitectura: Opción B (Recomendada para v2.1)

**New Module: `browser_import`** (NOT browser_scraper)
```
src/ig_orchestrator/browser_import/
├─ __init__.py
├─ tampermonkey_parser.py    # Parse JSON from Tampermonkey
├─ batch_builder.py          # Build batch from parsed JSON
└─ import_modal.py           # GUI modal for paste JSON
```

**BD (mínimo):**
```sql
CREATE TABLE IF NOT EXISTS instagram_import_history (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  url TEXT NOT NULL,
  has_like INTEGER DEFAULT 0,  -- 1 = ya procesada
  imported_at TIMESTAMP,
  UNIQUE(username, url)
);
```

**Flujo:**

**1. Tampermonkey mejorado** (pequeña extensión de tu script):
```javascript
// Agregar botón al panel "🧑‍💼 Export Account"
function exportCurrentAccount() {
  const username = extraerUsername();  // Ya existe
  const urls = obtenerURLs();           // Ya existe
  const hasStories = confirm("¿Tiene stories esta cuenta? (OK=sí, Cancel=no)");
  
  const account = {
    username: username,
    has_stories: hasStories,
    urls: urls,
    timestamp: new Date().toISOString()
  };
  
  let allAccounts = JSON.parse(localStorage.getItem('tm_accounts') || '[]');
  allAccounts.push(account);
  localStorage.setItem('tm_accounts', JSON.stringify(allAccounts));
  
  // Copiar al portapapeles
  await copiarTexto(JSON.stringify(account, null, 2));
  alert(`✅ Cuenta exportada y copiada. URLs: ${urls.length}`);
  limpiarURLs();  // Reset para siguiente cuenta
}

function downloadAllAsJSON() {
  const allAccounts = JSON.parse(localStorage.getItem('tm_accounts') || '[]');
  const json = JSON.stringify({ accounts: allAccounts }, null, 2);
  
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `instagram_urls_${new Date().toISOString().split('T')[0]}.json`;
  link.click();
}
```

**2. App lado (GUI):**

Nueva modal: `gui/import_browser_modal.py`
```python
class ImportBrowserModal:
  def __init__(self, parent):
    self.modal = tk.Toplevel(parent)
    self.modal.title("Import URLs from Browser")
    
    # Paste area
    self.text_widget = tk.Text(self.modal, height=20, width=80)
    self.text_widget.pack(fill=tk.BOTH, expand=True)
    
    # Buttons: Parse, Create Batch, Cancel
    self.btn_parse = tk.Button(self.modal, text="Parse JSON", 
                               command=self.parse_json)
    self.btn_parse.pack(side=tk.LEFT)
    
  def parse_json(self):
    json_str = self.text_widget.get("1.0", tk.END)
    parsed = json.loads(json_str)  # Throws if invalid
    
    # Valida estructura
    accounts = parsed.get('accounts', [])
    
    # Crea batch
    batch_name = f"Auto_browser_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch_id = self.db.insert_batch(batch_name, len(accounts))
    
    for account in accounts:
      username = account['username']
      
      # Auto-fix: username con punto = no stories
      has_stories = account.get('has_stories', False)
      if '.' in username:
        has_stories = False
      
      account_id = self.db.insert_or_get_account(username)
      
      for url in account['urls']:
        url_type = classify_url(url)  # POST, REEL, STORY, etc
        self.db.insert_url(batch_id, url, url_type, account_id, 
                          has_like=True)  # Mark as liked (processed)
    
    # Muestra preview
    show_toast(f"✅ Batch created: {batch_name}")
    self.modal.destroy()
```

---

## Arquitectura: Opción A (Futuro, si necesita 100% auto)

Para referencia futura si user quiere Selenium automático:

**New Module: `instagram_scraper`**
```
src/ig_orchestrator/instagram_scraper/
├─ __init__.py
├─ selenium_scraper.py      # Selenium automation
├─ session_manager.py       # Manage saved sessions
└─ story_detector.py        # Detect red border
```

**No se implementa en v2.1, solo análisis guardado aquí.**

---

## Comparativa: Decisión para v2.1

✅ **OPCIÓN B RECOMENDADA** para v2.1:
- **Esfuerzo:** 5-6 horas
- **Risk:** MUY BAJO
- **Complejidad:** MEDIA
- **User experience:** Simple (navega + copia + pega + ejecuta)
- **Scalability:** Bien para 5-50 cuentas/día
- **Mantenimiento:** Bajo (script ya probado)

**Razones:**
1. Tu Tampermonkey ya hace 90% del trabajo
2. Usuario quiere "intervención ligera", no fully-auto
3. Delays naturales (user-paced) = zero ban risk
4. Si IG cambia HTML, user solo actualiza script
5. Selenium requeriría gestión de sesiones + chromedriver

⚠️ **Opción A (Selenium) = Futuro**
- Solo si user tiene 100+ cuentas y quiere fully-auto
- Implementar en v2.2+
- Complejidad 2x más
- Risk medio (XPath breaks, session management)

---

## Validaciones Críticas

**Auto-fix al importar JSON:**

```python
def validate_imported_account(account):
  username = account['username']
  
  # 1. Si username tiene punto → no stories (bot limitation)
  if '.' in username:
    account['has_stories'] = False
  
  # 2. Si URLs vacías → warning
  if not account.get('urls'):
    raise ValueError(f"No URLs for {username}")
  
  # 3. URLs válidas (https://instagram.com/...)
  for url in account['urls']:
    if not url.startswith(('https://instagram.com/', 'https://www.instagram.com/')):
      raise ValueError(f"Invalid URL: {url}")
  
  return account
```

---

## Conclusión

✅ **VIABLE Y RECOMENDADO — Opción B MEJORADA (Tampermonkey Batch Automation)**

**Razones:**
- Usa tu script existente como base (zero learning curve)
- User **no interviene entre cuentas** (totalmente automático)
- User solo: copia lista → Click "Start" → Espera
- Risk de ban: MUY BAJO (browser real, delays 5s)
- Implementación: 6-8 horas
- **Simultáneo: Mientras Tampermonkey scanea, app descarga en paralelo** ⭐

**Ventaja clave:** Es casi como Opción A (Selenium) pero:
- Sin Selenium (sin chromedriver, sin dependencies)
- Sin session management (user ya logeado)
- Más robusto (tolerante a cambios IG)
- Más simple de mantener (es solo JavaScript)
- **User queda en control** (puede pausar, ver progreso)

**Timing real:**
- 50 cuentas @ 5s cada una = 250 segundos ≈ 4 minutos
- Mientras eso, app ya descargó cuenta 1-5
- User ve progreso en tiempo real
- Al final: JSON listo, batch creado, descarga ongoing

---

## Recomendación para v2.1

**Implementar Opción B:**
1. Extiende Tampermonkey: agregar botón "Export Account" + "Download All JSON"
2. Agregar modal `ImportBrowserModal` en app
3. Auto-validar usernames + stories fix
4. Crear batch automático
5. Bonus: Si tiene tiempo, integrar con Spike 4.1 (background execution)

**NO implementar Opción A aún** — demasiado complejo para MVP

## Prompt para Implementación (Opción B: v2.1)

```
Implementar importación de URLs desde Tampermonkey (browser) en app:

1. Extender Tampermonkey script (pequeños cambios):
   - Agregar botón "📤 Export Account" que:
     - Obtiene username actual
     - Pide confirmación: "¿Tiene stories?" (si/no)
     - Crea JSON: {username, has_stories, urls, timestamp}
     - Copia al portapapeles
     - Acumula en localStorage.tm_accounts
   - Agregar botón "💾 Download All JSON" que:
     - Descarga archivo .json con todas las cuentas
     - Limpia localStorage

2. Crear módulo `src/ig_orchestrator/browser_import/`
   - `tampermonkey_parser.py`:
     ```python
     def parse_tampermonkey_json(json_str) -> List[Account]:
       data = json.loads(json_str)
       accounts = data.get('accounts', [])
       
       for account in accounts:
         username = account['username']
         # Auto-fix: username con punto
         if '.' in username:
           account['has_stories'] = False
         # Validar URLs
         validate_urls(account['urls'])
       
       return accounts
     ```

3. Crear GUI modal: `gui/import_browser_modal.py`
   - Tk modal con text area (paste JSON)
   - Botones: "Parse & Create Batch" / "Cancel"
   - Al parsear:
     - Muestra preview: "Accounts: @a, @b, @c | URLs: 45 total"
     - Crea batch automático
     - Importa cuentas + URLs
     - Muestra batch creado
     - Cierra modal

4. Conectar con UI:
   - Agregar botón "Import from Browser" en main toolbar
   - Abre ImportBrowserModal
   - Batch creado = listo para ejecutar

5. BD cambios (mínimo):
   - Nueva tabla instagram_import_history (para audit)
   - Columna urls.was_liked INTEGER (marca si ya tiene like)

6. Validaciones:
   ```python
   # Username con punto
   if '.' in username:
     urls = [u for u in urls if not u.endswith('/stories/')]
     has_stories = False
   
   # URLs válidas
   for url in urls:
     if not 'instagram.com' in url:
       raise ValueError(f"Invalid URL: {url}")
   ```

7. Tests:
   - test_parse_tampermonkey_json_valid()
   - test_parse_tampermonkey_json_invalid()
   - test_username_dot_auto_fix()
   - test_import_browser_modal_creates_batch()
   - test_batch_ready_to_execute()

8. Documentación:
   - Actualizar README.md: sección "Import URLs from Browser"
   - Adjuntar Tampermonkey script mejorado
   - Instrucciones: usuario navega → copia → pega → ejecuta

Cambios a Tampermonkey (agregar al script):
  
  A. Modal de input para batch:
  ```javascript
  function openBatchScanModal() {
    // Modal que pida lista de cuentas
    // Input: @account1, @account2, ..., @account50
    // Botón "Start Automation"
  }
  ```
  
  B. Clase BatchAutomation:
  ```javascript
  class BatchAutomation {
    async start(accountList) {
      const accounts = this.parseAccounts(accountList);
      const results = [];
      
      for (const username of accounts) {
        // Navega
        window.location = `https://instagram.com/${username}`;
        await this.waitForPageLoad(30000);  // 30s timeout
        
        // Detecta
        const hasStories = this.detectRedBorder();
        const urls = await this.scanPostsForNewURLs();
        
        results.push({username, has_stories: hasStories, urls});
        this.updateUI(`✅ ${username}: ${urls.length} URLs`);
        
        // Pausa (IMPORTANTE)
        await this.sleep(5000);
      }
      
      // Genera JSON
      this.downloadJSON({accounts: results});
    }
    
    detectRedBorder() {
      // Busca img con border-color:red o clase con borde rojo
      const profileImg = document.querySelector('img[alt*="profile"]');
      const style = window.getComputedStyle(profileImg?.parentElement);
      return style.borderColor.includes('red') || false;
    }
    
    async scanPostsForNewURLs() {
      // Scrollea, detecta likes, extrae URLs sin like
      const urls = [];
      
      // Scroll al fondo
      while (this.hasMorePosts()) {
        window.scrollBy(0, window.innerHeight);
        await this.sleep(1000);
      }
      
      // Parse posts
      document.querySelectorAll('article a[href*="/p/"]').forEach(link => {
        const url = link.href.split('?')[0];
        const hasLike = link.querySelector('svg[aria-label="Unlike"]') !== null;
        
        if (!hasLike && !urls.includes(url)) {
          urls.push(url);
        }
      });
      
      return urls;
    }
  }
  ```
  
  C. Integración en panel:
  - Agregar botón "🤖 Batch Scan" que abre modal
  - Modal con textarea para lista de cuentas
  - Botón "Start Automation" inicia BatchAutomation.start()
  - Progress tracker en vivo
  
  D. Descargar JSON automático al terminar
```

---

## Alternativa Futura (NO v2.1): Selenium Automático

```
[Guardado para v2.2+ si user solicita 100% automatización]

Opción A sería:
- Selenium + saved session cookies
- Detecta stories por borde rojo (@media queries)
- Scanea posts (detecta likes)
- Delays: 2s posts, 10s cuentas
- Simultáneo: scrape + download en parallel
- Complejidad: 10-12h
```
