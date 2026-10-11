# Tutorial de la serie v3

Guía de uso, feat a feat: **dónde está la opción, qué hace cada botón, qué rellenar y cómo probarla**.
Se amplía con cada feat terminado (regla del plan: un feat no está cerrado sin su sección aquí).

| Feat | Versión | Sección |
|---|---|---|
| 1 · Auditoría de biblioteca | v3.1.0 | [Feat 1](#feat-1--auditar-biblioteca-v310) |
| 2 · Instancias y «Traer descargas» | v3.2.0 | [Feat 2](#feat-2--instancias-y-traer-descargas-v320) |

---

## Feat 1 · Auditar biblioteca (v3.1.0)

**Para qué sirve:** chequeo de salud de la biblioteca. Compara la app (`bdapp`), `accounts_lite`, `accounts_complete` y las carpetas reales de `G:`. **Solo lee; no cambia nada.**

**Dónde está:** menú `Catálogo → Auditar biblioteca…`  ·  consola: `python -m ig_orchestrator audit-library`.

### Campos y botones

| Elemento | Qué es |
|---|---|
| `accounts_lite` | Ruta de la base `accounts_lite.sqlite` de `G:\4K Stogram`. Se rellena sola con la del «Organizar stories». |
| `accounts_complete (opcional)` | Normalmente `G:\4K Stogram\accounts_complete.sqlite`. Si no existe, se omite esa parte. |
| **Auditar** | Lanza la comprobación (tarda ~1 s con `G:` conectada). |
| **Código** | Filtra la tabla por tipo de hallazgo. |
| **Exportar Markdown / CSV** | Guarda el informe (el CSV se abre en Excel). |
| **Abrir en Explorer** | Abre la carpeta de la fila seleccionada (o la carpeta existente más cercana). |

### Qué significa cada código

| Código | Significado | ¿Qué hacer? |
|---|---|---|
| `PATH_MISSING` | La base dice que la carpeta existe y en disco no está. | Revisar si se borró/movió; se arreglará en feats posteriores. |
| `OWNER_DUP` | Varias carpetas con el mismo id de Instagram (cuenta renombrada o duplicada). `SAME_CATEGORY` / `DELETED_PAIR` / `ALL_DELETED` / `CROSS_CATEGORY` es solo una pista. | Anotarlo; lo resuelve el feat 7. |
| `OWNER_MISMATCH` | La app y `G:` tienen un id de Instagram distinto para el mismo username. | Revisar a mano. |
| `FOLDER_MISMATCH` | La carpeta de la app no coincide con la de `G:`. | Revisar a mano. |
| `ONLY_IN_APP` / `ONLY_IN_LITE` | Cuenta solo en la app / solo en `G:`. `ONLY_IN_LITE` es informativo (cuentas que la app aún no gestiona). | El feat 3 las traerá. |
| `COMPLETE_STALE` | `accounts_complete` está desfasado respecto a lite. | Volver a ejecutar sc1 antes del feat 3. |
| `LAST_MODIFIED_MIXED` | Dos formatos de fecha en lite (informativo). | Nada. |
| `NAME_CASE`, `USERNAME_DUP` | Mayúsculas distintas / mismo username en dos rutas. | Revisar. |
| `DISK_OFFLINE` | `G:` no está conectada: solo se compararon bases de datos. | Conectar `G:`. |

**Cuándo usarlo:** antes del feat 3 (foto de partida), después de cada feat que toque carpetas, y si sospechas que algo no cuadra.

**Cómo probarlo:** abre el menú, pulsa **Auditar** y compara con los números de `tasks/done/v3/feat-uc3-1.md`.

---

## Feat 2 · Instancias y «Traer descargas» (v3.2.0)

**Para qué sirve:** eliminar el paso manual de copiar a mano las carpetas de la otra máquina. Desde este PC, la app **trae** las carpetas que la laptop dejó en su carpeta compartida hasta tu carpeta de trabajo.

### Cómo funciona tu flujo (con tus rutas)

```
LAPTOP (inst1)                                              ESTE PC (pc1)
Descarga en:                                                Carpeta de trabajo (WORKING):
C:\Users\eduba\Downloads\DW\Telegram_Desktop                C:\Users\eduba\Downloads\DW\Telegram_Desktop
        │  (tú mueves las carpetas, como ahora)                     ▲
        ▼                                                           │  «Traer descargas…» (la app)
C:\Eduardo\ig_orchestrator\tmp  ── compartida como ──►  \\DESKTOP-OM856P7\ig_orchestrator\tmp
```

Lo único que cambia respecto a hoy: el paso «cortar de la compartida y pegar en mi carpeta de trabajo» lo hace la app (verificado, sin sobrescribir). El paso en la laptop (mover de `Telegram_Desktop` a `tmp`) sigue siendo manual hasta el feat 6.

> **No hace falta tocar nada en la laptop** para este feat: se instala y configura solo en este PC.

### Paso 1 · Registrar las instancias — `Ajustes → Instancias`

Pulsa **Añadir** dos veces. El significado de cada campo:

| Campo | Qué poner | ¿Se usa? |
|---|---|---|
| **Nombre** | Un nombre corto: `pc1`, `inst1`. | Sí (se muestra en listas). |
| **Rol** | `MAIN` = la principal (este PC). `WORKER` = la que solo descarga (laptop). | Informativo por ahora. |
| **Es esta instancia (local)** | Márcalo **solo** en la fila de este PC. | Sí: la local nunca aparece como origen. |
| **Su carpeta de descargas** | La carpeta donde ESA máquina descarga. | Solo informativa. |
| **Carpeta compartida: ruta desde ESTE PC** | La ruta de red por la que ESTE PC ve la carpeta compartida. | **Sí, es la que usa «Traer descargas».** |
| **Carpeta compartida: ruta en ELLA misma** | La misma carpeta tal como la ve la laptop. | Solo informativa. |
| Notas | Libre. | No. |

**Instancia 1 — este PC**

| Campo | Valor |
|---|---|
| Nombre | `pc1` |
| Rol | `MAIN` |
| Es esta instancia (local) | ✔ |
| Su carpeta de descargas | `C:\Users\eduba\Downloads\DW\Telegram_Desktop` |
| Carpetas compartidas | *(vacías)* |

**Instancia 2 — la laptop**

| Campo | Valor |
|---|---|
| Nombre | `inst1` |
| Rol | `WORKER` |
| Es esta instancia (local) | *(sin marcar)* |
| Su carpeta de descargas | `C:\Users\eduba\Downloads\DW\Telegram_Desktop` |
| Carpeta compartida: ruta desde ESTE PC | `\\DESKTOP-OM856P7\ig_orchestrator\tmp` |
| Carpeta compartida: ruta en ELLA misma | `C:\Eduardo\ig_orchestrator\tmp` |

Selecciona `inst1` y pulsa **Probar**: debe decir *accesible · escritura: Sí · libre: X GB*. Si dice «No existe o no es accesible», la laptop está apagada o la carpeta no está compartida con permisos de lectura y escritura. Los cambios se guardan al instante (no hace falta pulsar «Guardar» de Ajustes).

### Paso 2 · Traer las descargas — `Lote → Traer descargas…`

(También hay un botón **Traer descargas…** en el diálogo de lotes, que preselecciona el lote elegido.)

| Elemento | Qué hace |
|---|---|
| **Instancia** | Elige `inst1`; el campo *Origen* se rellena con su carpeta compartida. «(ruta libre)» te deja escribir cualquier carpeta. |
| **Origen** + *Examinar…* | Carpeta de la que traer. **Escanear** la lista (se escanea sola al abrir). |
| **Destino** | Siempre tu carpeta de trabajo (`WORKING_FOLDER` del `.env`). Solo se muestra. |
| **Conservar copia en origen** | Marcado = copia (la laptop mantiene sus carpetas). Desmarcado (por defecto) = mueve, como tu «cortar». |
| **Comparar con lote** | Elige un lote y verás «N/M cuentas recibidas. Faltan: … Sobrantes: …». |
| Tabla | Una fila por carpeta: ficheros, MB y estado. |
| **Traer seleccionadas** | Trae solo las filas que marques (Ctrl/Mayús para varias). |
| **Traer todas las listas** | Trae todas las que estén *Lista* o *Ya existe en destino*. |
| **Cancelar** | Detiene el traspaso: lo no procesado sigue en la laptop y no quedan ficheros a medias. |

**Estados de cada carpeta**

| Estado | Significa | Qué hace la app |
|---|---|---|
| **Lista** | Estable y sin conflicto. | La trae. |
| **En uso** | Se ha modificado hace menos de 3× `DOWNLOAD_STABLE_SECONDS` (la laptop aún escribe). | Pide confirmación antes de traerla. |
| **Ya existe en destino** | Hay una carpeta con ese nombre en tu trabajo. | Fusiona sin sobrescribir: mismo nombre y tamaño → omite; otro tamaño → `nombre_1.ext`. |
| **Vacía** | Sin ficheros. | La ignora. |

Al terminar, si elegiste un lote, la app pregunta si quieres marcarlo como **«Ejecutado en otra instancia»**. Con «Sí», el lote pasa a *Por renombrar* y ya puedes pulsar **Renombrar**.

### Paso 3 · Renombrar

Igual que siempre. Extra: si pulsas **Renombrar** con tu carpeta de trabajo vacía y la laptop tiene carpetas listas, la app te pregunta «¿Traer las descargas primero?».

### Cómo probarlo sin riesgo

1. Registra `inst1` y pulsa **Probar**.
2. En la laptop, deja **una** carpeta pequeña en `C:\Eduardo\ig_orchestrator\tmp` (p. ej. una cuenta con 2–3 ficheros) y espera 30 s.
3. `Lote → Traer descargas…` → debe aparecer *Lista* → **Traer seleccionadas**.
4. Comprueba que la carpeta está en tu trabajo y ya no está en la laptop.
5. Prueba también **Conservar copia en origen** y **Cancelar** con una carpeta grande.

### Problemas típicos

| Síntoma | Causa probable |
|---|---|
| «No existe o no es accesible» al Probar | Laptop apagada, red caída, carpeta no compartida o sin permiso de escritura. |
| «Sin respuesta en 8 s» | El nombre de red no resuelve; prueba la IP: `\\192.168.x.x\ig_orchestrator\tmp`. |
| No aparece ninguna instancia en el desplegable | Solo salen las **no locales** con carpeta compartida (o de descargas) rellena. |
| La carpeta sale «En uso» | Se modificó hace menos de ~30 s; espera y pulsa **Escanear**. |
