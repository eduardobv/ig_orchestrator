# filesystem — clasificación de archivos y rutas de salida

## Clasificación de archivos

- Imagen: `.jpg`, `.jpeg`, `.png`, `.webp`. Video: `.mp4`, `.mov`, `.mkv`, `.webm`. Otro: `UNKNOWN`.
- Una URL `REEL` que descarga solo imágenes se corrige a `POST`.

## Descargas y movimiento

```
TELEGRAM_DESKTOP_DOWNLOAD_FOLDER/   # inicial (Telegram Desktop)
  ↓
WORKING_FOLDER\username\            # raíz de la cuenta
  ├─ story\        # STORY
  ├─ reels\        # REEL con video
  └─ highlights\   # HIGHLIGHTS      (POST con imagen → raíz de la cuenta)
```

- Si el destino existe: sufijo numérico `archivo_1.jpg`, `archivo_2.jpg`… (nunca se sobrescribe).
- Al finalizar un lote real: limpiar `telegram_media*` en la raíz y `*_1.mp4` duplicados en `reels\` (`batch_cleanup.py`).
- Almacén opcional (v3.11): `app_settings['staging.root']`; ver `staging/MODULE.md`.
