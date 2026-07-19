# Spike: GUI de escritorio para crear y ejecutar lotes

## Objetivo

Crear una interfaz grafica de escritorio para preparar lotes de descarga sin editar manualmente `config/batch.json`.

La GUI debe permitir seleccionar cuentas frecuentes, activar descarga de stories, pegar URLs de posts/reels/highlights, editar/eliminar entradas del lote y ejecutar el orquestador. El flujo CLI actual debe seguir funcionando igual con `config/batch.json`.

La GUI no debe ser web, Angular ni React.

## Contexto observado

El input actual vive en `config/batch.json` con este contrato:

```json
{
  "schema_version": "1.0",
  "batch_name": "descargas_06_01_julio_2026",
  "defaults": {
    "download_stories": false,
    "start_now_date": "2026-07-05"
  },
  "accounts": [
    {
      "username": "example",
      "start_now_date": "2026-06-21",
      "download_stories": false,
      "urls": []
    }
  ]
}
```

El archivo real ya funciona como catalogo manual de cuentas frecuentes: contiene muchos `username`, normalmente con `download_stories = false` y `urls = []`, mas algunos huecos con `username` vacio.

El proyecto ya tiene estas piezas reutilizables:

- `account_history`: tabla SQLite global para usernames conocidos, sin repetir.
- `input_batches`, `accounts`, `url_jobs`: tablas que representan el lote real a procesar.
- `import_parsed_batch`: guarda batches, cuentas y URL jobs desde un lote parseado.
- `run_continue --batch-id`: procesa un lote ya existente en SQLite sin reimportar JSON.
- `batch_json_parser`: validaciones de fecha, username, URLs Instagram y duplicados.

Conclusion del spike: la GUI debe escribir trabajos en SQLite usando la misma logica de creacion/importacion de lotes, y ejecutar el motor existente contra un `batch_id`. El JSON queda como entrada CLI independiente y como fuente inicial de sugerencias, no como backend obligatorio de la GUI.

## Decision tecnica recomendada

Usar `tkinter` + `ttk`, incluido en la libreria estandar de Python.

Motivos:

- Cumple el requisito de escritorio y evita frontend web.
- No introduce dependencia runtime nueva.
- Es suficiente para un formulario rapido con buscador, tabla, checkboxes, textarea y consola de progreso.
- Funciona bien en Windows con Python 3.11+.

No usar PySide6/PyQt en esta primera version salvo que se pida una UI mas sofisticada despues. Son mejores visualmente, pero anaden una dependencia grande para un flujo que necesita ante todo rapidez y fiabilidad.

## Flujo de usuario esperado

1. Abrir la GUI:

```bash
python -m ig_orchestrator gui
```

2. La ventana muestra:

- nombre del lote sugerido automaticamente;
- fecha por defecto editable;
- buscador/autocomplete de cuentas frecuentes;
- lista del lote actual;
- editor de cuenta con `download_stories`;
- caja grande para pegar URLs, una por linea;
- botones para agregar, actualizar, eliminar, limpiar y ejecutar.

3. El usuario busca una cuenta en Instagram manualmente.
4. En la GUI escribe o selecciona el username.
5. Si hay stories nuevas, marca `Stories`.
6. Si hay posts/reels/highlights nuevos, pega las URLs en el textarea.
7. Pulsa `Agregar` o `Actualizar`.
8. Repite para las cuentas necesarias.
9. Pulsa `Ejecutar`.
10. La GUI crea un batch nuevo en SQLite y lanza el procesamiento real.
11. La GUI muestra salida/progreso del proceso y al terminar muestra batch id, resumen y reporte si existe.

## Diseno de interfaz

Ventana principal: `Instagram Orchestrator`

Zona superior:

- `Batch name`: input editable, inicializado con el ultimo `batch_name`
  ejecutado en SQLite. Si no hay ejecuciones, usa el ultimo batch guardado; si
  tampoco existe, sugiere `descargas_YYYY_MM_DD_HHMM`.
- `Start date`: input `YYYY-MM-DD`, por defecto hoy.
- `Dry-run`: checkbox.
- `Ejecutar`: boton principal.
- `Guardar lote`: boton secundario para crear el batch sin ejecutarlo.

Panel izquierdo: catalogo de cuentas

- Buscador con filtrado incremental.
- Lista de usernames desde:
  - `account_history`;
  - `config/batch.json`;
  - opcionalmente `config/bkp/*.json` si no hay suficientes entradas en `account_history`.
- Doble click en un username lo carga en el editor.
- Accion futura opcional: marcar cuenta como `DISABLED` para ocultarla.

Panel central: lote actual

- Tabla `ttk.Treeview` con columnas:
  - username;
  - stories: si/no;
  - urls: contador;
  - start date;
  - estado de validacion.
- Seleccionar una fila carga sus datos en el editor.
- Botones:
  - `Subir`;
  - `Bajar`;
  - `Duplicar`;
  - `Eliminar`;
  - `Limpiar lote`.

Panel derecho: editor de cuenta

- `Username`: combobox editable con autocomplete.
- `Download stories`: checkbox.
- `New account`: checkbox desmarcado por defecto. Al marcarlo muestra tres
  campos obligatorios: `ownerId`, `path` y `startInitDate` (`YYYY-MM-DD`).
- `Start date`: input por defecto hoy. Tras `Agregar / Actualizar`, el editor
  limpia username, stories y URLs, pero mantiene la fecha de hoy.
- `URLs`: textarea multilinea, una URL por linea.
- Botones:
  - `Pegar`;
  - `Normalizar`;
  - `Agregar / Actualizar`;
  - `Limpiar editor`.
- Indicadores compactos:
  - total URLs;
  - duplicadas;
  - invalidas;
  - tipos detectados: reels/posts/stories/highlights.

Panel inferior: ejecucion

- Consola read-only con stdout/stderr del proceso y timestamp local con
  milisegundos en cada linea.
- Barra de progreso indeterminada mientras corre.
- Botones:
  - `Clean`, disponible para vaciar la consola de estado cuando sea necesario;
  - `Cancelar proceso` si se lanzo como subprocess;
  - `Renombrar`, deshabilitado hasta que termine correctamente un lote real;
  - `Abrir reporte` cuando exista;
  - `Abrir carpeta logs`.

Zona superior de recuperacion:

- `Recuperar ejecucion (N)` abre `Ejecuciones pendientes`, un selector con `batch date`, `batch name`,
  `batch id`, estado y resumen de cuentas.
- `Reanudar seleccionado` recupera el lote completo en `Lote actual` y ejecuta
  `run_continue --batch-id`.
- `Dar por finalizado` pide confirmacion, marca el batch `COMPLETED` sin borrar
  datos y lo retira del selector.
- Durante la ejecucion, `Lote actual` muestra por color cuentas completadas,
  en reintento, en curso, pendientes y fallidas.
- `Cancelar proceso` conserva los estados individuales y deja el batch
  `PARTIAL`, listo para reanudar.

`Renombrar` ejecuta en segundo plano:

```text
python D:\Archivos\Scripts\IG\ManualRenameFiles\main.py --newRename --startNowDate "START_DATE_GLOBAL" [--new-account "USERNAME" "OWNER_ID" "START_INIT_DATE" "PATH"]... --no-duplicated --move-renamed
```

Cada cuenta marcada como `New account` agrega su propio bloque
`--new-account`. `Agregar / Actualizar` la incorpora al lote actual y tambien
al catalogo `account_history`, donde se conserva `ownerId`, `path` y
`startInitDate` para consultas posteriores.

La salida combinada del renombrador se transmite a la consola de estado. El
boton no se habilita tras dry-run ni tras una ejecucion fallida.

## Reglas funcionales

- No permitir ejecutar un lote vacio.
- No permitir una cuenta activa sin stories y sin URLs.
- Permitir cuentas nuevas no presentes en el catalogo.
- Normalizar username con `strip()`, sin `@` inicial.
- Pegar URLs en bloque separadas por saltos de linea o por comas.
- Aceptar URLs con comillas dobles o simples, con coma al final, y normalizar
  el texto a una URL limpia por linea.
- Ignorar lineas vacias.
- Detectar duplicados dentro de la misma cuenta antes de guardar.
- Validar dominio Instagram usando la misma politica del parser actual.
- Clasificar URLs usando `classify_instagram_url`.
- Mostrar errores de validacion sin cerrar la ventana.
- Al guardar en SQLite, crear o actualizar `account_history` para cada username usado.
- No escribir secretos ni mostrar valores sensibles del `.env`.
- No modificar ni limpiar `config/batch.json` cuando el lote nace desde GUI.

## Arquitectura propuesta

Agregar un paquete nuevo:

```text
src/ig_orchestrator/gui/
  __init__.py
  app.py
  batch_draft.py
  batch_draft_service.py
  account_catalog_service.py
  process_runner.py
  batch_resume_service.py
```

Responsabilidades:

- `gui.app`: construye widgets Tkinter, eventos y estado visual.
- `gui.batch_draft`: dataclasses de borrador de lote y cuenta.
- `gui.batch_draft_service`: valida el borrador y lo persiste en SQLite como `input_batches`, `accounts` y `url_jobs`.
- `gui.account_catalog_service`: lee sugerencias desde `account_history`, `config/batch.json` y backups.
- `gui.process_runner`: lanza el proceso en background y stream de salida.
- `gui.batch_resume_service`: consulta pendientes, reconstruye borradores,
  resume el seguimiento y finaliza batches manualmente.

Agregar entrada CLI:

```bash
python -m ig_orchestrator gui
```

Implementacion sugerida:

- En `main.py`, agregar subcomando `gui`.
- El subcomando carga settings, inicializa SQLite y abre la app Tkinter.
- La app no debe bloquear ni reemplazar el flujo `--input`.

## Persistencia desde GUI

La GUI debe crear batches directamente en SQLite. Para evitar duplicar logica con el importador JSON, extraer un servicio comun:

```text
input/batch_creation_service.py
```

Ese servicio debe recibir datos ya validados o parseados y encargarse de:

- crear un `input_batch` con `source_file = NULL` o un marcador claro de origen GUI;
- rechazar `batch_name` duplicado;
- ordenar cuentas con la misma regla actual;
- crear/actualizar `account_history`;
- crear `accounts`;
- crear story generada si `download_stories = true`;
- crear `url_jobs` para URLs manuales;
- registrar duplicados si aplica.

Luego:

- `batch_importer.py` usa este servicio comun despues de parsear JSON.
- `gui.batch_draft_service` usa este servicio comun despues de validar el borrador.

Esto mantiene una sola logica para JSON y GUI.

## Ejecucion desde GUI

Primera version recomendada: lanzar un subprocess.

Comando real:

```bash
python -m ig_orchestrator run_continue --batch-id {batch_id}
```

Comando dry-run:

Hay dos opciones aceptables:

1. Implementar `run_continue --batch-id {batch_id} --dry-run`.
2. Si se quiere menor alcance, deshabilitar dry-run para batches GUI en la primera fase y dejarlo para la segunda.

La opcion preferida es anadir dry-run a `run_continue`, porque la GUI necesita validar sin enviar a Telegram.

El subprocess permite:

- mantener Telethon y asyncio fuera del hilo UI;
- mostrar stdout/stderr en la consola inferior;
- cancelar el proceso si es necesario;
- no mezclar el ciclo de eventos de Tkinter con la descarga real.

## Tareas propuestas

### Tarea GUI 1: editor de lote y persistencia SQLite

Objetivo: abrir una GUI de escritorio que permita crear un lote y guardarlo en SQLite sin ejecutar Telegram.

Alcance:

- Crear paquete `ig_orchestrator.gui`.
- Agregar subcomando `python -m ig_orchestrator gui`.
- Implementar catalogo de cuentas desde `account_history` y `config/batch.json`.
- Implementar editor de lote con agregar/actualizar/eliminar/reordenar.
- Implementar validaciones locales.
- Persistir el lote en SQLite usando un servicio comun compartido con el importador JSON.
- Mantener intacto el modo actual `python -m ig_orchestrator --input config\batch.json`.
- Agregar tests unitarios para:
  - conversion de borrador GUI a batch persistido;
  - catalogo desde `account_history`;
  - catalogo desde `config/batch.json`;
  - validacion de cuenta sin stories y sin URLs;
  - rechazo de `batch_name` duplicado.

Criterios de aceptacion:

- La GUI abre con `python -m ig_orchestrator gui`.
- El usuario puede seleccionar una cuenta existente del JSON actual.
- El usuario puede agregar una cuenta nueva.
- El usuario puede marcar stories y pegar URLs.
- El usuario puede editar y eliminar filas antes de guardar.
- Al guardar, SQLite contiene `input_batches`, `accounts`, `url_jobs` y `account_history`.
- `config/batch.json` no se modifica.
- Todos los tests pasan.

Version sugerida:

```text
v1.25.0
```

### Tarea GUI 2: ejecucion, dry-run y progreso desde la GUI

Objetivo: permitir ejecutar desde la ventana el batch creado por GUI.

Alcance:

- Agregar soporte dry-run para `run_continue --batch-id`.
- Implementar `process_runner` con subprocess.
- Mostrar salida del proceso en la consola inferior.
- Bloquear edicion mientras el proceso corre.
- Mostrar resultado final, batch id, SQLite path y reporte Markdown si existe.
- Agregar boton para abrir reporte y carpeta de logs.
- Manejar errores de `.env`, Telethon, batch duplicado y validacion sin cerrar la app.

Criterios de aceptacion:

- `Ejecutar` guarda el lote y procesa ese `batch_id`.
- `Dry-run` no envia mensajes a Telegram ni mueve archivos.
- El output del proceso se ve en la GUI.
- La ventana no queda congelada durante la ejecucion.
- El modo CLI actual sigue funcionando igual.
- Todos los tests pasan.

Version sugerida:

```text
v1.26.0
```

## Fuera de alcance

- Automatizar navegacion por Instagram.
- Extraer URLs automaticamente desde el navegador.
- Integracion Tampermonkey.
- Web UI.
- Angular, React, FastAPI, Streamlit.
- Cambiar el bot de Telegram.
- Cambiar la logica de descarga, watcher, movimiento o reportes.
- Integracion nueva con renombrador, duplicados o movimiento final.

## Notas para implementacion

- Usar `pathlib.Path`.
- No crear una base de datos separada para la GUI.
- No guardar secretos en SQLite ni logs.
- Evitar dependencias nuevas.
- Mantener modulos pequenos y testeables.
- No hacer llamadas reales a Telegram en tests.
- Si se necesita una vista mas moderna despues, la capa de servicios debe permitir reemplazar Tkinter sin tocar la logica de lote.

## Comandos esperados

Abrir GUI:

```bash
python -m ig_orchestrator gui
```

Ejecutar CLI como hasta ahora:

```bash
python -m ig_orchestrator --input config\batch.json --run
```

Continuar/procesar lote creado por GUI:

```bash
python -m ig_orchestrator run_continue --batch-id 123
```

Dry-run de lote creado por GUI, si se implementa en Tarea GUI 2:

```bash
python -m ig_orchestrator run_continue --batch-id 123 --dry-run
```
