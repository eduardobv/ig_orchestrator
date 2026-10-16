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
| Barra de botones (iconos) | Nuevo lote, Registrar/actualizar, Lotes/ejecuciones, Ejecutar, Detener, Pausar/Reanudar, Renombrar, Renombrar manual, Organizar stories (mismos atajos que los menús; cada icono tiene tooltip). |
| **Catálogo** (izquierda) | Filtro de búsqueda, botón pegar, cambio lista/árbol. Clic derecho: ver §5. |
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
| **Pegar** | Pega URLs del portapapeles en el cuadro de URLs. |
| **Normalizar** | Limpia y deduplica las URLs del editor. |
| **Limpiar editor** | Vacía los campos del editor. |
| **Eliminar selección / Eliminar todo** | Quita cuentas del lote actual (no toca el catálogo ni el disco). |

### Ver

| Opción | Qué hace |
|---|---|
| **Estado de ejecución…** | Abre/oculta la ventana de log. |
| **Catálogo en lista / en árbol** | Cambia la vista del catálogo. El **árbol** es necesario para las acciones sobre carpetas, selección múltiple y arrastrar. |
| **Mostrar biblioteca completa (archivadas)** | Incluye las cuentas archivadas (p. ej. importadas sin lote). |

### Lote

| Opción | Qué hace / qué abre |
|---|---|
| **Ejecutar** | Lanza el lote actual: envía URLs al bot de Telegram, espera descargas y las mueve a la carpeta de trabajo. Progreso en consola y tabla. |
| **Detener** | Detiene el proceso en curso (descarga o renombrado integrado; este último para antes de la siguiente cuenta). |
| **Pausar / Reanudar** | Con una cola, pausa/reanuda la secuencia. Con un lote suelto, **Pausar** detiene el proceso y deja el lote en PARTIAL (el trabajo hecho se conserva); el icono pasa a *Reanudar* y continúa el mismo lote desde SQLite. |
| **Ejecutar tras Detener/Pausar** | Con un lote ya iniciado, Ejecutar lo **reanuda** (no intenta registrarlo de nuevo, así que no aparece «Batch name … already exists»). |
| **Organizar stories…** | Modal *Stories Inbox*: elige la carpeta de entrada, *Guardar rutas* y *Ejecutar* para mover stories sueltas a la carpeta `story` de cada cuenta; muestra un log de movimientos. |
| **Traer descargas…** | Modal para traer carpetas descargadas por otra instancia (origen, destino, comparar con lote, *Escanear*, *Traer seleccionadas/todas*, *Importar paquetes*). |
| **Publicar descargas…** | (En una instancia worker) crea un paquete en la carpeta compartida con carpetas y resultados del lote; modo *Mover* o *Copiar*. |
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
| **Lote / Fecha** | Nombre del lote (único) y fecha de inicio (`startNowDate`, usada al renombrar). |
| **Username** | Cuenta a añadir. Botones: pegar y limpiar. |
| **URLs** | Una por línea. |
| **Stories** (casilla) / **Priority** | Genera la story de la cuenta y/o la prioriza. |
| **New account** | Marca una cuenta nueva. Muestra *Datos de cuenta nueva*: **Owner Id**, **Fecha del primer post**, **Ruta** (carpeta de la biblioteca donde irá). |
| **Update** | Cuenta existente: muestra *Datos de catálogo (Actualizar)* con sus datos actuales. |

Si pegas un username que está *Eliminada*, la app avisa y pregunta si añadirla igualmente.

---

## 5. Menús contextuales del catálogo

### 5.1 Sobre una **cuenta** (fila de usuario)

| Opción | Qué hace |
|---|---|
| **Abrir** | Carga la cuenta en el editor. |
| **Inactivo / Favorito / Quitar favorito** | Cambia estado/favorita. |
| **Ocultar / Activar** | Estado Disabled / Activa. |
| **Ficha de la cuenta…** | Editar id de Instagram y datos (§5.3). **Es la forma de corregir un ownerId.** |
| **Mover a otra carpeta…** / **Mover las N cuentas a otra carpeta…** | Abre el **selector de carpeta destino** (§5.1.1). Con varias cuentas seleccionadas (Ctrl/Mayús; el clic derecho conserva la selección) el menú dice «Mover las N cuentas…» y se mueven en un solo plan. Muestra el plan antes de ejecutar. |
| **Abrir carpeta** | Abre la carpeta de la cuenta en el Explorador. |
| **Copiar ruta** | Copia la ruta (una por línea si hay varias). |
| **Eliminar (a la papelera)…** | Envía la carpeta a la papelera (§5.5). |
| **Verificar cuenta seleccionada** | Sincroniza esa cuenta con el disco. |
| **Cambió de username…** | Ver menú Catálogo. |
| **Marcar como eliminada… / Restaurar cuenta eliminada…** | Ciclo de «eliminada en Instagram». |

**El estado sigue a la carpeta.** Al mover cuentas (o una carpeta con cuentas): si el destino es una carpeta `…-Deleted` (o la carpeta de eliminadas), las cuentas pasan a **Eliminada**; si es una carpeta `…-Inactive`, pasan a **Inactiva**; si salen de una de ellas hacia una carpeta normal, vuelven a su estado anterior (o Activa). La vista previa del plan lo avisa («Estado: @cuenta → Eliminada / Inactiva / Reactivada») y *Deshacer* lo revierte. Renombrar una carpeta no cambia estados.

#### 5.1.1 Selector de carpeta destino

| Zona | Qué hace |
|---|---|
| **Sugerencias** (hasta 3) | Carpetas «inversas» a donde está la cuenta: desde `X-Model` → `X-Model-Deleted`, `X-Model-Inactive` y la carpeta de eliminadas; desde `X-Model-Deleted` → `X-Model` y `X-Model-Inactive`; desde `X-Model-Inactive` → `X-Model` y `X-Model-Deleted`. También «donde estaba antes». Un clic elige la carpeta. Si la hermana no existe, aparece como **Crear «…»** (pide confirmación, la crea y la elige). |
| **Buscar carpeta** | Escribe parte del nombre: el árbol expande y selecciona la coincidencia. **Enter** o las flechas ↑↓ pasan a la siguiente; se indica «Coincidencia n de m». |
| **Árbol** | Todas las carpetas, también las archivadas. Doble clic o **Elegir** confirma la carpeta seleccionada. |
| **Nueva carpeta aquí…** | Crea una carpeta dentro de la seleccionada (en disco y catálogo, registrada en *Operaciones de disco*, se puede deshacer) y la selecciona. |

### 5.2 Sobre una **carpeta** (vista árbol)

| Opción | Qué hace |
|---|---|
| **Nueva carpeta…** | Crea una subcarpeta en disco **y** en el catálogo. |
| **Renombrar carpeta…** | Renombra en disco y actualiza las rutas de todas sus cuentas. |
| **Mover a…** | Mueve la carpeta (con sus cuentas) a otra. |
| **Eliminar carpeta vacía…** | Borra la carpeta (y sus subcarpetas) en disco y en el catálogo. **Solo** si no hay ficheros ni cuentas dentro; si no, el plan se bloquea y dice por qué. Con vista previa y *Deshacer*. |
| **Verificar categoría seleccionada** | Sincroniza con el disco todas las cuentas de esa carpeta. |

Las acciones sobre carpetas son estas cinco.
Todas las operaciones de disco muestran primero una **vista previa** (*Operación de disco*: acciones, de/a, cuentas y carpetas afectadas) y solo se ejecutan con **Ejecutar**.

### 5.3 Ficha de la cuenta (modal)

| Campo | Efecto |
|---|---|
| **Id de Instagram** | Solo dígitos. Avisa si otro registro tiene el mismo id, o si los ficheros de la cuenta son mayoritariamente de otro id. **No renombra ficheros.** |
| **Fecha del primer post** | `AAAA-MM-DD`, no futura. La usa el renombrado de cuentas nuevas. |
| **Favorita / Notas** | Libres. |
| Solo lectura | Estado, carpeta, estado de disco, contadores (posts/reels/stories/highlights), último contenido, nombres anteriores, últimos lotes y operaciones. |

*Guardar* valida; los errores bloquean, los avisos permiten «guardar de todos modos». Actualiza también `accounts_lite` si el espejo está activo.

### 5.4 Arrastrar y soltar

En el árbol, arrastra una o varias cuentas seleccionadas (o una carpeta) sobre otra carpeta: se abre la vista previa del plan; hasta pulsar **Ejecutar** no se mueve nada. No se mezclan cuentas y carpetas en un mismo arrastre.

### 5.5 Papelera

| Acción | Qué hace |
|---|---|
| **Eliminar (a la papelera)…** | Mueve la carpeta a `.trash\<fecha>__<usuario>` (instantáneo, mismo disco). La cuenta queda como *Eliminada* y sin carpeta. Bloqueada si está en un lote en ejecución, tiene datos pendientes en el almacén o G: no está disponible. |
| **Catálogo → Papelera…** | Lista lo eliminado (ficheros, tamaño, fecha, **caducidad**, sitio original). **Restaurar** devuelve la carpeta si su sitio sigue libre. **Eliminar definitivamente / Vaciar papelera… / Vaciar caducadas…** borra de verdad y exige escribir `ELIMINAR`; después pregunta si quitar también las cuentas del **catálogo** (se conservan las que estén en algún lote). La caducidad se configura en Ajustes → Catálogo; la app **nunca borra sola**, solo avisa. |

Para quitar una cuenta del **catálogo y del disco**: *Eliminar (a la papelera)…* y después *Papelera… → Vaciar* (la carpeta se borra de G:). La fila de la cuenta queda en el catálogo como *Eliminada* (no se borra de la base de datos).

### 5.6 Vista lista

Clic derecho sobre un nombre: mismo menú de cuenta (las acciones de carpeta y la selección múltiple requieren la vista árbol).

---

## 6. Tabla «Cuentas del lote actual»

| Elemento | Qué hace |
|---|---|
| Doble clic | *Ver URLs…* de la cuenta (problemáticas). |
| Clic derecho → **Completar** | Marca la cuenta como completada manualmente. |
| Clic derecho → **Pausar (mover a lote guardado)…** | Selecciona una o varias cuentas **sin empezar** (estado pendiente, ninguna URL enviada) —también con el lote en ejecución— y pide confirmación. Las cuentas salen del lote y pasan a un lote **GUARDADO** (borrador) llamado `<lote>_PAUSA` (se amplía si ya existe; `_PAUSA2`… si el nombre está ocupado). El lote actual se da por terminado sin ellas y queda listo para renombrar; el lote guardado se ejecuta después desde *Lotes guardados*. Deshabilitado si alguna cuenta ya empezó o si pausarías todas. |
| **Ver URLs completadas / en reintento / fallidas…** | Modal con las URLs de ese estado; clic derecho en una URL: **Copiar**, **Abrir en Chrome**, **Copiar todas**. |
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
| **Ejecutar** | Confirma y renombra en segundo plano; resumen por cuenta. |

Estados: *Renombrar*, *Cuenta nueva*, *Omitida* (con motivo), aviso `!`, *Conflicto al mover*, *Pendiente de mover*, *Referencia: índice*.

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
| **Procesamiento** | *Priorizar stories (dos barridas)*; **Motor de renombrado** (integrado o script externo) y **vista previa siempre**; *Vaciar tabla de ficheros descargados*. |
| **Catálogo** | Carpeta de cuentas eliminadas y *Conservar la carpeta de grupo*; **Mantener actualizado accounts_lite**; **Almacén** (carpeta local) y **Tras renombrar** (preguntar / almacén / biblioteca); **Papelera: días de retención** (0 = sin límite). |
| **Notificaciones** | Aviso por Telegram al terminar un lote: activar, destino, plantilla, errores del bot que avisan, *Enviar prueba*. |
| **Instancias** | Registro de equipos: nombre, rol, es-local, carpeta de descargas, carpeta compartida (ruta desde este PC y en la propia), notas; *Añadir / Editar / Eliminar / Probar*. |

---

## 10. Preguntas frecuentes

**¿Cómo sabe la app que una carpeta está vacía?** Al deshacer la creación de una carpeta se usa el borrado de carpeta vacía del sistema operativo: solo se elimina si **no contiene nada** (ni ficheros ni subcarpetas). No se mira ningún `media_id`.

**¿Cómo cambio un ownerId equivocado?** Clic derecho en la cuenta → **Ficha de la cuenta…** → campo *Id de Instagram* → *Guardar*. No renombra ficheros. Si varias cuentas comparten id: *Catálogo → Revisar ids repetidos…*.

**¿Cómo elimino una cuenta del catálogo y del disco?** *Eliminar (a la papelera)…* y luego *Papelera… → Vaciar*.

**¿Cómo elimino una carpeta vacía?** Clic derecho sobre la carpeta (vista árbol) → **Eliminar carpeta vacía…**. Si tiene ficheros o cuentas, no se puede (el plan explica por qué).

**G: está apagada, ¿qué puedo hacer?** Descargar, renombrar (con índice) y dejar en el almacén o pendiente de mover; ver, filtrar y editar fichas. No se pueden mover/eliminar/sincronizar carpetas.
