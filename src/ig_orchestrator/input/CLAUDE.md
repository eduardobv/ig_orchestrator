# input — importación y clasificación de URLs

## Clasificación (`url_classifier.py`)

- `/stories/highlights/...` → `HIGHLIGHTS`
- `/stories/{username}/` → `STORY`
- `/reel/...` → `REEL`
- `/p/...?...img_index=...` → `POST`
- `/p/...` sin `img_index` → inicialmente `REEL`; se corrige a `POST` si solo se descargan imágenes (corrección posterior en el flujo de archivos).

## Importación

- `batch_name` único: no se reutiliza (`--run` rechaza uno existente; `run_continue` retoma).
- Tras importar un lote real: respaldo del JSON en `config/bkp` y `batch.json` limpio sin perder metadata.
- Registra usernames en `account_history` (global, sin repetir entre lotes).
- Origen de cada URL: `GENERATED_STORY` o `INPUT_URL`.
