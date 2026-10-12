# Tutorial de la serie v3

Guía de uso, feat a feat: **dónde está la opción, qué hace cada botón, qué rellenar y cómo probarla**.
Se amplía con cada feat terminado (regla del plan: un feat no está cerrado sin su sección aquí).

| Feat | Versión | Sección |
|---|---|---|
| 1 · Auditoría de biblioteca | v3.1.0 | [Feat 1](#feat-1--auditar-biblioteca-v310) |
| 2 · Instancias y «Traer descargas» | v3.2.0 | [Feat 2](#feat-2--instancias-y-traer-descargas-v320) |
| 3 · Catálogo completo en la app | v3.3.0 | [Feat 3](#feat-3--catálogo-completo-en-la-app-v330) |
| 4 · Operaciones de disco desde el catálogo | v3.4.0 | [Feat 4](#feat-4--operaciones-de-disco-desde-el-catálogo-v340) |
| 5 · Cuenta eliminada en Instagram | v3.5.0 | [Feat 5](#feat-5--cuenta-eliminada-en-instagram-v350) |

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

1. `python generatedirmap.py --lite` (13–55 s) → actualiza rutas (la fuente de verdad de qué carpetas existen).
2. `python generatedirmap.py --update` (2–32 s) → añade/actualiza en complete las cuentas nuevas o movidas y sus ficheros.
   **`--update` no borra** de complete las carpetas que ya no existen en disco; si quieres complete limpio usa en su lugar `python generatedirmap.py --complete` (~8 min, reconstruye todo).

No hace falta que complete esté perfecto: **la importación usa lite para saber qué carpetas existen** y complete solo para enriquecer (contadores y ficheros). Las carpetas que complete conserva y lite no tiene se **ignoran** y se listan en el informe (sección SOBRAN).

### Paso 1 · Simular — `Catálogo → Importar desde bdsc1…`

| Elemento | Qué es |
|---|---|
| `accounts_lite` / `accounts_complete` | Rutas de las dos bases de `G:\4K Stogram`. Se rellenan solas. |
| **Incluir índice de ficheros** | Marcado = carga también los ~900 000 ficheros (necesario para renombrar sin `G:`). Tarda ~14 s. |
| **Simular** | Calcula todo y lo muestra **sin escribir nada**. Úsalo siempre primero. |
| **Importar** | Hace una copia de seguridad (`data/bkp/orchestrator_gui_pre_import_*.sqlite`) y aplica la importación. |

**Cómo leer el informe**

La primera línea es el veredicto:

| Veredicto | Significa |
|---|---|
| ✔ **CORRECTO: se puede importar.** | Sin avisos ni incidencias. |
| ✔ **SE PUEDE IMPORTAR (con avisos)** | Es seguro importar; los avisos/incidencias son cosas para revisar *después*. Lo habitual en tu biblioteca. |
| ✖ **NO IMPORTAR TODAVIA** | Más de la mitad de las rutas caen fuera de la raíz de la biblioteca: la raíz (`G:\4K Stogram`) es incorrecta. |

**¿Puede pasar algo malo al pulsar Importar?** No debería: solo *añade* cuentas archivadas y *rellena* rutas/contadores; nunca cambia estados, favoritos o fechas de tus cuentas, no toca `G:` y antes hace una copia en `data/bkp/` que puedes restaurar.

Secciones del informe (con las listas de carpetas; «Guardar informe completo…» las trae enteras):

| Sección | Significa |
|---|---|
| **SOBRAN en accounts_complete** | Carpetas que complete aún tiene pero que ya no están en lite (borradas o movidas). Se ignoran. Para limpiarlas de complete: `sc1 --complete`. |
| **FALTAN en accounts_complete** | Carpetas que están en lite pero complete no conoce: se importan **sin índice de ficheros**. Ejecuta `sc1 --update` y vuelve a importar. |

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
| `OUTSIDE_ROOT` / `PATH_CLASH` | Ruta fuera de `G:\4K Stogram` / ruta ya usada por otra cuenta. | Revisar |
| `PARSE_ERROR` | Ficheros con nombre no reconocido (no entran en el índice). | Revisar |

### Paso 2 · Importar

Pulsa **Importar** y confirma. Es **idempotente**: si lo repites sin cambios en disco verás «0 creadas, 0 actualizadas». Desde consola: `python -m ig_orchestrator import-bdsc1 --dry-run` y luego sin `--dry-run`.

### Qué cambia en la app después

- **Catálogo:** sigue mostrando solo tus cuentas gestionadas. Para ver todas: menú `Ver → Mostrar biblioteca completa (archivadas)` (las archivadas salen en gris claro). No se recuerda entre sesiones.
- **Usar una cuenta archivada** (añadirla al editor o a un lote) la pasa automáticamente a **Habilitada**.
- **Organizar stories:** ya resuelve la carpeta de la cuenta desde la app (no usa `accounts_lite`). Desde v3.4.1 el diálogo solo pide la carpeta de stories; el campo de la base de cuentas antigua desapareció.
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
| El informe dice «raíz de la biblioteca: …» distinta de `G:\4K Stogram` | Ajusta `path_roots.LIBRARY` o usa `--root`. |
| Quieres deshacer | Restaura la copia de `data/bkp/` (cierra la app antes). |


---

## Feat 4 · Operaciones de disco desde el catálogo (v3.4.0)

**Para qué sirve:** crear, renombrar y mover carpetas y cuentas **desde el catálogo**, y que se refleje a la vez en `G:` y en la app. Es la primera función que **escribe en tu biblioteca**, por eso todo pasa por una vista previa, queda registrado y se puede deshacer.

> **Primera vez:** pruébalo con algo pequeño y reversible (una carpeta nueva vacía, o una cuenta de `10.TEMP`). `G:` debe estar conectada.

### Dónde está

Necesitas la **vista de árbol** del catálogo (botón del árbol junto al título «Catálogo», o `Ver → Vista de árbol`).

| Qué seleccionas | Clic derecho → | Qué hace |
|---|---|---|
| Una **carpeta** (categoría o grupo) | **Nueva carpeta…** | Pide un nombre y crea la carpeta dentro de la seleccionada (en disco y en el catálogo). Ejemplo: clic derecho en `00.FAVORITES` → *Nueva carpeta…* → `Maria-Perez` → se crea `G:\4K Stogram\00.FAVORITES\Maria-Perez`. |
| Una **carpeta** | **Renombrar carpeta…** | Cambia el nombre en disco y actualiza las rutas de **todas** las cuentas y subcarpetas que cuelgan de ella. |
| Una **carpeta** | **Mover a…** | Elige otra carpeta destino en un árbol; mueve la carpeta entera con todo su contenido. |
| Una **cuenta** (en árbol o en lista) | **Mover a otra carpeta…** | Mueve la carpeta de la cuenta a otra categoría/grupo (p. ej. de `00.FAVORITES\Grupo` a `04.INACTIVE`). |

No hay (todavía) arrastrar y soltar, borrar, fusionar ni renombrar el *username* de una cuenta: eso llega en feats posteriores.

### La vista previa

Antes de tocar nada se abre una ventana con:

| Elemento | Significa |
|---|---|
| Título | Qué vas a hacer. |
| Cuentas / carpetas afectadas | Cuántas rutas cambiarán. |
| Tabla *Acción · De · A* | Lo que se hará exactamente (rutas relativas a `G:\4K Stogram`). |
| Texto en rojo | **Conflictos que bloquean** (ver tabla). Con alguno, **Ejecutar** está desactivado. |
| **Ejecutar / Cancelar** | Nada ocurre hasta que pulses Ejecutar. |

| Conflicto | Significa |
|---|---|
| `DEST_EXISTS` | Ya existe algo con ese nombre en el destino. **Nunca se sobrescribe ni se fusiona.** |
| `INVALID_NAME` | El nombre tiene caracteres no válidos en Windows (`< > : " / \ | ? *`), es un nombre reservado (`CON`, `NUL`…) o acaba en punto/espacio. |
| `INTO_ITSELF` | Intentas mover una carpeta dentro de sí misma. |
| `ACCOUNT_IN_ACTIVE_BATCH` | Una cuenta afectada está en un lote que se está ejecutando. |
| `OFFLINE` | `G:` no está disponible. |
| `NO_CHANGE` / `NO_PATH` | El destino es el mismo / la cuenta no tiene carpeta conocida. |

Si `G:` está desconectada, las opciones del menú aparecen **desactivadas** (o un aviso lo explica).

### Qué se actualiza solo

- La carpeta en `G:` (renombrado instantáneo, solo metadatos).
- La ruta de la cuenta/carpetas en la app, y el árbol del catálogo.
- **`accounts_lite`**: se actualiza la ruta de las cuentas afectadas para que *Organizar stories* y el renombrado antiguo (`sc2`) sigan funcionando sin pasos manuales. Si lite no está accesible, se rehace al abrir la app.

### Deshacer y recuperación — `Catálogo → Operaciones de disco…`

| Elemento | Qué hace |
|---|---|
| Tabla | Cada acción realizada (fecha, tipo, origen → destino, estado). |
| **Deshacer** | Revierte la acción seleccionada en disco y en la app. Solo si el estado actual coincide (p. ej. una carpeta creada solo se puede deshacer si sigue vacía). |

Si la app se cierra a mitad de una operación, **al abrirla** comprueba el disco: si el movimiento llegó a hacerse, completa la app; si no, lo descarta. Te avisa con un mensaje.

### Cómo probarlo

1. Árbol del catálogo → clic derecho en una categoría pequeña → **Nueva carpeta…** `Prueba` → vista previa → **Ejecutar**. Comprueba en el Explorador que existe y que sale en el árbol.
2. Clic derecho en `Prueba` → **Renombrar carpeta…** → `Prueba2`.
3. Clic derecho en una cuenta de `10.TEMP` → **Mover a otra carpeta…** → `Prueba2`. Comprueba el disco y que *Organizar stories* la encuentra.
4. `Catálogo → Operaciones de disco…` → selecciona cada una y **Deshacer** en orden inverso (mover → renombrar → crear).

### Problemas típicos

| Síntoma | Causa |
|---|---|
| No aparece el menú de carpetas | Estás en la vista de lista: cambia a vista de árbol. |
| Las opciones salen desactivadas | `G:` no está conectada o hay un proceso en ejecución. |
| «Ya existe en disco» | Hay una carpeta con ese nombre: elige otro nombre u otro destino (no se fusiona). |
| Una carpeta no se ve tras crearla | Solo se muestran carpetas con cuentas o recién creadas vacías; pulsa el filtro vacío para refrescar. |


---

## Feat 5 · Cuenta eliminada en Instagram (v3.5.0)

**Para qué sirve:** cuando una cuenta ya no existe en Instagram, un solo paso la marca como **eliminada** y mueve su carpeta a `G:\4K Stogram\09.DELETED`. Sustituye al proceso manual (marcar + mover en el Explorador + tocar las bases a mano). Usa el motor del feat 4: vista previa, historial y deshacer.

> **Primera vez:** pruébalo con una cuenta de `10.TEMP`, y luego pulsa **Deshacer** o **Restaurar**. `G:` debe estar conectada.

### Dónde está

| Acción | Dónde | Qué hace |
|---|---|---|
| **Marcar como eliminada…** | Clic derecho en la cuenta, o `Catálogo → Marcar como eliminada…` | Estado `DELETED` + mueve la carpeta a `09.DELETED\<cuenta>`. Quita el favorito. |
| **Marcar varias como eliminadas…** | `Catálogo` | Pega varios usernames (uno por línea o separados por comas) y obtienes **un solo** plan. |
| **Restaurar cuenta eliminada…** | Clic derecho / `Catálogo` | Devuelve la carpeta a su sitio anterior y el estado que tenía. Solo cuentas `DELETED`. |
| **Sugerir eliminadas…** | `Catálogo` | Lista cuentas que fallaron con «no encontrada» en **2 o más lotes** distintos y sin descargas correctas después. **Es solo una pista**: nunca actúa sola. Selecciona y pulsa *Vista previa…*. |
| **Etiquetar 09.DELETED…** | `Catálogo` | Marca como `DELETED` las cuentas que **ya estaban** en `09.DELETED` (sin mover nada). Úsalo una vez tras importar. |
| **Ocultar** | Clic derecho / `Catálogo` | Antes se llamaba «Delete». Solo oculta la cuenta (`DISABLED`); **no mueve nada**. |

### Elegir el destino de la carpeta (v3.5.1)

Al pulsar **Marcar como eliminada…** se abre una ventana con una fila por cuenta: *Cuenta · De · A (carpeta destino) · Motivo*.

| Motivo | Cuándo se sugiere |
|---|---|
| **Carpeta -Deleted de la modelo** | Existe `<Modelo>-Deleted` (o `-Delete`) junto a la carpeta de la modelo. Ej.: la cuenta está en `00.FAVORITES\Valeria-Makusheva\lerabuns` y existe `00.FAVORITES\Valeria-Makusheva-Deleted` → se sugiere esa. |
| **Carpeta de eliminadas** | No existe la carpeta de la modelo con `-Deleted`, o la cuenta cuelga directamente de una categoría: se sugiere `09.DELETED`. |
| **Elegido por ti** | Cambiaste el destino. |
| **Ya está en una carpeta de eliminadas** | Solo cambiará el estado (no se mueve). |

| Botón | Qué hace |
|---|---|
| **Cambiar destino…** | Abre el árbol de carpetas para las filas seleccionadas. Elige una existente, o selecciona la carpeta padre y pulsa **Nueva carpeta aquí…** para escribir un nombre: la carpeta se **crea al ejecutar** y la cuenta se mueve dentro. |
| **Usar carpeta de eliminadas** | Pone `09.DELETED` (o la que tengas en Ajustes) en las filas seleccionadas. |
| **Restablecer sugerido** | Vuelve a la sugerencia automática. |
| **Usar sufijo _2 si ya existe** | Si ya hay una carpeta con ese nombre en el destino, usa `nombre_2` en vez de bloquear. |

Los avisos y bloqueos (favorita, id compartido, lote en ejecución, destino existente…) se muestran abajo y se recalculan al cambiar el destino; **Ejecutar** se desactiva mientras haya un bloqueo. Con varias cuentas puedes dar un destino distinto a cada una.

### Dónde se ven las cuentas eliminadas

Las cuentas `DELETED` **no salen** en el catálogo normal (igual que las archivadas). Para verlas: `Ver → Mostrar biblioteca completa` (salen en color **lila**).

### La vista previa (misma ventana del feat 4)

| Texto | Significa |
|---|---|
| Fila *Mover* `De → A` | La carpeta que se moverá a la carpeta de eliminadas. |
| Fila *Solo estado* | La cuenta no tiene carpeta en disco o ya está en `09.DELETED`: solo cambia el estado. |
| `era favorita` (aviso) | Dejará de ser favorita; se restaura si deshaces o restauras. |
| `el id … aparece también en @otra` (aviso) | Probablemente es un **renombrado**, no una eliminación: revísalo antes (feat 7 lo resolverá). No bloquea. |
| `lote borrador` (aviso) | La cuenta sigue en ese lote borrador; no se quita. |
| `ACCOUNT_IN_ACTIVE_BATCH` (rojo) | Está en un lote en ejecución: bloquea. |
| `DEST_EXISTS` (rojo) | Ya hay una carpeta con ese nombre en `09.DELETED`. La app pregunta si usar sufijo `_2`. |

### Ajustes — `Ajustes → Catálogo`

| Campo | Qué hace |
|---|---|
| Carpeta de cuentas eliminadas | Carpeta relativa a la biblioteca (por defecto `09.DELETED`). |
| Conservar la carpeta de grupo | Si lo marcas, usa `09.DELETED\<grupo>\<cuenta>` en vez de plano. Por defecto desmarcado (plano, como tus 134 actuales). |

### Deshacer

`Catálogo → Operaciones de disco…` → selecciona la operación → **Deshacer**: la carpeta vuelve a su sitio y la cuenta recupera su estado y su favorito anteriores. **Restaurar** hace lo mismo a posteriori, sin depender del historial.

### Si pasa algo raro

| Síntoma | Causa |
|---|---|
| Al abrir la app dice que completó una operación | Se cerró a mitad: la app lo comprobó en disco y lo dejó consistente. |
| La cuenta aparece movida pero sigue sin estado «eliminada» | Muy raro (corte entre el movimiento y el estado): usa **Etiquetar 09.DELETED…**. |
| «Restaurar» solo cambia el estado | La cuenta se etiquetó sin moverla: no se conoce su carpeta anterior. |
| Intentas añadir al editor una cuenta eliminada | La app pide confirmación explícita. |

### Cómo probarlo

1. `Ver → Mostrar biblioteca completa` y `Catálogo → Etiquetar 09.DELETED…`: clasifica las ~134 que ya estaban en esa carpeta (no mueve nada).
2. Clic derecho en una cuenta de `10.TEMP` → **Marcar como eliminada…** → revisa la vista previa → *Ejecutar*. Comprueba la carpeta en `09.DELETED`.
3. `Catálogo → Operaciones de disco…` → **Deshacer** (vuelve todo). Repite y esta vez usa **Restaurar cuenta eliminada…**.
4. Pega 2 usernames en **Marcar varias…** y revisa que sale un solo plan.
