# feat-uc4-2 — Traer descargas desde una carpeta de intercambio

| | |
|---|---|
| **Dificultad** | 2 / 12 |
| **Cubre** | UC4 (parte «pc1 recoge») · proceso manual M1 |
| **Riesgo** | Bajo: solo mueve/copia carpetas de descarga; no toca la biblioteca ni `bdsc1` |
| **Dependencias** | Ninguna (mejora con `feat-uc4-6`, que automatiza el lado de `inst1`) |
| **Estimación** | 2–3 días |

## Objetivo

Eliminar el paso manual «copiar de `tmp` a `Telegram_Desktop`»: desde pc1, un diálogo de la app **trae** las carpetas de cuenta
que `inst1` dejó en la carpeta compartida (`\\DESKTOP-OM856P7\ig_orchestrator\tmp`) a la carpeta de trabajo local
(`WORKING_FOLDER`), con comprobaciones, progreso y reanudación, y deja el lote listo para renombrar.

## Valor que entrega por sí solo

- Tu flujo diario baja de 6 pasos a 3: **Traer → Ejecutado en otra instancia → Renombrar**.
- Seguridad: verifica tamaños, no sobrescribe, no mueve carpetas que `inst1` aún está escribiendo.
- Visibilidad: «el lote tenía 15 cuentas, han llegado 12; faltan: …» **antes** de marcarlo como ejecutado.

## Estado actual (evidencia)

- No hay concepto de carpeta de intercambio; `path_roots` solo tiene `TELEGRAM_DESKTOP`, `WORKING` y `FINAL_BASE` (vacío).
- `Ajustes` (`gui/settings/dialog.py`) no permite editar rutas: viven en `.env` y en `sc2/config.json`.
- «Ejecutado en otra instancia» se invoca desde el diálogo de lotes (`gui/batches/dialog.py:435`) y marca las URLs como `FAILED_FINAL`.
- `sc2` en modo `newRename` **no acepta** `--manualFolder` (`config.py:194`), por eso este feat **trae los ficheros a `WORKING_FOLDER`**
  en lugar de renombrar «desde donde estén». Renombrar desde cualquier carpeta llega con `feat-uc1-9`.

## Diseño

### Registro de instancias (BD) — actualizado 2026-10-11

En lugar de una única ruta de intercambio, la app mantiene un **registro de instancias** con sus rutas. La instancia local se marca como principal o secundaria.

```sql
CREATE TABLE IF NOT EXISTS instances (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,            -- 'inst1', 'pc1'
    role TEXT NOT NULL,                   -- MAIN | WORKER
    is_local INTEGER NOT NULL DEFAULT 0,  -- exactamente una fila local
    working_path TEXT,                    -- carpeta de descargas de ESA instancia (ruta local de ella)
    exchange_path TEXT,                   -- carpeta compartida accesible desde la instancia principal (UNC o unidad)
    exchange_local_path TEXT,             -- la misma carpeta vista desde ella misma
    app_version TEXT, last_seen_at TEXT, notes TEXT);
```

Ejemplo: `inst1` → `working_path = C:\Users\eduba\Downloads\DW\Telegram_Desktop`, `exchange_path = \\DESKTOP-OM856P7\ig_orchestrator\tmp`, `exchange_local_path = C:\Eduardo\ig_orchestrator\tmp`.
`WORKING` de la instancia local sigue viniendo de `.env`/`path_roots`.

Nueva pestaña **Ajustes → Instancias** (en `gui/settings/dialog.py`): alta/edición/baja, botón «Probar» (existencia, escritura, espacio libre) y estado (accesible/no). Sin migración destructiva: `CREATE TABLE IF NOT EXISTS`.
El diálogo de «Traer» (abajo) lista las instancias registradas como orígenes, y `feat-uc4-6`/`feat-uc1-9` reutilizan este registro (publicar, importar, renombrar desde su carpeta).

### Módulo sin Tk

```
src/ig_orchestrator/exchange/
    inbox_scan.py   # scan_exchange(root, *, stable_seconds) -> list[ExchangeFolder]
    pull.py         # plan_pull(folders, dest_root, policy) -> PullPlan ; execute_pull(plan, progress_cb, cancel_event) -> PullResult
    MODULE.md
```

- `ExchangeFolder`: `name`, `path`, `file_count`, `total_bytes`, `newest_mtime`, `is_stable`.
  `is_stable` = ningún fichero modificado en los últimos `DOWNLOAD_STABLE_SECONDS`×3 (ya existe el ajuste) → evita traer carpetas a medias.
- Política de conflicto por carpeta destino ya existente (restos en `Telegram_Desktop`):
  1. `merge_skip_identical` (por defecto): añade ficheros que no existen; mismo nombre + mismo tamaño → se omite y cuenta como duplicado;
     mismo nombre + distinto tamaño → sufijo `_1`, `_2` (misma convención que `filesystem/file_mover._safe_destination`).
  2. `abort`.
- Copia **verificada**: `copy2` a un temporal `*.part` en destino → comprobar tamaño → `os.replace` → borrar origen (si «mover»).
  Una caída de red deja `.part` huérfanos; el siguiente intento los limpia y reanuda por fichero.
- Opción «Conservar copia en origen» (por defecto desactivada).
- Cancelación y progreso por fichero/bytes (`threading.Event`, mismo patrón que `ProcessRunner`).

### UI

1. **`Lote → Traer descargas…`** (`gui/chrome/menubar.py`, cascada `menu.batch`, junto a «Renombrar») y botón en el diálogo de lotes.
2. Diálogo `gui/exchange/pull_dialog.py`:
   - Cabecera: **selector de instancia** (origen = `exchange_path` de la instancia elegida, o su `working_path` si es accesible por red) + ruta editable + «Examinar…».
   - Destino: la carpeta de trabajo de la instancia local (`WORKING`).
   - Tabla: ☐ Carpeta · Ficheros · MB · Estado (`Lista` / `En uso` / `Ya existe en destino` / `Vacía`).
   - Selector **«Comparar con lote»** (opcional): muestra *cuentas del lote recibidas / faltantes / sobrantes* usando
     `batch_accounts` + `catalog_accounts.username` (comparación sin mayúsculas).
   - Botones: **Traer seleccionadas**, **Traer todas las listas**, Cancelar.
3. Al terminar: ofrece (no impone) «Marcar este lote como *Ejecutado en otra instancia*» llamando a la función existente
   `mark_batch_executed_elsewhere` y, en la misma ventana, «Renombrar ahora».
4. Aviso al pulsar **Renombrar** si `WORKING_FOLDER` está vacío y `EXCHANGE` contiene carpetas estables: «¿Traer descargas primero?».

### Registro

Cada ejecución escribe en el log de la sesión (`logs/<ts>/exchange.log`) y en la consola de la GUI: carpeta, ficheros, bytes, omitidos, errores.
No se crea tabla nueva (el diario formal llega con `feat-uc2-4`).

## Casos borde

- Compartida inaccesible (inst1 apagada) → mensaje claro, sin bloquear la GUI (comprobación en hilo con timeout de 8 s).
- Carpeta con la misma cuenta en minúsculas/mayúsculas distintas → comparar con `casefold`.
- Cuenta presente en origen **y** en `Telegram_Desktop` (restos de un renombrado fallido) → política `merge_skip_identical`.
- Rutas > 260 caracteres → usar prefijo `\\?\` en las operaciones.
- Espacio libre insuficiente en destino → comprobación previa con `shutil.disk_usage`.

## Pruebas

- `tests/exchange/test_inbox_scan.py`: estabilidad por `mtime` (con `os.utime`), carpetas vacías.
- `tests/exchange/test_pull.py`: mover, copiar, conflicto con mismo/distinto tamaño, cancelación a mitad, `.part` huérfano, origen que desaparece.
- `tests/gui/test_pull_dialog.py`: construcción y estados de la tabla con un backend falso.
- Manual: traer 1 carpeta real pequeña desde `\\DESKTOP-OM856P7\ig_orchestrator\tmp` y comprobar que `Renombrar` sigue funcionando.

## Criterios de aceptación

1. Traer una carpeta de 1 000 ficheros desde la compartida no pierde ni duplica ficheros (comparación de listados con tamaño).
2. Una carpeta con ficheros modificados hace < 30 s aparece como «En uso» y no se selecciona por defecto.
3. Cancelar deja el origen intacto y el destino sin ficheros a medias.
4. Con la compartida apagada la GUI responde y muestra el motivo.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (flujo de dos instancias), `gui/settings/MODULE.md`, nuevo `exchange/MODULE.md`, `tasks/done/`.

## Fuera de alcance

Automatizar el lado de `inst1` (→ `feat-uc4-6`); renombrar sin pasar por `WORKING_FOLDER` (→ `feat-uc1-9`).

## Resultado de la implementación (2026-10-11, v3.2.0)

- Implementado según el diseño. Desviaciones: «Renombrar ahora» no se ofrece dentro del diálogo; tras marcar el lote se avisa «ya puedes pulsar Renombrar» (el estado de renombrado vive en la ventana principal).
- El registro `instances` se guarda al instante desde su pestaña (no depende de «Guardar» de Ajustes).
- El destino es siempre `WORKING_FOLDER` de la instancia local (`.env`).
- Pendiente de prueba manual real: traer una carpeta pequeña desde `\DESKTOP-OM856P7\ig_orchestrator	mp`.
