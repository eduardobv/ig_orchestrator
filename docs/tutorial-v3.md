# Tutorial de la serie v3

Guía de uso, feat a feat: **dónde está la opción, qué hace cada botón, qué rellenar y cómo probarla**.
Se amplía con cada feat terminado (regla del plan: un feat no está cerrado sin su sección aquí).

| Feat | Versión | Sección |
|---|---|---|
| 1 · Auditoría de biblioteca | v3.1.0 | [Feat 1](#feat-1--auditar-biblioteca-v310) |
| 2 · Instancias y «Traer descargas» | v3.2.0 | [Feat 2](#feat-2--instancias-y-traer-descargas-v320) |
| 3 · Catálogo completo en la app | v3.3.0 | [Feat 3](#feat-3--catálogo-completo-en-la-app-v330) |

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
| **Comparar con lote** | Elige un lote **de este PC** (el mismo que enviaste a la laptop). La tabla añade la columna **En el lote** y las cuentas del lote que **aún no han llegado** salen como filas en gris «Falta (aún no llega)». Debajo, un resumen: «N de M cuentas ya están en la carpeta compartida · faltan X · Y carpetas no pertenecen al lote». Las filas en gris no se pueden traer (no existen todavía en la compartida). |
| Tabla | Una fila por carpeta que hay **en la carpeta compartida**: ficheros, MB, estado y (si elegiste lote) si pertenece al lote. |
| **Traer seleccionadas** | Trae solo las filas que marques (Ctrl/Mayús para varias). |
| **Traer todas las listas** | Trae todas las que estén *Lista* o *Ya existe en destino*. |
| **Cancelar** | Detiene el traspaso: lo no procesado sigue en la laptop y no quedan ficheros a medias. |

### Qué ve (y qué NO ve) la app — importante

Cada instancia tiene **su propia base de datos** y no se comunican. Por eso este diálogo **solo mira la carpeta compartida** (`tmp`) y tu carpeta de trabajo. **No sabe** qué lote está ejecutando la laptop ni qué cuentas ha terminado; **no ve** su carpeta de descargas (`Telegram_Desktop`), porque no está compartida.

Consecuencia práctica: **puedes ir trayendo mientras el lote sigue en la laptop**, pero solo lo que tú ya hayas movido a `tmp`. La app no puede saber si una cuenta está completa en la laptop; eso lo decides tú al moverla a `tmp`. «Comparar con lote» te ayuda: te dice cuántas cuentas del lote ya han llegado y cuáles faltan. (El feat 6 automatizará esto: la laptop publicará solo cuentas terminadas junto con un `manifest.json`.)

**Estados de cada carpeta** (se calculan solo con la carpeta compartida y tu carpeta de trabajo)

| Estado | Significa | Qué hace la app |
|---|---|---|
| **Lista** | Está en `tmp`, sin cambios recientes y no existe aún en tu carpeta de trabajo. | La trae. |
| **En uso** | Algún fichero de esa carpeta se modificó hace menos de 3× `DOWNLOAD_STABLE_SECONDS` (~30 s). Típico: **estás en medio de mover la carpeta a `tmp`** o la laptop sigue escribiendo. | Pide confirmación antes de traerla (riesgo de traerla incompleta). |
| **Ya existe en destino** | En **tu** carpeta de trabajo ya hay una carpeta con ese nombre (restos de otro lote o de un renombrado). | Fusiona sin sobrescribir: mismo nombre y tamaño → omite; otro tamaño → `nombre_1.ext`. |
| **Vacía** | La carpeta de `tmp` no tiene ficheros. | La ignora. |
| **Falta (aún no llega)** | Solo con «Comparar con lote»: cuenta del lote que no está en `tmp`. | Nada; es informativo. |

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
| La carpeta sale «En uso» | Se modificó hace menos de ~30 s (p. ej. aún la estás moviendo a `tmp`); espera y pulsa **Escanear**. |
| Elijo un lote y casi todo sale «Falta» | Normal si aún no has movido esas cuentas a `tmp`; la tabla solo muestra lo que ya está en la compartida. |


---

## Feat 3 · Catálogo completo en la app (v3.3.0)

**Para qué sirve:** que la app (`bdapp`) conozca **toda** tu biblioteca de `G:` (no solo las 334 cuentas que gestionas) con su ruta, sus contadores y el **índice de ficheros** que usará el renombrado sin necesitar `G:`. Después de esto ya no se consulta `accounts_lite`/`accounts_complete` para nada (salvo para volver a importar).

**Qué NO hace:** no escribe en `G:` ni en `accounts_*`, no mueve ni renombra carpetas, no escanea el disco (solo lee las bases de `sc1`).

### Paso 0 · Refrescar `accounts_complete` (una vez, a mano)

La importación es tan buena como `accounts_complete`. Con `G:` conectada, en tu carpeta de `sc1` (GenerateDirMap):

1. `python generatedirmap.py --lite` (13–55 s) → actualiza rutas.
2. `python generatedirmap.py --update` (2–32 s) → reconstruye en complete las cuentas nuevas/movidas y sus ficheros.

Si no lo haces, la importación te avisará: «accounts_complete desfasado respecto a lite: N rutas solo en lite…». (Hoy: 253 rutas de lite que complete no tiene.)

### Paso 1 · Simular — `Catálogo → Importar desde bdsc1…`

| Elemento | Qué es |
|---|---|
| `accounts_lite` / `accounts_complete` | Rutas de las dos bases de `G:K Stogram`. Se rellenan solas. |
| **Incluir índice de ficheros** | Marcado = carga también los ~900 000 ficheros (necesario para renombrar sin `G:`). Tarda ~14 s. |
| **Simular** | Calcula todo y lo muestra **sin escribir nada**. Úsalo siempre primero. |
| **Importar** | Hace una copia de seguridad (`data/bkp/orchestrator_gui_pre_import_*.sqlite`) y aplica la importación. |

**Cómo leer el informe**

| Línea | Significa |
|---|---|
| Cuentas creadas | Cuentas que existen en `G:` y no estaban en la app. Entran como **Archivadas**. |
| Cuentas actualizadas | Cuentas que ya tenías: reciben ruta, contadores y fecha del último contenido. **No cambian de estado, favorito ni fecha de inicio.** |
| Carpetas creadas | Nodos del árbol (categorías/grupos) que faltaban. |
| Indice de ficheros | Cuentas cuyo listado de ficheros se (re)cargó / sin cambios. |
| Incidencias | Cosas que requieren tu atención (ver tabla). Se guardan en la tabla `library_import_issues`; **no se corrige nada solo**. |

| Incidencia | Significa | Lo resuelve |
|---|---|---|
| `OWNER_DUP` | Varias carpetas con el mismo id de Instagram (cuenta renombrada/duplicada). | Feat 7 |
| `OWNER_MISMATCH` | El id de la app y el de `G:` difieren para un username. **No se sobrescribe.** | Revisar a mano |
| `FOLDER_MISMATCH` | La carpeta de la app no es la de `G:`. | Revisar / feat 4 |
| `USERNAME_DUP` | El mismo username en dos carpetas: se importa una (la de categoría activa o más reciente) y se anota la otra. | Feat 7 |
| `ONLY_IN_APP` | Cuenta de la app que ya no está en `G:`. | Feats 5/8 |
| `OUTSIDE_ROOT` / `PATH_CLASH` | Ruta fuera de `G:K Stogram` / ruta ya usada por otra cuenta. | Revisar |
| `PARSE_ERROR` | Ficheros con nombre no reconocido (no entran en el índice). | Revisar |

### Paso 2 · Importar

Pulsa **Importar** y confirma. Es **idempotente**: si lo repites sin cambios en disco verás «0 creadas, 0 actualizadas». Desde consola: `python -m ig_orchestrator import-bdsc1 --dry-run` y luego sin `--dry-run`.

### Qué cambia en la app después

- **Catálogo:** sigue mostrando solo tus cuentas gestionadas. Para ver todas: menú `Ver → Mostrar biblioteca completa (archivadas)` (las archivadas salen en gris claro). No se recuerda entre sesiones.
- **Usar una cuenta archivada** (añadirla al editor o a un lote) la pasa automáticamente a **Habilitada**.
- **Organizar stories:** ya resuelve la carpeta de la cuenta desde la app, aunque la cuenta no esté en `accounts_lite`. La «base de cuentas antigua» del diálogo pasa a ser opcional.
- **Búsqueda por id de Instagram:** el campo `instagram_user_id` está indexado (base del feat 7).

### Cómo probarlo

1. (Paso 0) Refresca `accounts_complete`.
2. `Catálogo → Importar desde bdsc1…` → **Simular**: comprueba que «Cuentas actualizadas» ≈ tus 331–334 gestionadas y que las incidencias coinciden con la auditoría (feat 1).
3. **Importar** → `Ver → Mostrar biblioteca completa`: debes ver ~1 250 cuentas; desmarca y vuelve a ver tus 334.
4. Repite **Importar**: debe decir 0 cambios.
5. `Organizar stories` con una imagen de una cuenta archivada: debe moverla a su carpeta `story`.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «No existe la base de datos: …» | Ruta mal o `G:` desconectada (puedes copiar las dos bases a local y apuntar ahí). |
| Muchas cuentas «creadas» en una segunda importación | Se movieron carpetas en `G:` y complete no se refrescó: repite el paso 0. |
| El informe dice «raíz de la biblioteca: …» distinta de `G:K Stogram` | Ajusta `path_roots.LIBRARY` o usa `--root`. |
| Quieres deshacer | Restaura la copia de `data/bkp/` (cierra la app antes). |
