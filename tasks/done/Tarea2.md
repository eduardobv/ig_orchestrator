# Tarea 2 - Settings y configuracion

Version objetivo: `v1.2.0`

## Objetivo

Crear un modulo de configuracion que lea `.env` y exponga un objeto `Settings`.

## Archivo principal

```text
src/ig_orchestrator/settings.py
```

## Campos requeridos

```text
telegram_api_id
telegram_api_hash
telethon_session_name
telegram_download_bot_username
telegram_desktop_download_folder
working_folder
reports_folder
sqlite_db_path
max_retries
retry_base_seconds
retry_max_seconds
download_wait_timeout_seconds
download_stable_seconds
```

## Criterios de aceptacion

* Si falta una variable obligatoria, mostrar error claro.
* Las rutas deben manejarse con `pathlib.Path`.
* No loguear secretos.
* Mantener variables de renombrado/final move como reservadas, no obligatorias para `v1.0.1`.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Tests unitarios de carga correcta.
* Tests unitarios de variables faltantes.
