# feat-uc4-6 — Instancia 24/7: publicación automática + manifiesto de resultados

| | |
|---|---|
| **Dificultad** | 6 / 12 |
| **Cubre** | UC4 (parte «inst1 entrega») · proceso manual M1 · corrige el parche «Ejecutado en otra instancia» |
| **Riesgo** | Medio: toca el final del flujo de lotes y crea un formato de intercambio versionado |
| **Dependencias** | `feat-uc4-2` (reutiliza `exchange/pull.py` y el diálogo). Si no existe, este feat incluye una versión mínima del diálogo de importación |
| **Estimación** | 5–6 días |

## Objetivo

Que `inst1` **entregue sola** lo que descarga: al terminar el trabajo deja en la carpeta compartida un **paquete** (ficheros + `manifest.json` con los
resultados reales de cada URL) y que pc1 lo **importe fielmente** (estados reales, no «fallido: ejecutado en otra instancia»), listo para renombrar.

## Valor que entrega por sí solo

- Se acabó entrar por escritorio remoto para copiar carpetas: `inst1` publica sola al terminar.
- pc1 recibe información verdadera: qué URLs funcionaron, cuáles fallaron y por qué, cuántos ficheros por cuenta, qué cuentas eran nuevas y con qué parámetros de renombrado.
- Se detiene la contaminación de datos: hoy **18 651 de 25 226 URLs (74 %)** están `FAILED_FINAL` por «Executed on another instance» (`v3-status.md` §3.2).
- Recuperación ante cortes: el paquete es atómico; si `inst1` se apaga a mitad, no aparece como «listo».

## Estado actual (evidencia)

- `inst1` tiene su propia `orchestrator_gui.sqlite` y su `.env`; el código se copia a mano (carpeta `src` de `inst1` fechada 2026-09-13).
- `mark_batch_executed_elsewhere` (`gui/batches/resume.py:477`) pone `FAILED_FINAL` a todo lo pendiente y `COMPLETED` a las cuentas.
- Existe export/import de lotes (`gui/batches/transfer.py`, formato `ig_orchestrator.batch_export` v1) pero **solo transporta la definición** (cuentas, URLs, parámetros), no resultados ni ficheros.
- `Settings` no distingue roles; `EXCHANGE` aparece en `feat-uc4-2`.

## Diseño

### Ajustes de instancia

Nombre y rol salen del **registro de instancias** (`instances`, creado en `feat-uc4-2`; fila `is_local = 1`). El resto, en `app_settings`:

| Clave | Valores | Por defecto |
|---|---|---|
| `instance.role` (reflejo de `instances.role`) | `MAIN` · `WORKER` | `MAIN` |
| `exchange.auto_publish` | 0/1 (solo `WORKER`) | 0 |
| `exchange.publish_mode` | `MOVE` · `COPY` | `MOVE` |
| `exchange.keep_days` | días antes de limpiar paquetes ya importados | 7 |

### Formato del paquete (`EXCHANGE\<instancia>_<batch>_<yyyymmdd_HHMMSS>\`)

```
manifest.json            ← se escribe el ÚLTIMO (como .tmp y luego os.replace): su presencia = «paquete completo»
data\<username>\...      ← las carpetas de cuenta tal cual (story\, reels\, highlights\, ficheros de raíz)
imported.json            ← lo escribe el importador (evita importaciones dobles)
```

`manifest.json` (formato `ig_orchestrator.batch_result`, `format_version: "1"`):

```json
{
  "format": "ig_orchestrator.batch_result",
  "format_version": "1",
  "package_id": "uuid4",
  "created_at": "ISO-8601",
  "source": {"instance": "inst1", "app_version": "2.2.0", "schema_user_version": 100},
  "min_reader_version": "3.0.0",
  "batches": [{
    "batch_name": "descargas_2026_10_10", "start_date": "2026-10-10", "final_status": "AWAITING_RENAME",
    "accounts": [{
      "username": "…", "instagram_user_id": "…", "download_stories": true,
      "is_new_account": false,
      "rename": {"owner_id": null, "start_init_date": null, "destination_path": null},
      "folder": "data/<username>",
      "files": {"count": 120, "bytes": 123456789},
      "urls": [{"url": "…", "type": "REEL", "source": "INPUT_URL", "status": "COMPLETED",
                "retries": 0, "error_code": null, "error_text": null, "files": 3}]
    }]
  }],
  "files": [{"path": "data/<username>/story/xxx.mp4", "size": 123}]
}
```

- `files[]` lista cada fichero con su tamaño (permite verificación sin hashes; el `sha256` por fichero es opcional y desactivado por defecto por coste).
- El paquete es **autocontenido**: pc1 no necesita la BD de `inst1`.

### Lado `WORKER` (publicación)

`exchange/publish.py`:

1. Disparador: al cerrarse el último lote de la cola (o un lote suelto) en `gui/run/controller.py`/`orchestration/batch_orchestrator.py` **solo si** `instance.role = WORKER` y `exchange.auto_publish = 1`.
   Botón manual equivalente: **Lote → Publicar descargas…** (para cuando se quiera adelantar o repetir).
2. Construye el manifiesto desde `bdapp` (lotes finalizados desde la última publicación) y los ficheros de `WORKING_FOLDER`.
3. Copia/mueve a `EXCHANGE\<paquete>.partial\` con verificación de tamaño; al terminar renombra a `<paquete>\` y escribe `manifest.json`.
4. En modo `MOVE` borra el origen **solo** tras verificar el 100 %. Marca el lote con `published_at` en la tabla `exchange_publications`.
5. Notificación Telegram opcional reutilizando `telegram/notify_service.py` («Paquete X listo en la compartida: N cuentas / M ficheros»).
6. Si la compartida no responde, reintenta con la política de reintentos existente y deja la publicación `PENDING`; **no** bloquea el siguiente lote.

### Lado `MAIN` (importación fiel)

`exchange/result_import.py` (extiende el diálogo de `feat-uc4-2`, que ahora lista **paquetes** con manifiesto además de carpetas sueltas):

1. Valida `format`, `format_version`, `min_reader_version ≤ app_version` y que `package_id` no esté ya en `exchange_imports`.
2. Copia `data\*` a `WORKING_FOLDER` con la misma lógica verificada de `feat-uc4-2`.
3. Crea o completa el lote local:
   - si `batch_name` no existe → se crea con `catalog_accounts` resueltos por username (o por `instagram_user_id`) y `batch_urls` con los **estados reales**;
   - si existe como DRAFT/IMPORTED → se aplican los resultados a sus URLs coincidentes (por `url` y cuenta);
   - cuentas nuevas: se rellenan `is_new_account`, `rename_owner_id`, `rename_start_init_date`, `rename_destination_path` para que **Renombrar** funcione sin teclear nada;
   - se crea **una** fila en `batch_runs` con `summary = "Imported from <instancia> (package <id>)"`; no se fabrican ejecuciones intermedias.
4. Deja el lote en `AWAITING_RENAME` (como hoy) pero con datos verdaderos.
5. Escribe `imported.json` en el paquete y una fila en `exchange_imports`; el paquete se limpia tras `exchange.keep_days`.

El botón antiguo **«Ejecutado en otra instancia»** se conserva como *fallback* para lotes sin paquete, con un texto que avise de que descarta los resultados.

### Esquema

```sql
CREATE TABLE IF NOT EXISTS exchange_publications (
    id INTEGER PRIMARY KEY, package_id TEXT NOT NULL UNIQUE, batch_ids TEXT NOT NULL,   -- JSON [ids]
    status TEXT NOT NULL,  -- PENDING | PUBLISHED | FAILED
    path TEXT, files INTEGER, bytes INTEGER, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exchange_imports (
    id INTEGER PRIMARY KEY, package_id TEXT NOT NULL UNIQUE, source_instance TEXT,
    batch_id INTEGER REFERENCES batches(id), imported_at TEXT NOT NULL, files INTEGER, bytes INTEGER);
```

## Casos borde

- `inst1` y `pc1` con **versiones distintas**: el manifiesto lleva `app_version`/`min_reader_version`; pc1 rechaza formatos mayores y avisa de versiones menores.
- Misma cuenta en dos lotes de la misma publicación: sus ficheros se mezclan en `data\<username>` (igual que hoy en `Telegram_Desktop`); el manifiesto lista ambas URLs.
- Nombre de lote ya usado en pc1 con contenido distinto → el diálogo pide *Adjuntar* o *Crear con sufijo*.
- Falta de espacio en la compartida o en pc1 → comprobación previa; en `MOVE` nada se borra hasta verificar.
- La compartida se apaga durante la copia → `.partial` se reanuda por fichero.
- Cuentas con username cambiado desde la publicación: resolver por `instagram_user_id` primero.

## Pruebas

- `tests/exchange/test_manifest.py`: construcción a partir de una BD de prueba, serialización estable, validación de versiones.
- `tests/exchange/test_publish.py`: paquete atómico (sin `manifest.json` no es válido), `MOVE` vs `COPY`, corte a mitad, reintento.
- `tests/exchange/test_result_import.py`: lote nuevo, lote existente, cuenta nueva con parámetros de renombrado, idempotencia, `package_id` repetido, versión incompatible.
- Prueba manual: dos instancias reales con un lote pequeño; comprobar que en pc1 los estados de URL coinciden con los de `inst1` y que **Renombrar** funciona.

## Criterios de aceptación

1. Tras terminar un lote en `inst1`, sin intervención humana aparece un paquete completo en `\\DESKTOP-OM856P7\ig_orchestrator\tmp`.
2. En pc1, **Traer** + **Renombrar** completan el flujo sin editar nada a mano; ninguna URL queda en `FAILED_FINAL` por «Executed on another instance».
3. Importar dos veces el mismo paquete no duplica nada.
4. Cortar la red durante la publicación no deja un paquete que parezca válido.

## Documentación a actualizar

`CHANGELOG.md`, `README.md` (modo de dos instancias, formato del paquete), nuevo `exchange/MODULE.md` (esquema `batch_result`), `docs/modularizacion_v2.md`, `tasks/done/`.

## Fuera de alcance

Sincronizar las **bases de datos** de las dos instancias (cada una conserva la suya; solo se intercambian resultados), copia automática del código entre instancias, renombrar en `inst1`.
