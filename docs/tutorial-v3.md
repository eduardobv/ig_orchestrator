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
| 6 · La laptop entrega sola (paquetes) | v3.6.0 | [Feat 6](#feat-6--la-laptop-entrega-sola-paquetes-v360) |
| 7 · Cuenta que cambió de username | v3.7.0 | [Feat 7](#feat-7--cuenta-que-cambió-de-username-v370) |
| 8 · Sincronizar con el disco | v3.8.0 | [Feat 8](#feat-8--sincronizar-con-el-disco-v380) |
| 9 · Renombrado integrado | v3.9.0 | [Feat 9](#feat-9--renombrado-integrado-v390) |
| 10 · Renombrar sin G: | v3.10.0 | [Feat 10](#feat-10--renombrar-sin-la-unidad-g-v3100) |
| 11 · Almacén y volcado | v3.11.0 | [Feat 11](#feat-11--almacen-y-volcado-a-g-v3110) |
| 12 · Catálogo avanzado | v3.12.0 | [Feat 12](#feat-12--catalogo-avanzado-v3120) |
| 13 · Mover con sugerencias | v3.13.0 | [Feat 13](#feat-13--mover-con-sugerencias-busqueda-y-seleccion-multiple-v3130) |
| 14 · Estado según carpeta y ventanas centradas | v3.14.0 | [Feat 14](#feat-14--estado-segun-carpeta-color-unico-y-ventanas-centradas-v3140) |
| 15 · Estado también con -Inactive | v3.15.0 | [Feat 15](#feat-15--el-estado-tambien-sigue-a-las-carpetas--inactive-v3150) |
| 16 · Cierre de pendientes | v3.16.0 | [Feat 16](#feat-16--cierre-de-pendientes-v3160) |

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

En la **vista de árbol** las cuentas `DELETED` aparecen dentro de su carpeta (p. ej. `Adrianna-Eves-Deleted`) en color **lila**. En la **vista de lista** no salen (igual que las archivadas); para verlas ahí: `Ver → Mostrar biblioteca completa`.

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


---

## Feat 6 · La laptop entrega sola (paquetes) (v3.6.0)

**Para qué sirve:** la laptop 24/7 (`inst1`) deja de necesitar que muevas carpetas a mano. Al terminar un lote, la app de la laptop **publica un paquete** en la carpeta compartida con las carpetas descargadas **y el resultado real de cada URL**. En tu PC, **Importar paquetes** copia los ficheros y crea el lote con esos resultados, listo para **Renombrar**. Se acabó el «Ejecutado en otra instancia» que marcaba todo como fallido.

> **Importante:** necesitas la **versión 3.6.0 o superior en las dos máquinas**. La laptop debe actualizarse para publicar; tu PC para importar. Cada máquina sigue con su propia base de datos.

### Cómo queda tu flujo

```
LAPTOP (WORKER)                                              TU PC (MAIN)
Descarga el lote (Telegram_Desktop = su carpeta de trabajo)
        │  al terminar, la app publica sola (o Lote → Publicar descargas…)
        ▼
C:\Eduardo\ig_orchestrator\tmp\inst1_<lote>_<fecha>\      ── compartida ──►   Lote → Traer descargas… → Importar paquetes
   manifest.json  +  data\<cuenta>\...                                                   (copia ficheros + crea el lote con estados reales)
                                                                                         ▼
                                                                              Renombrar (como siempre)
```

### Paso 1 · En la laptop: configurar (una vez)

`Ajustes → Instancias`:

| Qué | Valor (ejemplo con tus rutas) |
|---|---|
| Añadir la instancia local | Nombre `inst1` · Rol **WORKER** · marcada **«Es esta instancia (local)»** |
| Carpeta compartida: ruta en ELLA misma | `C:\Eduardo\ig_orchestrator\tmp` (**obligatoria para publicar**) |
| Casilla **Publicar automáticamente al terminar los lotes** | Marcada para que lo haga sola |
| Modo | **MOVE** (mueve: borra la carpeta de descargas solo después de verificar el 100 %) o **COPY** (conserva el origen) |

> La auto-publicación solo funciona si la instancia **local** es `WORKER`. En tu PC (rol MAIN) la casilla no tiene efecto.

### Paso 2 · En la laptop: publicar

| Cómo | Qué pasa |
|---|---|
| **Automático** | Al terminar un lote (o una cola entera) sin errores, la consola dice «Publicando…» y luego «Paquete publicado: N cuenta(s), M fichero(s)». No bloquea el siguiente lote. |
| **Manual** — `Lote → Publicar descargas…` | Lista los lotes terminados sin publicar. Elige uno o varios, el modo (mover/copiar) y pulsa **Publicar**. |

Si la compartida está apagada, no se pierde nada: el origen no se toca y puedes repetirlo con `Publicar descargas…`.

Reglas del paquete: se construye en una carpeta `*.partial`; el `manifest.json` se escribe el **último** y solo entonces se renombra. Si se corta la red, **no queda un paquete que parezca válido** (los `*.partial` viejos se limpian solos).

### Paso 3 · En tu PC: importar

`Lote → Traer descargas…` → elige `inst1` → **Escanear**. Verás dos tipos de fila:

| Fila | Qué es | Botón |
|---|---|---|
| Carpeta suelta (como antes) | Una carpeta de cuenta movida a mano | **Traer seleccionadas / todas** |
| **[Paquete]** `inst1 · <lote>` en azul | Un paquete publicado por la laptop: lote(s), nº de cuentas, ficheros y MB | **Importar paquetes** |

| Estado del paquete | Significa |
|---|---|
| **Paquete listo** | Se puede importar. |
| **Ya importado** | Ya se importó (no se duplica nada). |
| Texto de error (p. ej. «Incompleto (sin manifiesto)», «requiere la app 3.6.0…») | No se puede importar; el texto dice por qué. |

**Importar paquetes** (sin seleccionar nada importa todos los listos):

1. Comprueba el tamaño de cada fichero contra el manifiesto (si alguno falta o difiere, no importa nada).
2. Copia las carpetas a tu carpeta de trabajo sin sobrescribir (igual que «Traer»).
3. Crea el lote con los **estados reales** de cada URL (completadas, fallidas y por qué), las cuentas nuevas con sus datos de renombrado, y lo deja **POR RENOMBRAR**.
4. Marca el paquete como importado y borra los ficheros del paquete (con *Conservar copia en origen* se conservan).

Reglas del lote: si ya tenías el lote como **borrador** se le aplican los resultados; si existía terminado, se crea como `<lote>_inst1` (y se avisa). Las cuentas se buscan primero por **id de Instagram** y luego por username; las desconocidas se crean.

### Paso 4 · Renombrar

Igual que siempre: `Renombrar`. Las cuentas nuevas ya llevan su id, fecha de inicio y carpeta destino.

### «Ejecutado en otra instancia»

Sigue existiendo para lotes **sin paquete**, pero ahora avisa de que **descarta los resultados reales**. Si la laptop publicó un paquete, usa **Importar paquetes**.

### Cómo probarlo

1. Actualiza las dos máquinas a ≥ 3.6.0. En la laptop configura el Paso 1.
2. Lanza un lote pequeño en la laptop (o usa `Publicar descargas…` con uno terminado, en modo **COPY** la primera vez).
3. En tu PC: `Traer descargas…` → **Escanear** → debe aparecer la fila **[Paquete]** → **Importar paquetes**.
4. Comprueba en `Lote → Abrir lotes` que el lote está **POR RENOMBRAR** y que las URLs tienen sus estados reales (ninguna «Executed on another instance»); pulsa **Renombrar**.
5. Vuelve a escanear: el paquete sale **Ya importado**. Importarlo otra vez no hace nada.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «No hay carpeta compartida…» al publicar | La instancia local no tiene «ruta en ELLA misma» o no está marcada como local. |
| La publicación automática no se dispara | La instancia local no es WORKER, la casilla está desmarcada o el lote no terminó correctamente. |
| «El paquete requiere la app 3.6.0…» | Las dos máquinas deben estar en la misma versión o superior a la del paquete. |
| «Paquete dañado» | Algún fichero falta o cambió de tamaño tras publicar: vuelve a publicarlo. |
| Una cuenta no trae ficheros | No tenía carpeta en el trabajo de la laptop: se avisa al publicar («Sin carpeta descargada»). |


---

## Feat 7 · Cuenta que cambió de username (v3.7.0)

**Para qué sirve:** cuando una cuenta de Instagram cambia de nombre, lo resuelves **desde la app en un gesto**: se renombra (o se fusiona) la carpeta en `G:`, se actualiza la base de datos, el `accounts_lite` y la pantalla, **sin reiniciar la app**. El nombre antiguo queda como alias para no perder el historial.

> **Primera vez:** pruébalo con una cuenta de `10.TEMP` y luego **Deshacer** desde `Catálogo → Operaciones de disco…`. `G:` debe estar conectada.

### Dos casos

| Caso | Cuándo | Qué hace |
|---|---|---|
| **Renombrado simple** | No existe ninguna carpeta ni cuenta con el nombre nuevo | Renombra la carpeta. La cuenta **conserva su id interno** (la misma fila), cambia el username y el nombre antiguo pasa a alias. |
| **Fusión** | Ya existe `@nuevo` (típico: descargaste la cuenta con su nombre nuevo antes de enterarte) | Une las dos carpetas **sin perder ficheros** y deja una sola cuenta. |

### Cómo se hace — clic derecho en la cuenta → **Cambió de username…**

(también en el menú `Catálogo`). Escribe el username nuevo (sin @) y se abre la ventana de vista previa.

**En un renombrado simple** verás la acción *Renombrar* (de → a) y, si la cuenta tiene URLs de stories en lotes borrador, cuántas se actualizarán al nombre nuevo.

**En una fusión** además aparece:

| Elemento | Qué es |
|---|---|
| Tabla *Cuenta · Carpeta · Contenido · Último contenido* | Las dos cuentas, para decidir. |
| **Cuenta y carpeta que se conservan** | *Automático*: primero la ubicación que sigue en uso (no `09.DELETED`/`-Deleted`), luego la de más contenido. O elige *Esta cuenta* / *La que ya existe*. |
| Resumen | Ej.: «120 se mueven, 15 idénticos (se retiran del origen), 3 duplicados semánticos (a `_duplicates`), 2 con sufijo». |
| Casilla *Confirmo que son la misma cuenta* | Solo si falta el id de Instagram en una de las dos (no se puede comprobar). |

**Reglas de la fusión (nada se borra por error):**

| Situación del fichero | Qué pasa |
|---|---|
| Mismo nombre y mismo tamaño | Es idéntico: se retira del origen (queda el de la carpeta que se conserva). |
| Mismo nombre, otro tamaño | Se mueve con sufijo `_1`, `_2`… |
| Mismo id de publicación pero otro nombre | Duplicado: va a una carpeta `_duplicates` de la cuenta, **no se borra**. |
| Cualquier otro | Se mueve a la misma subcarpeta (story, reels, highlights…). |

**Bloqueos** (salen en rojo): los **ids de Instagram son distintos** (no se fusiona nunca), la cuenta está en un **lote en ejecución**, el username no es válido (letras, números, `.` y `_`, hasta 30), o `G:` no está disponible.

### Revisar ids repetidos — `Catálogo → Revisar ids repetidos…`

Lista las cuentas que comparten **el mismo id de Instagram** (probablemente la misma persona). Cada grupo trae una **pista**:

| Pista | Significa |
|---|---|
| **Renombrado probable** | Una está en uso y las otras archivadas (`09.DELETED`/`-Deleted`) o mucho más antiguas. |
| **Misma categoría** | Todas en la misma categoría: revisa y fusiona. |
| **Revisión manual** | Categorías distintas. |
| **Todas eliminadas** | Todas en `09.DELETED`: casi siempre se ignora. |

Botones: **Resolver…** (eliges cuál es el username **vigente** —la sugerida lleva ★— y se fusionan las demás en esa cuenta, una ventana de vista previa por cada una), **No es renombrado** (el grupo deja de aparecer) y **Actualizar**. Hoy tu base tiene 2 grupos.

### Nombres antiguos (alias)

* **Editor:** si escribes un username antiguo, la app pregunta «@viejo ahora es @nuevo — ¿usar @nuevo?». *No* significa que es otra cuenta con ese nombre. Si el nombre lo usaron varias cuentas, no adivina.
* **Organizar stories:** un fichero con el nombre antiguo se mueve a la cuenta actual y el resultado dice `MOVED_VIA_ALIAS` («@viejo ahora es @nuevo»).

### Deshacer — `Catálogo → Operaciones de disco…`

Selecciona la operación → **Deshacer**: carpetas, ficheros, username, alias y (en fusiones) la cuenta eliminada vuelven a su estado, con los **mismos id**. No se puede deshacer si: ya moviste esos ficheros, se unieron filas del **mismo lote**, o la cuenta volvió a cambiar de nombre (se explica el motivo).

### Cómo probarlo

1. Crea en `10.TEMP` una cuenta de prueba con una imagen. Clic derecho → **Cambió de username…** → `prueba2`: comprueba la carpeta, el árbol (sin reiniciar) y `Catálogo → Operaciones de disco…`.
2. En el editor escribe el nombre antiguo y comprueba el aviso «@viejo ahora es @nuevo».
3. **Deshacer** y comprueba que todo vuelve.
4. Fusión: con dos cuentas de prueba con el mismo id de Instagram, renombra una al nombre de la otra, revisa el resumen y ejecuta; luego **Deshacer**.
5. `Revisar ids repetidos…` → **Resolver…** con tus 2 grupos reales (empieza por el «renombrado probable»).

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «Los ids de Instagram son distintos» | No es la misma cuenta: no se fusiona. Si el id guardado es erróneo, corrígelo con *Update* en el editor. |
| Pide confirmar que son la misma cuenta | Falta el id en alguna: la app no puede comprobarlo; confirma solo si estás seguro. |
| «La fusión unió filas del mismo lote» al deshacer | Ya no se puede revertir automáticamente; restaura el backup si lo necesitas. |
| No sale en «ids repetidos» | Ya está resuelto, marcado como «No es renombrado», o falta el id de Instagram. |


---

## Feat 8 · Sincronizar con el disco (v3.8.0)

**Para qué sirve:** es tu **red de seguridad** por si alguna vez cambias algo en `G:` fuera de la app (con el Explorador). Detecta qué carpetas cambiaron y deja que la app las siga. **Sustituye a `sc1`** (`generatedirmap.py`): ya no necesitas ejecutarlo.

**Qué NO hace:** no mueve, renombra ni borra nada en el disco, y **nunca se ejecuta sola** (ni al abrir la app). Solo lee y actualiza la base de datos de la app.

> Si de ahora en adelante haces todo desde la app, casi nunca necesitarás esto: cada operación (mover, renombrar, borrar…) ya actualiza la base.

### Cómo es de rápida

En vez de leer los ~950 000 nombres de fichero (como `sc1 --complete`, unos 8 minutos), la app pregunta por la **fecha de modificación de cada carpeta de cuenta** (y de `story`, `reels`, `highlights`). Solo vuelve a leer las carpetas cuya fecha cambió. Con tus datos: **1 169 cuentas revisadas en medio segundo** (más en frío, por el disco USB).

### Dónde está — `Catálogo → Sincronizar con el disco`

| Opción | Qué hace |
|---|---|
| **Rápida (solo lo que cambió)** | Revisa todas las cuentas y relee solo las carpetas cambiadas; busca carpetas nuevas o ausentes. Es la que usarás. |
| **Verificar categoría seleccionada** | Lo mismo pero solo para una carpeta (selecciónala en la vista de árbol, o clic derecho → *Verificar categoría seleccionada*). |
| **Verificar cuenta seleccionada** | Una sola cuenta (clic derecho en la cuenta). Instantáneo. |
| **Verificación completa…** | Relee **todas** las carpetas aunque no hayan cambiado (equivale a `sc1 --complete`). Avisa del tiempo y pide confirmación. Úsala si dudas de los datos. |
| **Hallazgos de sincronización…** | Abre la lista de diferencias pendientes. |

También por consola: `python -m ig_orchestrator scan [--scope all|category|account] [--path 00.FAVORITES] [--account usuario] [--deep]`.

### La primera vez

Justo después de importar, la app **da por buena la importación**: solo anota la fecha de cada carpeta como punto de partida (por eso la primera «Rápida» es instantánea y dice «N tomadas como base»). Las cuentas **sin id de Instagram** sí se leen. A partir de ahí, cada sincronización relee solo lo que cambió. Si quieres comprobarlo todo desde cero: **Verificación completa**.

### Qué actualiza sola

* Los **contadores** (posts, reels, stories, highlights), la **fecha del último contenido**, el **id de Instagram si estaba vacío** y el **índice de ficheros** de las carpetas que cambiaron.
* Marca cada cuenta: `PRESENT`/`MISSING` (si la carpeta ya no está en disco).

### Hallazgos — lo que necesita tu decisión

Nunca se aplican solos. En `Hallazgos de sincronización…` selecciona y pulsa **Aceptar** (la app sigue al disco) o **Ignorar**.

| Hallazgo | Significa | «Aceptar» hace |
|---|---|---|
| **Carpeta nueva** | Hay una carpeta de cuenta en `G:` que la app no conoce. | Crea la cuenta como **archivada** (se lee en la próxima sincronización). |
| **Carpeta movida/renombrada** | Una cuenta conocida ya no está en su sitio y hay una carpeta con **el mismo username o el mismo id de Instagram** en otro. | Actualiza la ruta de la cuenta a la nueva. |
| **Carpeta ausente** | Una cuenta conocida ya no está en disco. | Nada: queda marcada como ausente (**no se borra la cuenta**). |
| **Id de Instagram distinto** | El id que hay en disco no es el que guarda la app. | Guarda el id del disco. |
| **Username repetido** | Hay dos carpetas con el mismo username. | Nada: resuélvelo con «Cambió de username…» (fusionar). |

Si hubo errores de lectura (disco USB con problemas), **no se marca ninguna cuenta como ausente** para evitar falsas alarmas. Con `G:` desconectada la sincronización está desactivada.

### Reglas (avanzado)

Las reglas heredadas de `sc1` ahora se pueden cambiar en la base (`app_settings`): `library.max_depth` (3), `library.media_subfolders` (`reels,story,highlights`), `library.media_extensions`, `library.non_account_names`.

### Cómo probarlo

1. `Catálogo → Sincronizar con el disco → Rápida`: la primera vez dice que tomó cuentas «como base»; debe terminar en segundos y sin hallazgos.
2. Repítela: debe leer **0 carpetas de cuentas** y no tener cambios.
3. En el Explorador crea una carpeta de cuenta con una imagen dentro (en una categoría de prueba como `10.TEMP`) y ejecuta *Rápida*: sale **Carpeta nueva**. *Aceptar* → aparece como cuenta archivada (`Ver → Mostrar biblioteca completa`).
4. Mueve una carpeta de cuenta con el Explorador y sincroniza: sale **Carpeta movida/renombrada**; *Aceptar* actualiza la ruta. (Muévela de vuelta después.)
5. Añade una foto a una cuenta y pulsa **Verificar cuenta**: los contadores se actualizan.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «La biblioteca (G:) no está disponible» | `G:` desconectada: no se puede sincronizar. |
| Una cuenta no se actualiza | Su fecha de carpeta no cambió (herramientas que no la tocan): usa **Verificar cuenta** o **Verificación completa**. |
| Muchas cuentas «con cambios» tras renombrar un lote | Normal por ahora: el renombrado antiguo no anota contadores; la sincronización rápida lo corrige en segundos. |
| Sale «Carpeta nueva» para algo que no es una cuenta | Una carpeta con ficheros multimedia sueltos cuenta como cuenta (igual que `sc1`): *Ignorar*. |


---

## Feat 9 · Renombrado integrado (v3.9.0)

**Para qué sirve:** el botón **Renombrar** ya no lanza el script externo `ManualRenameFiles` (`sc2`). Hace lo mismo **dentro de la app**, con el **mismo resultado** (está probado contra `sc2` con la misma semilla), pero con una **vista previa** donde ves cada fichero y su nombre nuevo antes de tocar nada, y usando solo la base de datos de la app (no `accounts_lite`).

> **Primera vez:** pruébalo con una descarga pequeña. La vista previa te enseña exactamente lo que se aplicará.

### Qué hace el renombrado (igual que `sc2`)

1. Para cada carpeta de cuenta descargada, mira los ficheros que ya hay en la biblioteca (`G:`) de esa cuenta.
2. Los ficheros descargados (`1234567890123.jpg`) cuyo **id ya existe** en la biblioteca son **duplicados**: se renombran `id_duplicated.jpg` (y se borran si marcas *Eliminar duplicados*).
3. El resto se agrupa por los 6 primeros dígitos del id y recibe una **fecha** interpolada entre los ficheros vecinos de la biblioteca (los más nuevos que el último, entre la fecha del último y tu fecha de inicio). Nombre final: `2026-10-10 14.22.07 3500...123_<idUsuario>_manual.jpg`.
4. Las **cuentas nuevas** reparten sus ficheros entre su *fecha de inicio* y la fecha del lote, con el id de propietario del lote.
5. La carpeta renombrada se **mueve a la biblioteca** (junto a la carpeta de la cuenta). Si ya existe, se fusiona sin sobrescribir; si algún nombre choca, esa cuenta no se mueve.

### Cómo se usa — botón **Renombrar** (igual que antes)

Se abre **Renombrar descargas**:

| Elemento | Qué es |
|---|---|
| **¿Dónde están los ficheros a renombrar?** | *Mi carpeta de trabajo* (por defecto), las carpetas de **otras instancias registradas** (descargas o compartida), o cualquier ruta con *Examinar…*. Así puedes renombrar directamente en la compartida de la laptop, sin traerla antes. |
| *Fecha de inicio* | La del lote (startNowDate); no se edita aquí. |
| **Eliminar duplicados** | Borra los `_duplicated` generados en esta ejecución. |
| **Mover a la biblioteca** | Mueve la carpeta de cada cuenta a su sitio en `G:`. Sin marcar, solo renombra. |
| **Vista previa** | Calcula todo **sin tocar el disco**: árbol *cuenta → fichero → nombre nuevo → fecha*, avisos y conflictos de movimiento. |
| **Otra semilla** | Los minutos y segundos de las fechas son aleatorios; con otra semilla salen otros. **Lo que ves es lo que se aplica.** |
| **Ejecutar** | Pide confirmación y renombra en segundo plano. |

En la lista, cada cuenta muestra su estado:

| Estado | Significa |
|---|---|
| **Renombrar** | Cuenta de la biblioteca: se renombrará y moverá (ves a qué carpeta). |
| **Cuenta nueva** | Estaba declarada como nueva en el lote: se registrará en la app. |
| **Omitida** | No se tocará. La razón sale en la línea: *no está registrada y no se declaró como nueva*, *la carpeta registrada no existe*, *declarada como nueva pero ya está registrada*, *no está como carpeta en el origen*. |
| `!` (aviso) | Por ejemplo, una subcarpeta (como `story`) que no existe en la biblioteca: no se renombra. |
| ✖ Conflicto al mover | Algún fichero choca con uno de la biblioteca: la carpeta se queda sin mover. |

### Al terminar

* La consola y un resumen muestran, por cuenta: renombrados, duplicados, eliminados y si se movió. Las cuentas con problemas salen en un aviso.
* Las **cuentas nuevas** quedan registradas **una sola vez en la app** (id de Instagram, fecha de inicio, carpeta) y, si el espejo está activo, también en `accounts_lite`.
* Los **contadores** y el **índice de ficheros** de cada cuenta movida se actualizan al momento (no hace falta «Sincronizar con el disco»).
* El lote se marca como completado si todo salió bien; si quedan carpetas sin mover, **Renombrar** sigue disponible.
* Cada ejecución queda guardada (historial `rename_runs`).
* Si pulsas **Detener** durante el renombrado, para **antes de la siguiente cuenta** (la que está en curso termina).

### Ajustes — dónde están

**`Ajustes → Procesamiento`:**

| Opción | Qué hace |
|---|---|
| **Motor de renombrado** | *Integrado en la app* (por defecto) o *Script externo ManualRenameFiles (sc2)* (como antes, por si quieres comparar o hay un problema). |
| **Mostrar siempre la vista previa antes de renombrar** | Desmárcalo para renombrar directo con el botón, sin ventana (no recomendado al principio). |

**`Ajustes → Catálogo` → «Mantener actualizado accounts_lite»** (la casilla que pedías):

| Casilla | Efecto |
|---|---|
| **Marcada** (por defecto) | Cada vez que la app mueve, renombra, marca como eliminada o registra una cuenta, también actualiza `accounts_lite`. Mantiene vivos `sc2` y el resto de herramientas antiguas. |
| **Desmarcada** | La app **deja de escribir** en `accounts_lite`. Hazlo cuando ya no uses ni `sc1` ni el motor externo `sc2`. |

> Recomendación: usa el renombrado integrado unas semanas; cuando confirmes que todo va bien, elige motor *Integrado* y **desmarca** «Mantener actualizado accounts_lite».

### Cómo probarlo

1. Deja un par de carpetas de cuentas descargadas en tu carpeta de trabajo (o prueba con la compartida de la laptop).
2. Pulsa **Renombrar** → comprueba la lista → pulsa **Vista previa** si cambias algo → revisa unos cuantos nombres y fechas.
3. **Ejecutar** y mira la consola. Abre una de las carpetas en `G:`: los ficheros nuevos terminan en `_manual`.
4. Comprueba que las descargas ya no están en la carpeta de trabajo y que las cuentas nuevas aparecen en el catálogo con su carpeta.
5. (Opcional) Compara con el motor externo en otra descarga: `Ajustes → Procesamiento → Script externo`.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «Omitida — no está registrada…» | La carpeta descargada se llama como una cuenta que la app no conoce. Declárala como cuenta nueva en el lote o impórtala/regístrala. |
| «Conflicto al mover» | Un fichero con el mismo nombre ya existe en la biblioteca. Revisa esa cuenta; nada se sobrescribe. |
| Los ficheros de `story`/`reels` no se renombran | Esa subcarpeta no existe aún en la biblioteca para esa cuenta (igual que en `sc2`). Se avisa en la vista previa. |
| «Contadores no actualizados» | Había una sincronización en curso; ejecuta *Sincronizar con el disco → Rápida*. |
| Quiero volver al script de siempre | `Ajustes → Procesamiento → Motor → Script externo`. |


---

## Feat 10 · Renombrar sin la unidad G: (v3.10.0)

**Para qué sirve:** renombrar aunque el disco `G:` esté apagado o desconectado. La app guarda en su base de datos lo que el renombrado necesita saber de tu biblioteca (id, fecha y propietario de cada fichero), así que ya no hace falta leer el disco.

### Cómo funciona

| Situación | Qué hace la app |
|---|---|
| `G:` conectada | Lee la carpeta de la cuenta del disco (exacto), igual que antes. |
| `G:` desconectada y la cuenta tiene índice | Usa el índice. Renombra **en la carpeta de descargas** y deja la cuenta como **pendiente de mover**. |
| `G:` desconectada y la cuenta **no** tiene índice | La cuenta se **omite** (`NO_INDEX`). Conecta `G:` o sincroniza esa cuenta una vez. |
| Cuenta nueva | No necesita índice; se mueve y se registra cuando `G:` vuelva. |

### Dónde está cada opción

* **Renombrar descargas** (botón *Renombrar*): casilla **«Usar el índice de la app»** (fuerza el índice aunque `G:` esté conectada). En la vista previa, las cuentas muestran «Referencia: índice» y «Pendiente de mover (biblioteca no disponible)».
* **Lote → Mover renombradas pendientes…**: cuando vuelvas a conectar `G:`, pulsa aquí. Lista las carpetas pendientes, pide confirmación, las mueve (fusionando sin sobrescribir), registra las cuentas nuevas y actualiza contadores e índice. Si `G:` sigue sin estar disponible, te avisa y no hace nada.
* **Catálogo → Verificar índice con el disco** (selecciona una cuenta antes): compara el índice de esa cuenta con sus carpetas. Si hay diferencias (ficheros añadidos o borrados fuera de la app) las lista y te pregunta si **aceptar el disco**, que vuelve a indexar la cuenta.

### Qué se guarda

El índice guarda solo lo necesario (id, fecha, propietario, extensión y sufijo), por **id de cuenta**: renombrar la cuenta o moverla de carpeta no lo rompe. Cada fichero que renombra la app entra al índice al momento; los cambios hechos fuera de la app entran al sincronizar con el disco.

### Cómo probarlo

1. Prepara una descarga con una cuenta que ya esté en el catálogo.
2. Desconecta `G:` (o prueba con una copia). Pulsa **Renombrar**: la vista previa muestra «Referencia: índice» y «Pendiente de mover».
3. **Ejecutar**: los ficheros quedan renombrados en la carpeta de descargas y la cuenta como pendiente.
4. Vuelve a conectar `G:` → **Lote → Mover renombradas pendientes…** → confirma. Comprueba que la carpeta está en `G:` con los mismos nombres.
5. **Catálogo → Verificar índice con el disco** sobre esa cuenta: debe decir que coincide.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «NO_INDEX» | La cuenta nunca se sincronizó/importó, así que no hay índice. Conecta `G:` y pulsa *Sincronizar con el disco → Cuenta*. |
| «Conflicto al mover» al mover pendientes | Algún fichero ya existe en `G:` con el mismo nombre. Nada se sobrescribe; la carpeta sigue pendiente. |
| El renombrado asignó fechas algo distintas a lo esperado | El índice estaba desactualizado (cambios hechos fuera de la app). Usa *Verificar índice* y acepta el disco. |


---

## Feat 11 · Almacén y volcado a G: (v3.11.0)

**Para qué sirve:** separar *renombrar* de *entregar a la biblioteca*. Renombras en el día a día y las cuentas esperan en un **almacén** (una carpeta local, por ejemplo en un disco rápido). Solo conectas `G:` cuando quieres **volcar** todo de una vez.

### 1) Configurar el almacén — `Ajustes → Catálogo`

| Campo | Qué es |
|---|---|
| **Almacén de procesadas (carpeta local)** | Dónde se guardan las cuentas ya renombradas hasta volcarlas. Si está vacío, el almacén no se ofrece. |
| **Tras renombrar** | *Preguntar siempre* (por defecto), *Dejar en el almacén* o *Mover a la biblioteca* como valor inicial de la ventana de Renombrar. |

### 2) Renombrar hacia el almacén — botón *Renombrar*

En la ventana, **Destino de las procesadas**: *Biblioteca (G:)* o *Almacén (volcar después)*. Si cambias cualquier opción, la vista previa se invalida: pulsa **Vista previa** otra vez antes de **Ejecutar**.
Con *Almacén*, cada cuenta se mueve a `almacén\categoría\grupo\cuenta` (la misma estructura que `G:`); la biblioteca no se toca. El lote queda completado igual: no espera al volcado.

### 3) Volcar — `Lote → Pendiente de volcar a G:…`

| Elemento | Qué hace |
|---|---|
| Lista | Cada cuenta del almacén con ficheros, tamaño y **destino**: *Nueva* (la carpeta no existe en `G:`), *Fusionar* (ya existe), *Conflicto* (algún nombre ya existe en `G:`), *Falta* (la carpeta ya no está en el almacén). |
| **Actualizar** | Recalcula la lista (útil tras conectar `G:`). La cabecera dice si la biblioteca está conectada. |
| **Volcar seleccionadas / Volcar todo** | Pide confirmación con el resumen y vuelca en segundo plano. Se puede cerrar la ventana; el progreso sale en la consola. |
| **Quitar volcadas de la lista** | Limpia del panel las cuentas ya volcadas. |

Cómo vuelca: copia cada fichero, comprueba que el tamaño coincide y solo entonces lo borra del almacén. **Nunca sobrescribe**: si un nombre ya existe, esa cuenta queda en *Conflicto* y no se toca.
Si se corta la luz o cierras la app a mitad, vuelve a abrir el panel y pulsa *Volcar*: continúa sin duplicar ni perder ficheros.
Después se actualizan contadores e índice; las cuentas nuevas reciben su carpeta en el catálogo (y en `accounts_lite` si el espejo está activo).
Si moviste o renombraste la cuenta en el catálogo mientras esperaba, el volcado la lleva a su sitio nuevo.

### Cómo probarlo

1. Configura el almacén en Ajustes → Catálogo.
2. Renombra una descarga con **Destino = Almacén**. Comprueba que `G:` no cambió y que en el almacén aparece la carpeta de la cuenta.
3. Abre **Lote → Pendiente de volcar a G:…**: verás la cuenta como *Fusionar* o *Nueva*.
4. Con `G:` conectada, **Volcar todo**. El almacén queda vacío y la cuenta tiene los ficheros nuevos en `G:`.
5. (Opcional) Desconecta `G:`: *Volcar* avisa de que la biblioteca no está disponible y no hace nada.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «No hay almacén configurado» | Indica la carpeta en Ajustes → Catálogo. |
| Cuenta en *Conflicto* | Un fichero con el mismo nombre ya existe en `G:`. Revisa y decide a mano; el almacén conserva el original. |
| «No hay espacio suficiente en el almacén» al renombrar | El disco del almacén no tiene sitio para esa cuenta; la cuenta se queda sin mover. |
| Una cuenta nueva almacenada no se renombra por segunda vez | Hasta volcarla no tiene carpeta en el catálogo; vuélcala primero. |


---

## Feat 12 · Catálogo avanzado (v3.12.0)

**Para qué sirve:** gestionar la biblioteca desde el árbol del catálogo, sin el Explorador ni editar SQLite a mano.

### Ficha de la cuenta — clic derecho → *Ficha de la cuenta…* (o Catálogo → Ficha de la cuenta…)

| Campo | Qué hacer |
|---|---|
| **Id de Instagram** | Solo dígitos. Avisa si otro registro ya tiene ese id o si los ficheros de la cuenta son mayoritariamente de otro id. **No renombra ficheros.** |
| **Fecha del primer post** | `AAAA-MM-DD`, no futura. La usa el renombrado de cuentas nuevas. |
| **Favorita / Notas** | Libres. |
| Solo lectura | Estado, carpeta, estado de disco, contadores, último contenido, nombres anteriores, últimos lotes y últimas operaciones. |

Si hay avisos (no errores) puedes **guardar de todos modos**; los errores bloquean el guardado.

### Seleccionar varias cuentas y moverlas

En el árbol (vista árbol) usa **Ctrl** o **Mayús** para seleccionar varias cuentas → clic derecho → **Mover cuentas seleccionadas** → elige la carpeta destino.
Sale **un único plan**: las cuentas que no se pueden mover (ya están allí, carpeta repetida, lote en ejecución…) se omiten con una nota. Todo se guarda como **un grupo** en el historial, así que **Deshacer** revierte todas a la vez.

### Arrastrar y soltar

Arrastra una o varias cuentas seleccionadas (o una carpeta) sobre otra carpeta del árbol. Se abre la **vista previa del plan**; hasta que no pulses *Ejecutar* no se mueve nada. Con *Esc* cancelas el arrastre.

### Abrir carpeta / Copiar ruta

Clic derecho en una cuenta. *Copiar ruta* copia la ruta de cada cuenta seleccionada (una por línea).

### Papelera — clic derecho → *Eliminar (a la papelera)…* y Catálogo → *Papelera…*

* **Eliminar** mueve la carpeta a `G:\4K Stogram\.trash\<fecha>__<usuario>` (instantáneo, no copia nada) y la cuenta queda como *Eliminada* sin carpeta. Antes te lista cuáles se eliminarán y cuáles **están bloqueadas** (en un lote en ejecución, con datos pendientes de volcar en el almacén, o con `G:` desconectada).
* **Papelera…** muestra lo que hay (ficheros, tamaño, fecha, sitio original). **Restaurar** devuelve la carpeta a su sitio original si sigue libre.
* **Eliminar definitivamente / Vaciar papelera…** borra de verdad. Te muestra el recuento y exige **escribir `ELIMINAR`**.

### Cómo probarlo

1. Selecciona dos cuentas con Ctrl → arrástralas sobre otra carpeta → revisa el plan → *Ejecutar*. Luego *Historial de operaciones → Deshacer*.
2. Abre la **Ficha** de una cuenta, cambia el id a uno que tenga otra cuenta y comprueba el aviso.
3. Elimina una cuenta de prueba (`10.TEMP`), mira que desaparece de `G:` y aparece en **Papelera…**, restáurala.

### Problemas típicos

| Síntoma | Causa |
|---|---|
| «Se omite: …» en el plan | Esa cuenta no puede moverse (mismo destino, carpeta repetida, lote en ejecución, sin carpeta). Las demás sí. |
| «El sitio original está ocupado» al restaurar | Hay otra carpeta con ese nombre; muévela o renómbrala y restaura de nuevo. |
| No puedo eliminar una cuenta | Está en un lote en ejecución, tiene datos en el almacén o `G:` no está conectada. |


---

## Feat 13 · Mover con sugerencias, búsqueda y selección múltiple (v3.13.0)

**Para qué sirve:** mover cuentas rápido, sobre todo entre `Modelo`, `Modelo-Deleted` y `Modelo-Inactive`, sin recorrer el árbol a mano, y mover varias a la vez.

### Mover varias cuentas
1. En el catálogo (vista árbol) selecciona varias cuentas con **Ctrl** o **Mayús**.
2. Clic derecho **dentro de la selección** → **Mover las N cuentas a otra carpeta…** (la selección se conserva).
3. Elige la carpeta (abajo) y revisa el plan: un solo plan, un solo grupo en el historial.

### El selector de carpeta
| Qué | Cómo se usa |
|---|---|
| **Sugerencias** | Hasta tres botones con la carpeta lógica de destino. Si la cuenta está en `Ana-Model` → `Ana-Model-Deleted`, `Ana-Model-Inactive` y la carpeta de eliminadas; si está en `Ana-Model-Deleted` → `Ana-Model` y `Ana-Model-Inactive`; si está en `-Inactive` → `Ana-Model` y `Ana-Model-Deleted`. Un clic elige. Si la carpeta sugerida no existe sale **Crear «…»**: confirma y se crea junto a la actual. |
| **Buscar carpeta** | Escribe `ana-model-del…`: el árbol salta a la carpeta. **Enter** pasa a la siguiente coincidencia. |
| **Nueva carpeta aquí…** | Selecciona la carpeta padre en el árbol, pulsa el botón, escribe el nombre: se crea y queda seleccionada. |
| **Elegir** / doble clic | Confirma la carpeta seleccionada en el árbol. |

### Cómo probarlo
1. Selecciona dos cuentas de `X-Model` → clic derecho → «Mover las 2 cuentas…» → clic en la sugerencia `X-Model-Deleted` → *Ejecutar*. Deshaz desde *Operaciones de disco*.
2. Abre el selector de una cuenta y escribe parte de un nombre de carpeta: el árbol debe saltar a ella.
3. Pulsa «Nueva carpeta aquí…» sobre una categoría y comprueba que aparece en `G:` y en el árbol.

### Problemas típicos
| Síntoma | Causa |
|---|---|
| No hay sugerencias | Las cuentas seleccionadas no tienen carpeta o están en carpetas distintas sin relación de nombre. Usa búsqueda o el árbol. |
| «Crear …» pide confirmación | La carpeta hermana (`-Deleted`/`-Inactive`) no existe todavía. |


---

## Feat 14 · Estado según carpeta, color único y ventanas centradas (v3.14.0)

### 1) El estado sigue a la carpeta
Al **mover** cuentas (clic derecho → *Mover…*, arrastrar y soltar, o mover una carpeta con cuentas):

| Situación | Resultado |
|---|---|
| Destino = carpeta `Nombre-Model-Deleted` (o la carpeta de eliminadas de Ajustes) y la cuenta no está eliminada | Pasa a **Eliminada** |
| La cuenta estaba **Eliminada** y se saca de una carpeta `-Deleted` | Se **reactiva** con el estado que tenía antes (Inactiva, Activa…); si no se sabe, Activa |
| Cualquier otro movimiento | Sin cambios de estado |

En la **vista previa del plan** verás las líneas «Estado: @cuenta → Eliminada / Reactivada» antes de pulsar *Ejecutar*. **Deshacer** (Catálogo → Operaciones de disco) devuelve también el estado. Renombrar una carpeta no cambia estados.

### 2) Color único
Las cuentas eliminadas (las antiguas y las nuevas) se ven del mismo rojo suave que *Disabled*. El color se cambia en Configuración → Interfaz (*Disabled*).

### 3) Ventanas centradas
Todas las ventanas se abren con su centro en el centro del monitor donde está la ventana principal, sea cual sea la resolución. Si tienes dos monitores, se centran en el de la ventana principal.

### Cómo probarlo
1. Mueve una cuenta de `X-Model` a `X-Model-Deleted` (usa la sugerencia): el plan avisa «Estado → Eliminada»; tras ejecutar, la fila queda roja.
2. Muévela de vuelta: «Reactivada»; vuelve a su color anterior.
3. Abre varias ventanas (Ajustes, Papelera, Operaciones de disco…): todas aparecen en el centro.

### Problemas típicos
| Síntoma | Causa |
|---|---|
| Moví fuera de la app (Explorador) y el estado no cambió | Solo los movimientos hechos desde la app cambian el estado; la sincronización no los toca. |
| La carpeta se llama `-Inactive` y la cuenta sigue activa | Desde v3.15 también cambia (ver Feat 15). Si usas una versión anterior, solo `-Deleted` lo hacía. |


---

## Feat 15 · El estado también sigue a las carpetas -Inactive (v3.15.0)

Completa el Feat 14: ahora **`-Inactive`** funciona igual que `-Deleted`.

| Al mover… | Resultado |
|---|---|
| …a `Nombre-Model-Deleted` o a la carpeta de eliminadas | **Eliminada** (rojo) |
| …a `Nombre-Model-Inactive` | **Inactiva** (amarillo). Si estaba Eliminada, deja de estarlo |
| …desde `-Deleted` o `-Inactive` a una carpeta normal | Vuelve al estado que tenía **antes** (o Activa si no se conoce) |
| …entre carpetas normales | Sin cambios (una cuenta Inactiva puesta a mano sigue Inactiva) |

La **vista previa del plan** lista «Estado: @cuenta → Inactiva / Eliminada / Reactivada» y **Deshacer** devuelve el estado.

### Cómo probarlo
1. Mueve una cuenta Activa de `X-Model` a `X-Model-Inactive` (sugerencia del selector): el plan avisa «→ Inactiva»; tras ejecutar, la fila queda amarilla.
2. Muévela de vuelta a `X-Model`: «Reactivada», vuelve a Activa.
3. Muévela de `X-Model-Deleted` a `X-Model-Inactive`: pasa de Eliminada a Inactiva.
4. Deshaz el último movimiento en *Operaciones de disco*: recupera su estado anterior.


---

## Feat 16 · Cierre de pendientes (v3.16.0)

### 1) Eliminar carpeta vacía
Clic derecho sobre una carpeta (vista árbol) → **Eliminar carpeta vacía…** → vista previa → *Ejecutar*.
* Solo funciona si **no hay ficheros** ni **cuentas** dentro (ni en sus subcarpetas). Si no, el plan se bloquea y te dice qué lo impide («Contiene 3 ficheros…», «Contiene 1 cuenta del catálogo: @ana»).
* Se borra en disco y del catálogo. **Deshacer** (Catálogo → Operaciones de disco) la vuelve a crear.

### 2) Papelera con caducidad y «quitar del catálogo»
* **Ajustes → Catálogo → «Papelera: días antes de ofrecer el borrado definitivo»**: con 30, lo que entra hoy caduca en 30 días (0 = nunca).
* **Catálogo → Papelera…**: columna *Caduca*, contador «N caducadas» y botón **Vaciar caducadas…** (pide escribir `ELIMINAR`). Al arrancar la app avisa en la consola si hay caducadas. **No borra nada sola.**
* Al borrar definitivamente pregunta **«¿Quitar también estas cuentas del catálogo?»**: *Sí* borra sus filas (se conservan las que están en algún lote); *No* las deja como «Eliminada» sin carpeta.

### 3) Auditoría del índice
**Catálogo → Auditar biblioteca…** muestra además `INDEX_MISSING` (hay ficheros según los contadores pero el índice está vacío: sincroniza esa cuenta) e `INDEX_STALE` (un contador no coincide con el índice, p. ej. «posts 120 vs índice 118»).

### 4) Almacén visible
Si hay cuentas esperando en el almacén, la barra de estado muestra `Almacén: N cuenta(s) · tamaño pendientes` y `· G: desconectada` si no está la biblioteca. Al arrancar con `G:` conectada, la consola recuerda que puedes volcar (*Lote → Pendiente de volcar a G:…*).

### Cómo probarlo
1. Crea una carpeta vacía en `10.TEMP` desde el menú y elimínala; deshaz la operación.
2. Pon retención 1 día, elimina una cuenta de prueba, abre la Papelera y comprueba la columna *Caduca*.
3. Renombra una descarga con destino *Almacén* y mira la barra de estado.
