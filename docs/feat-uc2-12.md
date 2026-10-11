# feat-uc2-12 — Catálogo avanzado: eliminar (con cuarentena), fusionar, editar ficha, arrastrar y multiselección

| | |
|---|---|
| **Dificultad** | 12 / 12 |
| **Cubre** | UC2 (fase 2: completa lo pedido) |
| **Riesgo** | Alto en la parte destructiva (eliminar); el resto reutiliza piezas ya probadas |
| **Dependencias** | `feat-uc2-4` (motor), `feat-uc1-3` (catálogo completo). Aprovecha `feat-problem1-7` (fusión) y `feat-uc3-8` (estado de disco) si ya existen |
| **Estimación** | 8–10 días (se puede entregar por entregas parciales: 12a, 12b, 12c) |

## Objetivo

Convertir el árbol del catálogo en una **herramienta de gestión de la biblioteca**: todo lo que hoy haces en el Explorador sobre las carpetas de cuentas
(mover, renombrar, borrar, fusionar) y todo lo que editas a mano en SQLite (ids, fechas) se hace desde la app, con vista previa, historial y deshacer.

## Valor que entrega por sí solo

- Eliminar carpetas **de forma recuperable**: van a una cuarentena en la propia unidad (instantáneo, sin copiar) con retención configurable y vaciado explícito.
- Fusionar dos carpetas/cuentas sin tocar el disco a mano.
- Editar la ficha de una cuenta (ids, fecha del primer post, notas…) con validaciones, en una sola pantalla.
- Mover varias cuentas a la vez (selección múltiple + arrastrar y soltar) con un único plan revisable.

## Entregas parciales sugeridas

| Entrega | Contenido | Utilidad |
|---|---|---|
| **12a** | Ficha editable + validaciones + multiselección + «Abrir carpeta / Copiar ruta» | Sustituye las ediciones manuales de SQLite |
| **12b** | Arrastrar y soltar + mover/renombrar en lote + atajos | Reorganizar la biblioteca cómodamente |
| **12c** | Cuarentena + eliminar + vaciar + fusionar genérico | Operaciones destructivas controladas |

## Estado actual (evidencia)

- El menú contextual tiene 6 acciones y ninguna toca disco (`gui/catalog/panel.py:190-207`); el `Treeview` es de selección única (`selectmode="browse"`).
- La ficha de una cuenta se edita en el editor de lotes (`gui/editor/panel.py`: Owner Id, First Post Date, Path) y solo para el lote en curso.
- No hay forma de ver ni corregir `instagram_user_id` global sin SQL.

## Diseño

### 12a — Ficha de cuenta

`gui/catalog/account_card.py` (diálogo/ panel lateral). Campos editables y su validación:

| Campo | Validación | Efectos |
|---|---|---|
| `instagram_user_id` | solo dígitos; aviso si otro `catalog_accounts` ya lo tiene (→ ofrece «Revisar ids repetidos…» de `feat-problem1-7`); aviso si difiere del `owner_id` mayoritario de los ficheros (`media_index`, si existe) | actualiza espejo `accounts_lite.ownerId` (mientras exista) |
| `start_init_date` | `YYYY-MM-DD`, no futura | usado por renombrado de cuentas nuevas |
| Estado / favorito | los existentes + `DELETED`/`ARCHIVED` | cambio de estado puro (si implica mover, se usa el flujo de `feat-problem1-5`) |
| Notas (nuevo `catalog_accounts.notes`) | texto libre | — |
| Carpeta/grupo | selector del árbol | genera un plan de movimiento (motor) |

Solo lectura en la ficha: `rel_path`, contadores, `last_media_at`, estado de disco, historial de nombres (`account_usernames`), últimas operaciones (`fs_operations`), lotes en los que participa.
Cambiar el id **no renombra ficheros** (el id vive en los nombres de fichero ya existentes; Q9) y la ficha lo indica.

Multiselección: el árbol pasa a `selectmode="extended"`; las acciones aplican a N cuentas generando **un plan con N pasos** y un único diálogo de vista previa.

### 12b — Arrastrar y soltar

Handlers `<B1-Motion>`/`<ButtonRelease-1>` en el `Treeview`: arrastrar cuentas (o carpetas) sobre una categoría/grupo → `plan_move(...)` → diálogo de vista previa → confirmar.
Indicador visual del destino y cancelación con `Esc`. Sin ejecución directa al soltar.

### 12c — Cuarentena, eliminar y fusionar

**Cuarentena** (`library/trash.py`):
- Carpeta `LIBRARY\.trash\<yyyymmdd_HHMMSS>__<username>\` (en el **mismo volumen** → `os.rename`, instantáneo).
  Añadir `.trash` a las carpetas «no-cuenta» del escáner (`library.non_account_names`).
- Tabla `trash_items(id, catalog_account_id, original_rel, trash_rel, bytes, files, deleted_at, expires_at, status)` (`QUARANTINED` / `RESTORED` / `PURGED`).
- La cuenta queda con `disk_state = TRASHED` (o se elimina la fila si el usuario elige «Eliminar también del catálogo»).
- **Restaurar** devuelve la carpeta a `original_rel` (si el hueco está libre).
- **Vaciar cuarentena…**: borrado real con recuento (ficheros/MB), confirmación escribiendo la palabra «ELIMINAR» y lista de lo que se borrará; se registra en `fs_operations`. Retención automática opcional (`trash.retention_days`, por defecto desactivada).
- Bloqueos: nunca se elimina una cuenta presente en un lote activo, con datos pendientes de volcar (`staged_accounts`) o sin G: conectada.

**Fusionar genérico** (`library/merge.py`, generaliza el caso B de `feat-problem1-7`): origen y destino cualquiera; mismas reglas (idéntico → omitir; mismo `media_id` → `_duplicates`; mismo nombre distinto tamaño → sufijo) con vista previa y manifiesto para deshacer.

### Historial y deshacer

Un único panel **Operaciones de disco** (de `feat-uc2-4`) con filtros y botón *Deshacer* para todas las operaciones nuevas (mover, renombrar, mover a cuarentena, restaurar, fusionar mientras sea reversible).

## Casos borde

- Selección que mezcla cuentas de distintas unidades o con distinto estado (bloqueada/offline): el plan indica cuáles se omiten.
- Arrastrar una carpeta sobre sí misma o sobre un descendiente: rechazado.
- Nombres duplicados al destino: el plan ofrece «renombrar con sufijo» o «fusionar».
- Cuarentena con nombres largos (>260): prefijo `\\?\`; el nombre usa el username truncado + hash corto.
- Espacio: la cuarentena no consume (mismo volumen); vaciarla libera espacio.
- `account_card`: ediciones concurrentes con una operación de disco en curso → solo lectura durante la operación.

## Pruebas

- `tests/gui/test_account_card.py`: validaciones, avisos, cambio de id con y sin conflicto, multiselección.
- `tests/library/test_trash.py`: cuarentena, restaurar con hueco libre/ocupado, vaciar, bloqueos, expiración.
- `tests/library/test_merge.py`: ver casos de `feat-problem1-7` + fusión entre categorías distintas.
- `tests/gui/test_catalog_dnd.py`: simulación de eventos de arrastre → plan correcto.
- Prueba manual con `10.TEMP` y con una copia de una categoría pequeña; intento deliberado de eliminar cuenta en lote activo.

## Criterios de aceptación

1. Editar `instagram_user_id` en la ficha actualiza `bdapp` y el espejo, y avisa si otro registro tiene el mismo id.
2. Mover 10 cuentas arrastrándolas produce un solo plan revisable y un solo grupo en el historial; «Deshacer» revierte las 10.
3. Eliminar una cuenta la envía a cuarentena en < 2 s y se puede restaurar; vaciar la cuarentena exige confirmación escrita.
4. Intentar eliminar una cuenta en un lote activo o con datos en el almacén queda bloqueado con explicación.
5. Ninguna operación deja `bdapp` y el disco en estados distintos tras un corte (cubierto por la recuperación de `feat-uc2-4`).

## Documentación a actualizar

`CHANGELOG.md`, `README.md`, `gui/catalog/MODULE.md`, `library/MODULE.md`, `tasks/done/`.

## Fuera de alcance / backlog

- `compareProcess` de `sc2` (comparar y reemplazar vídeos por tamaño): se **aparca**; si se quiere conservar, abrir un feat propio «Herramienta de comparación» (aislada del catálogo).
- Previsualización de medios en la propia app, etiquetas/colecciones, búsqueda por contenido.
