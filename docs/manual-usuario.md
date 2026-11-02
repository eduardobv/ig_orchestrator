# Manual de uso — ig_orchestrator (v3.12)

Referencia por pantalla y por opción de menú: **dónde está, qué hace y qué abre**. Para la explicación de cada novedad por separado y cómo probarla, ver `docs/tutorial-v3.md`.

> Convenciones: **Menú → Opción** = barra superior. «Clic derecho» = menú contextual. «Modal» = ventana que bloquea la principal hasta cerrarla.
> **G:** es la biblioteca (`G:\4K Stogram`). Muchas acciones de disco se desactivan si no está conectada.

---

## 1. Conceptos básicos

| Concepto | Qué es |
|---|---|
| **Catálogo** | Todas las cuentas de la biblioteca (una fila por cuenta en la base de datos de la app) y las carpetas donde viven. Se ve a la izquierda, en lista o en árbol. |
| **Lote** | Un conjunto de cuentas y URLs a descargar. Se edita a la derecha y se ejecuta con *Lote → Ejecutar*. |
| **Biblioteca (G:)** | El disco con las carpetas `categoría\grupo\cuenta`. La app la lee y la modifica, y guarda un índice de sus ficheros para poder trabajar sin ella. |
| **Almacén** | Carpeta local opcional donde esperan las cuentas ya renombradas hasta volcarlas a G:. |
| **Instancia** | Otro equipo (por ejemplo la laptop 24/7) que descarga y publica lotes. |
| **Papelera** | `G:\4K Stogram\.trash`: cuentas eliminadas recuperables. |

Estados de una cuenta: **Activa**, **Inactiva**, **Oculta (Disabled)**, **Cambiada**, **Archivada** (visible solo con *Ver → Mostrar biblioteca completa*), **Eliminada**.

---

## 2. Ventana principal

| Zona | Contenido |
|---|---|
| Barra de botones (iconos) | Nuevo lote, Registrar/actualizar, Lotes/ejecuciones, Ejecutar/Pausar/Reanudar (**un solo botón**: ▶ en reposo, ⏸ mientras corre el lote, ▶ al reanudar), Detener, Renombrar, Organizar stories y Traer carpetas de otra instancia (*pull*). *Renombrar manual* ya no está en la botonera: solo en *Lote → Renombrar manual*. Mismos atajos que los menús; cada icono tiene tooltip. |
| **Catálogo** (izquierda) | En vista árbol, casillas **Deleted** / **Inactive** (desmarcadas por defecto; ocultan esas carpetas solo en el árbol; la búsqueda las ignora y los selectores de carpeta siguen mostrándolas; también en el clic derecho de una carpeta). Filtro de búsqueda, botón pegar, cambio lista/árbol. Al refrescarse, el árbol conserva las carpetas expandidas y el scroll. Clic derecho: ver §5. El filtro busca por **username** (parte del nombre) o por **Owner ID**: pega el número (≥5 dígitos) de la página de Instagram y se muestra la cuenta cuyo Owner ID coincide exactamente, **entre todas las cuentas, también archivadas y eliminadas** aunque la vista no las muestre; el árbol abre su carpeta y la selecciona, y la barra de estado indica usuario y estado. Si no hay coincidencia, no pasa nada (los números no se toman como username). |
| **Editor** (derecha) | Datos de la cuenta que vas a añadir al lote (§4). |
| **Cuentas del lote actual** | Tabla de cuentas del lote con estado por colores; clic derecho (§6). |
| Consola / *Estado de ejecución* | Log en vivo (*Ver → Estado de ejecución…*): Copiar, Copiar todo, Limpiar. |
| Barra de estado | Mensaje actual, nº de cuentas e items del lote, el modo (*Nuevo lote*, *Editando lote*, *En ejecución*, *Histórico*) y, si hay cuentas esperando en el almacén, `Almacén: N cuenta(s) · tamaño pendientes` (y `· G: desconectada`). |

Colores del catálogo (configurables en Configuración → Interfaz): favorito, en lote, hoy, inactivo, disabled. Las cuentas **Eliminadas** usan el mismo color que *Disabled* (rojo suave).

**Ventanas:** todas las modales se abren centradas en el monitor de la ventana principal (cualquier resolución).

---

## 3. Menús de la barra superior

### Archivo

| Opción | Qué hace / qué abre |
|---|---|
| **Nuevo lote** | Limpia el editor y la tabla para empezar un lote nuevo (nombre y fecha por defecto). |
| **Registrar / actualizar lote** | Guarda el lote actual en la base de datos como borrador (DRAFT) o actualiza el existente. |
| **Lotes / ejecuciones…** | Modal con los lotes guardados y su estado (pendiente, en ejecución, completado, ejecutado en otra instancia…). Abrir, continuar o consultar un lote. |
| **Salir** | Cierra la app. |

### Edición

| Opción | Qué hace |
|---|---|
| **Pegar/Agregar** | Pega del portapapeles un username (y URLs) y lo añade/actualiza en el lote de una vez. |
| **Agregar/Actualizar** | Añade el contenido del editor al lote, o actualiza la cuenta si ya está. |
| **Pegar** | Pega URLs del portapapeles en el cuadro de URLs. Igual que **Ctrl+V** y *Pegar* del clic derecho: tras lo pegado añade un salto de línea, así la siguiente tanda empieza en línea nueva sin pulsar Enter. |
| **Copiar** (icono junto a *Pegar*) | En username, Owner Id, fecha del primer post y ruta: copia el valor del campo al portapapeles (vacío = no hace nada). |
| ~~Normalizar~~ | Oculto desde v3.25 (se usaba poco); la función sigue en el código. |
| **Limpiar editor** | Vacía los campos del editor. |
| **Eliminar selección / Eliminar todo** | Quita cuentas del lote actual (no toca el catálogo ni el disco). |

### Ver

| Opción | Qué hace |
|---|---|
| **Estado de ejecución…** | Abre/oculta la ventana de log. |
| **Catálogo en lista / en árbol** | Cambia la vista del catálogo. El **árbol** es necesario para las acciones sobre carpetas, selección múltiple y arrastrar. |
| **Mostrar biblioteca completa (archivadas)** | Incluye las cuentas archivadas (p. ej. importadas sin lote). Viene marcada por defecto y la app **recuerda** tu elección entre sesiones. |

### Lote

| Opción | Qué hace / qué abre |
|---|---|
| **Ejecutar** | Lanza el lote actual: envía URLs al bot de Telegram, espera descargas y las mueve a la carpeta de trabajo. Progreso en consola y tabla. |
| **Detener** | Detiene el proceso en curso (descarga o renombrado integrado; este último para antes de la siguiente cuenta). |
| **Pausar / Reanudar** (mismo botón que Ejecutar) | **Pausar** detiene el proceso y deja el lote en PARTIAL (el trabajo hecho se conserva); el icono pasa a *Reanudar* y continúa el mismo lote desde SQLite. |
| **Lotes / ejecuciones… > Reiniciar…** (botón y clic derecho, en Activos e Históricos) | Igual que *Reiniciar desde cero* pero sobre el lote seleccionado, en cualquier estado salvo GUARDADO y aunque la app se acabe de abrir. Avisa de que se pierde el estado actual y de que lo descargado se volverá a bajar (sufijo `_1`, `_2`… o pérdida si se limpian las carpetas); al confirmar reinicia y ejecuta. |
| **Lote > Reiniciar desde cero…** | Con el lote parado o pausado: tras confirmar, todas sus URLs y cuentas vuelven a pendiente (reintentos y errores a cero) y se ejecuta de nuevo desde el principio. Los archivos ya descargados no se borran (los nuevos llevan sufijo `_1`, `_2`…). Distinto de Reanudar, que continúa donde se quedó. |
| **Ejecutar tras Detener/Pausar** | Con un lote ya iniciado, Ejecutar lo **reanuda** (no intenta registrarlo de nuevo, así que no aparece «Batch name … already exists»). |
| **Lotes guardados y ejecuciones…** | Modal para organizar los lotes (ver «Modal» más abajo). |
| **Informe de ejecución…** | Abre el informe de tiempos del lote actual (o del último medido): resumen por fases, más lentos, tipos, errores, reintentos y recomendaciones; exporta a Markdown/CSV. |
| **Organizar stories…** | Modal *Stories Inbox*: elige la carpeta de entrada, *Guardar rutas* y *Ejecutar* para mover stories sueltas a la carpeta `story` de cada cuenta; al terminar muestra un **informe**: total movido, solo los ficheros con problema (duplicado, carpeta inexistente, cuenta no encontrada…), los ficheros que siguen en la carpeta (con nombre) o «carpeta vacía». **Forzar mover (sobrescribir)** reintenta los duplicados reemplazando el existente (pide confirmación). |
| **Traer descargas…** | Modal para traer carpetas descargadas por otra instancia (origen, destino, comparar con lote, *Escanear*, *Traer seleccionadas/todas*, *Importar paquetes*). |
| **Publicar descargas…** | (En una instancia worker) crea un paquete en la carpeta compartida con carpetas y resultados del lote; modo *Mover* o *Copiar*. |

#### Modal «Lotes guardados y ejecuciones»

Pestañas **Activos** (GUARDADO, en ejecución, POR RENOMBRAR) e **Históricos** (COMPLETED). Ya no existe la cola de ejecución. Al seleccionar un lote activo, abajo aparece **Cuentas del lote**: username, prio, URLs, stories y start date; haz clic en el título de cualquier columna para ordenar (otra vez para invertir).

| Elemento | Qué hace |
|---|---|
| **Nuevo lote** | Pide un nombre y crea un lote GUARDADO vacío. |
| **Cambiar nombre** | Cambia el nombre del lote seleccionado (único; no el lote que se está ejecutando). |
| **Borrar lote** | Borra un lote GUARDADO, vacío o con cuentas, o uno que nunca se inició (pide confirmación). Un lote con ejecuciones no se borra: usa *Finalizar sin renombrar*. |
| **Mover cuentas a…** | Con cuentas seleccionadas en la tabla de abajo: pide destino (un lote GUARDADO existente o **Nuevo lote…** con nombre sugerido). El destino debe ser GUARDADO. De un lote en ejecución solo se pueden mover cuentas sin empezar. Si la cuenta ya está en el destino, no se mueve nada. |
| **Importar / Exportar / Ejecutado en otra instancia** | Desde v4.22.0 están en la fila superior, junto a *Nuevo lote*, *Cambiar nombre* y *Borrar lote* (antes estaban abajo). Mismo comportamiento. |
| **Cargar** | (v4.22.0) Abre en la ventana principal el lote seleccionado, **sea cual sea su estado** (también PARTIAL, que no se puede Editar), sin ejecutarlo ni modificarlo: sirve para ver las URLs descargadas o completar cuentas. Va a la izquierda de *Editar*. Un lote POR RENOMBRAR queda listo para el botón Renombrar de la ventana principal. Con una ejecución en marcha no se permite. |
| **Sacar completadas…** | (v4.22.0) Con un lote **parado (PARTIAL)**: pide un nombre (sugerido `<lote>_LISTAS`) y mueve todas las cuentas COMPLETADAS a un lote nuevo **POR RENOMBRAR**, conservando Nueva / Update / Renew, URLs y su historial. Las incompletas se quedan en el lote original para reanudarlo. El lote nuevo se puede renombrar aquí o *Publicar descargas…* para que otra instancia lo traiga y renombre. No sirve si no hay completadas o si lo están todas (usa Renombrar). |
| **Editar** | Abre el lote GUARDADO en la ventana principal para modificarlo. |
| **Ejecutar** | Ejecuta (o reanuda) el lote seleccionado. Doble clic en la fila hace lo mismo. |
| **Renombrar** | Renombrado de ficheros de un lote POR RENOMBRAR. |
| **Finalizar sin renombrar** | Pasa el lote a COMPLETED sin renombrar. |
| **Clic derecho > Informe de ejecución…** | En cualquier lote de la lista: abre su informe de telemetría (ver *Lote > Informe de ejecución…*). |
| **Recuperar** (Históricos) | Devuelve a GUARDADO un lote del histórico **que nunca se inició**. Los que ya se ejecutaron solo se abren en lectura. |
| **Renombrar** | Modal **Renombrar descargas** (§7.1). Con el motor externo, lanza `ManualRenameFiles`. |
| **Mover renombradas pendientes…** | Mueve a G: las carpetas renombradas mientras G: no estaba disponible (§7.2). |
| **Pendiente de volcar a G:…** | Panel del almacén (§7.3). |
| **Renombrar manual** | Muestra el comando de renombrado externo para copiarlo (solo motor `sc2`). |

### Catálogo

| Opción | Qué hace / qué abre |
|---|---|
| **Abrir** | Carga la cuenta seleccionada en el editor. |
| **Favorito / Quitar favorito** | Marca o desmarca como favorita. |
| **Inactivo** | Cambia el estado a Inactiva. |
| **Ocultar** | Estado *Disabled*: deja de mostrarse como activa (no toca disco). |
| **Activar** | Vuelve a Activa. |
| **Sincronizar con el disco ▸** | **Rápida** (solo lo que cambió), **Verificar categoría seleccionada**, **Verificar cuenta seleccionada**, **Verificación completa…** (lee todas las carpetas; lento), **Hallazgos de sincronización…** (ver §8). |
| **Auditar biblioteca…** | Modal de auditoría: compara `accounts_lite`/`accounts_complete` con el disco y la app, y revisa el índice de ficheros (`INDEX_MISSING`: hay ficheros según los contadores pero ninguno indexado; `INDEX_STALE`: un contador difiere del índice); exporta Markdown/CSV. |
| **Ficha de la cuenta…** | Modal para editar id de Instagram, fecha del primer post, favorita, notas (§5.3). |
| **Papelera…** | Modal de la papelera (§5.5). |
| **Verificar índice con el disco** | Compara el índice de ficheros de la cuenta seleccionada con su carpeta (§8). |
| **Cambió de username…** | Renombra la cuenta (misma cuenta, nuevo username) o la fusiona con otra existente; renombra la carpeta. |
| **Revisar ids repetidos…** | Modal con cuentas distintas que comparten id de Instagram (probable cambio de username); *Resolver…* fusiona o *No es renombrado* las ignora. |
| **Marcar como eliminada… / varias… / Restaurar cuenta eliminada…** | Ciclo «eliminada en Instagram»: mueve la carpeta a su carpeta *-Deleted* o a la de eliminadas (modal con destino editable) y cambia el estado; restaurar lo deshace. |
| **Sugerir eliminadas…** | Lista cuentas que fallaron con «no encontrada» en ≥2 lotes. |
| **Etiquetar 09.DELETED…** | Marca como eliminadas las cuentas que ya están en esa carpeta (sin mover nada). |
| **Importar desde bdsc1…** | Modal de importación única desde `accounts_lite/complete` (*Simular* primero, luego *Importar*; hace copia de seguridad). |
| **Operaciones de disco…** | Historial de movimientos/renombrados/fusiones con **Deshacer** (§8). |

### Configuración

**Configuración…** abre la modal con pestañas (§9).

### Ayuda

**Acerca de**: versión de la app.

---

## 4. El editor del lote

| Campo | Para qué |
|---|---|
| **Lote / Fecha** | Nombre del lote (único; cuadro de 48 caracteres) y fecha de inicio (`startNowDate`, usada al renombrar). |
| **Username** | Cuenta a añadir. Botones: pegar y limpiar. A la derecha, **OwnerId:** muestra el id de Instagram de la cuenta (solo lectura, se puede seleccionar y copiar). |
| **URLs** | Una por línea. Si alguna es de una publicación de una **cuenta privada** (id muy largo, p. ej. `/p/Deh0qN5tt…/`), al Agregar sale un aviso, **no se agrega** la cuenta y se ofrece marcarla como privada; el contador muestra «privadas: N». |
| **Stories** (casilla) / **Priority** | Genera la story de la cuenta y/o la prioriza. |
| **New account** | Marca una cuenta nueva. Muestra *Datos de cuenta nueva*: **Owner Id**, **Fecha del primer post**, **Ruta** (carpeta de la biblioteca donde irá). La Ruta es un campo con sugerencias: escribe `models-d` y lista esa carpeta primero, luego su contenido y el resto por orden alfabético; vacío (o con ▾) muestra primero las contenedoras (`00.MODELS-A`, `00.MODELS-B`…) y luego las demás. Flechas ↑↓ + Enter, clic para elegir, Esc para cerrar. |
| **Update** | Cuenta existente: muestra *Datos de catálogo (Actualizar)* con sus datos actuales. |
| **Renew** (v4.17.0) | Cuenta ya registrada cuyos ficheros en `G:` no tienen el formato final. Pide solo la **Fecha del primer post**; Owner Id y ruta se mantienen. Al renombrar, los ficheros de `G:` cuyo nombre es solo el media id se juntan con los descargados y se renombran todos como si la cuenta fuera nueva (los de `G:` en su sitio; los descargados se mueven después). Cualquier otro nombre se ignora. Excluyente con *New account* y *Update*; necesita `G:` conectado. |

Si pegas un username que está *Eliminada*, la app avisa y pregunta si añadirla igualmente.

---

## 5. Menús contextuales del catálogo

### 5.1 Sobre una **cuenta** (fila de usuario)

| Opción | Qué hace |
|---|---|
El menú está dividido en seis grupos separados por líneas:

| Grupo | Opción | Qué hace |
|---|---|---|
| Ver | **Abrir** | Abre el perfil en Instagram y carga la cuenta en el editor. |
| Ver | **Ficha de la cuenta…** | Editar y copiar los datos de la cuenta (§5.3). **Es la forma de corregir un ownerId.** |
| Marcas | **Favorito / Quitar favorito** | Marca o desmarca favorita. |
| Marcas | **Marcar como privada / Quitar privada** | Cuenta privada de Instagram (el bot no descarga sus publicaciones). Se ve con **texto morado** en el catálogo. |
| Estado | **Activar** · **Inactivo** · **Ocultar** | Estado Activa / Inactive / Disabled. |
| Estado | **Marcar como eliminada… / Restaurar cuenta eliminada…** | Ciclo de «eliminada en Instagram». |
| Carpeta | **Abrir carpeta** | Abre la carpeta de la cuenta en el Explorador. |
| Carpeta | **Copiar ruta** | Copia la ruta completa (una por línea si hay varias). |
| Carpeta | **Mover a otra carpeta…** / **Mover las N cuentas a otra carpeta…** | Abre el **selector de carpeta destino** (§5.1.1). Con varias cuentas seleccionadas (Ctrl/Mayús; el clic derecho conserva la selección) el menú dice «Mover las N cuentas…». |
| Mantenimiento | **Verificar cuenta seleccionada** | Sincroniza esa cuenta con el disco. |
| Mantenimiento | **Cambió de username…** | Ver menú Catálogo. |
| Papelera | **Eliminar (a la papelera)…** | Envía la carpeta a la papelera (§5.5). |

**El estado sigue a la carpeta.** Al mover cuentas (o una carpeta con cuentas): si el destino es una carpeta `…-Deleted` (o la carpeta de eliminadas), las cuentas pasan a **Eliminada**; si es una carpeta `…-Inactive`, pasan a **Inactiva**; si salen de una de ellas hacia una carpeta normal, vuelven a su estado anterior (o Activa). La vista previa del plan lo avisa («Estado: @cuenta → Eliminada / Inactiva / Reactivada») y *Deshacer* lo revierte. Renombrar una carpeta no cambia estados.

#### 5.1.1 Selector de carpeta destino

| Zona | Qué hace |
|---|---|
| **Sugerencias** (hasta 3) | Carpetas «inversas» a donde está la cuenta: desde `X-Model` → `X-Model-Deleted`, `X-Model-Inactive` y la carpeta de eliminadas; desde `X-Model-Deleted` → `X-Model` y `X-Model-Inactive`; desde `X-Model-Inactive` → `X-Model` y `X-Model-Deleted`. También «donde estaba antes». Un clic elige la carpeta. Si la hermana no existe, aparece como **Crear «…»** (pide confirmación, la crea y la elige). |
| **Buscar carpeta** | Escribe parte del nombre: el árbol expande y selecciona la coincidencia. **Enter** o las flechas ↑↓ pasan a la siguiente; se indica «Coincidencia n de m». |
| **Árbol** | Todas las carpetas, también las archivadas. Doble clic o **Elegir** confirma la carpeta seleccionada. |
| **Nueva carpeta aquí…** | Crea una carpeta dentro de la seleccionada (en disco y catálogo, registrada en *Operaciones de disco*, se puede deshacer) y la selecciona. Si ya existe en el disco pero no está en el catálogo (p. ej. una carpeta vacía como `01.ACTIVE`), avisa y pregunta si **agregar la carpeta existente** al catálogo; nunca la reemplaza ni la borra. |

### 5.2 Sobre una **carpeta** (vista árbol)

| Opción | Qué hace |
|---|---|
| **Nueva carpeta…** | Crea una subcarpeta en disco **y** en el catálogo. |
| **Renombrar carpeta…** | Renombra en disco y actualiza las rutas de todas sus cuentas. |
| **Mover a…** | Mueve la carpeta (con sus cuentas) a otra. |
| **Eliminar carpeta vacía…** | Borra la carpeta (y sus subcarpetas) en disco y en el catálogo. **Solo** si no hay ficheros ni cuentas dentro; si no, el plan se bloquea y dice por qué. Con vista previa y *Deshacer*. |
| **Copiar ruta** | Copia al portapapeles la ruta completa de la carpeta en el disco. |
| **Verificar categoría seleccionada** | Sincroniza con el disco todas las cuentas de esa carpeta. |
| **Comprobar estado de las cuentas…** | Abre la modal *Estado de las cuentas* (ver 5.2b). |

Las acciones sobre carpetas son estas siete.
Todas las operaciones de disco muestran primero una **vista previa** (*Operación de disco*: acciones, de/a, cuentas y carpetas afectadas) y solo se ejecutan con **Ejecutar**.

### 5.2b Estado de las cuentas (modal)

Se abre con **Comprobar estado de las cuentas…** en una carpeta (por ejemplo `09.DELETED`). Consulta en Instagram, de una en una y con una espera entre cada una, si las cuentas de esa carpeta (y de sus subcarpetas) siguen existiendo.

* **Tabla:** *Usuario*, *Estado* (✔ existe, ✘ no existe, ? sin respuesta, … pendiente), *Analizada* (fecha y hora de la respuesta), *Movida* (`MOVED`, en rojo, si la cuenta ya no está en la carpeta donde se analizó), *Ruta destino* (dónde está ahora, solo si fue movida) y *Ruta origen*. Pulsa la cabecera de cada columna para ordenar (otra vez para invertir). El selector **Mostrar** filtra por estado.
* **Análisis:** el desplegable lista los análisis guardados de esa carpeta (número, fecha, estado, total). **Nuevo análisis** toma una foto de las cuentas actuales; **Eliminar análisis** borra solo el análisis, nunca carpetas.
* **Iniciar / Reanudar:** comprueba las cuentas pendientes (las ya respondidas no se repiten; las «?» se reintentan). **Detener** para en cuanto termina la consulta en curso. Si Instagram responde **429**, la comprobación se detiene sola y avisa; el progreso queda guardado y se reanuda más tarde (sube la espera en *Configuración > Ejecución > Estado de cuentas de Instagram*).
* **Cuentas ya analizadas (reutilización):** al pulsar *Nuevo análisis*, las cuentas que otro análisis ya respondió en las últimas N horas (*Configuración > Catálogo*, 48 h por defecto) salen ya con su resultado y su fecha en *Analizada* (`(#12)` = análisis de origen) y **no se vuelven a consultar**; solo se consultan las que faltan o son más antiguas. Para volver a consultar también las ya analizadas, marca **Re-analizar las ya analizadas en otros análisis** y pulsa *Iniciar/Reanudar*.
* **Seleccionadas: N:** contador de filas seleccionadas (al lado de *Mostrar*). Las cuentas ya movidas no se pueden seleccionar y todos los botones de mover las ignoran; el filtro *Movidas* las muestra.
* **Mover no existentes:** selecciona de una vez todas las ✘ que no se hayan movido y abre el mismo flujo que *Mover seleccionadas…*.
* **Mover seleccionadas…:** elige una o varias filas (o **Seleccionar todas**, con el filtro puesto si solo quieres las ✘ o las ✔) y abre el selector de destino con sugerencias, búsqueda y *Nueva carpeta aquí*; después muestra la vista previa de la operación de disco. Se puede mover con el análisis parcial. Con muchas cuentas la preparación tarda (se mira el disco de cada una): la modal muestra «Preparando el movimiento…» con barra animada y no se puede cerrar hasta terminar.
* **Doble clic sobre una cuenta:** abre su perfil de Instagram en el navegador (atajo de *Abrir en el navegador*).
* **Clic derecho sobre una cuenta:** *Abrir en el navegador* (su perfil de Instagram) y *Abrir en el explorador* (su carpeta en la biblioteca).
* Cerrar la modal con una comprobación en marcha pregunta si detenerla; el análisis no se pierde.

Menú **Catálogo > Revisar análisis de estado…** abre esta misma modal con **todos** los análisis guardados de cualquier carpeta (para revisarlos o mover cuentas más tarde); desde ahí no se puede crear un análisis nuevo (eso se hace con clic derecho en la carpeta).

### 5.3 Ficha de la cuenta (modal)

Todos los campos se pueden seleccionar y tienen un botón **Copiar**; **Copiar todo** deja un resumen de la cuenta en el portapapeles.

| Campo | Efecto |
|---|---|
| **Username** | Editable. Si lo cambias, al guardar se abre el flujo de **cambio de username** (vista previa; necesita G: conectada). |
| **Id de Instagram** | Solo dígitos. Avisa si otro registro tiene el mismo id, o si los ficheros de la cuenta son mayoritariamente de otro id. **No renombra ficheros.** |
| **Fecha del primer post** | `AAAA-MM-DD`, no futura. La usa el renombrado de cuentas nuevas. |
| **Favorita / Cuenta privada / Notas** | Libres. |
| **Ruta completa en disco** | Ruta absoluta de la carpeta de la cuenta (solo lectura, copiable). |
| Solo lectura | Estado, ruta relativa, estado de disco, contadores (posts/reels/stories/highlights), último contenido, nombres anteriores, últimos lotes y operaciones. |

*Guardar* valida; los errores bloquean, los avisos permiten «guardar de todos modos». Actualiza también `accounts_lite` si el espejo está activo.

### 5.4 Arrastrar y soltar

En el árbol, arrastra una o varias cuentas seleccionadas (o una carpeta) sobre otra carpeta: se abre la vista previa del plan; hasta pulsar **Ejecutar** no se mueve nada. No se mezclan cuentas y carpetas en un mismo arrastre.

### 5.5 Papelera

| Acción | Qué hace |
|---|---|
| **Eliminar (a la papelera)…** | Mueve la carpeta a `.trash\<fecha>__<usuario>` (instantáneo, mismo disco). La cuenta queda como *Eliminada* y sin carpeta. Bloqueada si está en un lote en ejecución, tiene datos pendientes en el almacén o G: no está disponible. |
| **Catálogo → Papelera…** | Lista lo eliminado (ficheros, tamaño, fecha, **caducidad**, sitio original). **Restaurar** devuelve la carpeta si su sitio sigue libre. **Eliminar definitivamente / Vaciar papelera… / Vaciar caducadas…** borra de verdad y exige escribir `ELIMINAR`; después pregunta si quitar también las cuentas del **catálogo** (se conservan las que estén en algún lote). La caducidad se configura en Ajustes → Catálogo; la app **nunca borra sola**, solo avisa. |

Para quitar una cuenta del **catálogo y del disco**: *Eliminar (a la papelera)…* y después *Papelera… → Vaciar* (la carpeta se borra de G:). La fila de la cuenta queda en el catálogo como *Eliminada* (no se borra de la base de datos).

### 5.5b Barra de desplazamiento

El catálogo (lista y árbol) tiene una barra vertical siempre visible a la derecha: arrástrala o haz clic para subir/bajar rápido sin la rueda del ratón.

### 5.6 Vista lista

Clic derecho sobre un nombre: mismo menú de cuenta (las acciones de carpeta y la selección múltiple requieren la vista árbol).

---

## 6. Tabla «Cuentas del lote actual»

| Elemento | Qué hace |
|---|---|
| Doble clic | **Abre el perfil de la cuenta en Chrome** (como *Abrir en Chrome*). Antes abría *Ver URLs…*; ahora está en el clic derecho. |
| Clic derecho → **Abrir en Chrome** | Abre `instagram.com/<usuario>/` en una pestaña nueva de Chrome (o del navegador por defecto si no hay Chrome). |
| Clic derecho → **Completar** | Marca la cuenta como completada manualmente. |
| Clic derecho → **Completar por http…** (v4.21.0) | Con el bot caído: descarga por HTTP los posts y reels que faltan de la cuenta, en cualquier estado. Pide *Descargar todas* o *Solo las primeras N* y la *Espera entre URLs* (solo para esa ejecución, no se guarda). El avance sale en la barra de estado. **Desde v4.23.0** la modal muestra en vivo «N URLs × X s = duración · terminaría hacia las HH:MM» (se recalcula al cambiar *todas*, *N* o la espera, y cada 15 s); cuenta solo la espera, no lo que tarda cada descarga. Requiere la sesión de *Configuración > Ejecución > Sesión HTTP* y que no haya ejecución en marcha. |
| Clic derecho → **Pausar (mover a lote guardado)…** | Selecciona una o varias cuentas **sin empezar** (estado pendiente, ninguna URL enviada) —también con el lote en ejecución— y pide confirmación. Las cuentas salen del lote y pasan a un lote **GUARDADO** (borrador) llamado `<lote>_PAUSA` (se amplía si ya existe; `_PAUSA2`… si el nombre está ocupado). El lote actual se da por terminado sin ellas y queda listo para renombrar; el lote guardado se ejecuta después desde *Lotes guardados*. Deshabilitado si alguna cuenta ya empezó o si pausarías todas. |
| Clic derecho → **Mover a nuevo lote guardado…** | Igual que *Pausar* (mismas condiciones: cuentas sin empezar, también con el lote en ejecución) pero **pregunta el nombre** del lote GUARDADO destino. Propone `<lote>_PARTE2` (o `_PARTE3`… si está usado); si escribes el nombre de un borrador existente, las cuentas se añaden a él. Rechaza el nombre del propio lote, el de un lote ya no borrador o un nombre vacío. |
| **Ver URLs pendientes…** (v4.21.0) | Igual que las siguientes, pero con todas las URLs que no están completadas, sea cual sea su estado (450 URLs y 200 completadas → 250). Incluye **Descargar por HTTP**. |
| **Ver URLs completadas / en reintento / fallidas…** | Modal con las URLs de ese estado; clic derecho en una URL: **Copiar**, **Abrir en Chrome**, **Copiar todas**. En *completadas*, *en reintento* y *pendientes* hay además selección múltiple y el botón **Descargar por HTTP** (v4.20.0): descarga las URLs elegidas (solo posts y reels) con la sesión de *Configuración > Ejecución > Sesión HTTP*, una cada 30 s (la franja nocturna usa su pausa), mostrando el avance; **Detener HTTP** la corta. La tabla se refresca sola y las URLs que se completan desaparecen de *en reintento*. En *completadas* pide confirmación (se vuelven a descargar; los archivos existentes se conservan). |
| **Abrir carpeta** | Abre la carpeta de descargas de la cuenta. |
| Botón **Eliminar** | Quita la cuenta del lote. |
| Colores | Verde = completada, ámbar = reintento, azul = procesando, gris = pendiente, rojo = fallida. |

---

## 7. Renombrar, mover y volcar

### 7.1 Renombrar descargas (modal)

| Elemento | Qué hace |
|---|---|
| **¿Dónde están los ficheros?** | Mi carpeta de trabajo, carpetas de instancias registradas, o cualquier ruta (*Examinar…*). |
| **Eliminar duplicados** | Borra los `_duplicated`. |
| **Mover a la biblioteca** | Mueve cada carpeta renombrada a su sitio. |
| **Usar el índice de la app** | Usa el índice en lugar de leer G:. Automático si G: no está. |
| **Destino de las procesadas** | *Biblioteca (G:)* o *Almacén (volcar después)*. |
| **Vista previa / Otra semilla** | Calcula todo sin tocar nada (árbol cuenta → fichero → nombre nuevo → fecha). Cualquier cambio de opción invalida la vista previa. |
| **Ejecutar** | Confirma y renombra en segundo plano; resumen por cuenta. Si la unidad de la biblioteca (G:) **no está conectada**, antes de empezar sale una modal: «se renombrará pero no se moverá a G:». **Aceptar** renombra las carpetas en su sitio (quedan pendientes de mover); **Cancelar** no hace nada. |

Estados: *Renombrar*, *Cuenta nueva*, *Renew* (cuenta existente renombrada otra vez desde la fecha del primer post; ficheros de `G:` solo-id + descargados), *Omitida* (con motivo), aviso `!`, *Conflicto al mover*, *Pendiente de mover*, *Referencia: índice*.

### 7.2 Mover renombradas pendientes
Con G: conectada, mueve las carpetas que se renombraron mientras no estaba. Nunca sobrescribe; un choque deja esa cuenta pendiente.

### 7.3 Pendiente de volcar a G: (almacén)
Lista del almacén: ficheros, tamaño, destino (*Nueva*, *Fusionar*, *Conflicto*, *Falta*) y estado. **Actualizar**, **Volcar seleccionadas**, **Volcar todo**, **Quitar volcadas de la lista**. Copia, verifica el tamaño y solo entonces borra del almacén; reanudable.

---

## 8. Sincronizar con el disco, índice, hallazgos y operaciones

**Qué detecta la sincronización:** carpetas de cuenta nuevas, movidas o ausentes; cambios de id de Instagram; cambios en el contenido (contadores, último contenido e índice de ficheros). Es incremental (mira las fechas de las carpetas).

| Opción | Cuándo usarla |
|---|---|
| **Rápida** | Tras trabajar fuera de la app. |
| **Verificar categoría / cuenta seleccionada** | Cuando sabes dónde cambió algo. |
| **Verificación completa…** | Si dudas de todo; minutos. |
| **Hallazgos de sincronización…** | Modal con *Carpeta nueva*, *Carpeta movida/renombrada*, *Carpeta ausente*, *Id de Instagram distinto*, *Username repetido*. **Aceptar** hace que la app siga al disco; **Ignorar** lo descarta. |
| **Verificar índice con el disco** | Compara el índice de ficheros de una cuenta con su carpeta; lista altas/bajas y permite *aceptar el disco*. |
| **Operaciones de disco…** | Historial con filtros y **Deshacer** (revierte disco y app; un grupo entero a la vez). |

### Añadir ficheros a mano
No existe «Analizar carpeta» como opción propia: se usa la **sincronización**.
- Si la carpeta de una cuenta **ya está en el catálogo** y añades ficheros, *Rápida* o *Verificar cuenta* actualizan sus contadores, su último contenido y el índice.
- Si es una carpeta **nueva** con ficheros multimedia, la sincronización genera un hallazgo **Carpeta nueva**; al **Aceptar** se crea la cuenta (como *Archivada*) y la siguiente sincronización lee sus ficheros y su id. Una carpeta vacía no se considera cuenta.

---

## 9. Configuración (modal con pestañas)

| Pestaña | Opciones principales |
|---|---|
| **General** | Idioma (reinicia la app). |
| **Interfaz** | Colores del catálogo, posición de la ventana principal (izquierda/centro/derecha) y *Guardar posición*. |
| **Ejecución** | Todos los ajustes de la descarga, agrupados (pasa el ratón sobre cada uno para ver su ayuda; se aplican a la **próxima ejecución**): *Orden del lote* (*Priorizar stories (dos barridas)*: primero las stories —cuentas con prioridad, luego por orden de alta— y después posts/reels/highlights de la cuenta con menos URLs a la que más); *Reintentos* (cola global de reintentos al final del lote, máximo general, máximo para stories, para «Media not found», para «sin respuesta del bot», espera base y máxima); *Bot y descargas* (plazos de primera respuesta por tipo —reel/post, story, carrusel, highlights—, **pausa entre URLs** —2 s—, **detectar bot sin respuesta** y espera antes de probar de nuevo —10 s—, plazo sin mensajes nuevos, cómo dar por terminada una URL —por conteo/descripción o por silencio—, silencio breve, silencio para dar por terminado en modo antiguo, recibir por eventos, consulta de respaldo, descargas simultáneas, carpeta de descarga propia con botón «…»); *Vigilante de Telegram Desktop*; *Reels grandes* (descarga por enlace: activar, plazos, tamaño máximo); *Comprobación en Instagram*; *Estado de cuentas de Instagram* (espera entre cuentas —30 s— y plazo de cada consulta, para la modal 5.2b); *Telethon* (esperas automáticas de Telegram); *Descarga de respaldo por HTTP*, *Franja nocturna*, *Bot caído* y *Sesión HTTP* (v4.20.0, ver «Descarga de respaldo por HTTP» más abajo; la sesión incluye el botón **Probar sesión**); *Telemetría* (nivel y días de retención; botón *Purgar telemetría…* que borra todo lo medido). **Prioridad:** esta pestaña > `.env` > valor por defecto; solo se guardan los valores que cambias, y **Restablecer valores** borra lo guardado. Un valor no válido se rechaza al pulsar *Guardar* y no se guarda nada. |
| **Procesamiento** | **Motor de renombrado** (integrado o script externo) y **vista previa siempre**; *Vaciar tabla de ficheros descargados*. |
| **Catálogo** | Carpeta de cuentas eliminadas y *Conservar la carpeta de grupo*; **Mantener actualizado accounts_lite**; **Almacén** (carpeta local) y **Tras renombrar** (preguntar / almacén / biblioteca); **Papelera: días de retención** (0 = sin límite); **Estado de cuentas: reutilizar análisis de las últimas N horas** (48 = 2 días; 0 = no reutilizar). |
| **Notificaciones** | Aviso al terminar un lote: activar, destino, plantilla, errores del bot que avisan, *Enviar prueba*. **Para que suene en el móvil** rellena *Token del bot* y *Chat ID* (crea un bot con @BotFather → `/newbot`, pulsa Start en él y abre `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver tu `chat.id`). Sin esos campos el aviso va a «Mensajes guardados» por tu propia cuenta y **no suena**. |
| **Instancias** | Registro de equipos: nombre, rol, es-local, carpeta de descargas, carpeta compartida (ruta desde este PC y en la propia), notas; *Añadir / Editar / Eliminar / Probar*. |

---

## 10. Preguntas frecuentes

**¿Cómo sabe la app que una carpeta está vacía?** Al deshacer la creación de una carpeta se usa el borrado de carpeta vacía del sistema operativo: solo se elimina si **no contiene nada** (ni ficheros ni subcarpetas). No se mira ningún `media_id`.

**¿Cómo cambio un ownerId equivocado?** Clic derecho en la cuenta → **Ficha de la cuenta…** → campo *Id de Instagram* → *Guardar*. No renombra ficheros. Si varias cuentas comparten id: *Catálogo → Revisar ids repetidos…*.

**¿Cómo elimino una cuenta del catálogo y del disco?** *Eliminar (a la papelera)…* y luego *Papelera… → Vaciar*.

**¿Cómo elimino una carpeta vacía?** Clic derecho sobre la carpeta (vista árbol) → **Eliminar carpeta vacía…**. Si tiene ficheros o cuentas, no se puede (el plan explica por qué).

**G: está apagada, ¿qué puedo hacer?** Descargar, renombrar (con índice) y dejar en el almacén o pendiente de mover; ver, filtrar y editar fichas. No se pueden mover/eliminar/sincronizar carpetas.


## Replicar el código en otra instancia (v4.18.0, dos partes desde v4.18.1)

No es una opción de la GUI; son dos dobles clics. **Parte 1, en este PC:** detén el batch de la instancia y ejecuta `inst_sync\empujar.bat` (la ruta de la instancia, vista desde este PC, está en `inst_sync\destino.txt`). Copia por red el código que cambió y avisa al final si además hay que ejecutar la parte 2 o si no hace falta; si todo coincide dice «Instancia sincronizada con el PC» y no mueve nada, por muchas veces que lo ejecutes. **Parte 2, en la instancia (solo si la parte 1 lo pide):** `inst_sync\sincronizar.bat` instala las dependencias, aplica los SQL pendientes y migra la base. Ambos aceptan `--simular` (solo informan).

## Descarga de respaldo por HTTP y bot caído (v4.20.0)

Cuando el bot no responde a un post o reel, la app puede descargarlo directamente de Instagram.

* **Configurar la sesión (una vez por instancia):** entra en instagram.com con Chrome, abre F12 > Application > Cookies > instagram.com y copia el valor de `sessionid` en *Configuración > Ejecución > Sesión HTTP*; pulsa **Probar sesión**. Puede ser de otra cuenta distinta a la tuya (mejor una secundaria). Si caduca, la app lo avisa con el mensaje *«cookie caducada: vuelve a entrar en Instagram y copia la nueva…»* y no vuelve a intentar HTTP en esa ejecución.
* **Qué hace en un lote:** si el bot no responde a una URL tras 2 intentos, se baja por HTTP (una petición cada 30 s). Tras 3 URLs seguidas así en una cuenta, se deja de preguntar al bot en esa cuenta y se pasa a otra; al final se terminan por HTTP. De 00:00 a 06:00 la pausa sube a 5 min.
* **Bot caído:** si varias URLs seguidas no responden, se envía la URL de prueba; si tampoco responde, se descarga por HTTP (1 cada 2 min) en bloques de 1 h, comprobando de nuevo el bot tras cada bloque. Si no vuelve tras 6 bloques, las cuentas pendientes pasan a **FAILED** y la ejecución termina para que decidas.
* La barra de estado muestra *«HTTP: …»* con lo que está pasando. Todos los valores son ajustes de *Configuración > Ejecución* (secciones nuevas), válidos desde la próxima ejecución.

## Pausa entre URLs y bot sin respuesta (v4.16.0)

* **Pausa entre URLs:** *Configuración > Ejecución > Bot y descargas > Pausa entre URLs (s)* (2 por defecto, 0 = sin pausa). La app espera ese tiempo entre una URL terminada y el envío de la siguiente, para no saturar al bot en cuentas con cientos de URLs.
* **Bot sin respuesta:** si el bot no contesta a una URL, la app espera *Espera antes de probar de nuevo (s)* (10) y envía otra (la siguiente o, si no queda ninguna, la misma). Si esa sí recibe respuesta, la anterior queda en la cola de reintentos. Si **tampoco** contesta, la **barra de estado** muestra *«Bot sin respuesta: en espera (no se envían más URLs hasta que conteste)…»* y la app no envía nada más hasta que el bot responda (puede ser minutos u horas; para salir usa **Pausar** o **Detener**). Al responder, recoge el contenido de las dos URLs, aunque lleguen desordenadas, y continúa con normalidad (*«El bot volvió a responder; se continúa.»*).
* Se desactiva con la casilla *Detectar bot sin respuesta* (entonces una URL sin respuesta va directa a reintentos, como antes). Los cambios se aplican a la **próxima ejecución**.
