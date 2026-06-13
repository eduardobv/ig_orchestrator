# Changelog

## v1.1.0 - Tarea 1 - Estructura base del proyecto

Fecha: 2026-06-13

### Creado

* `pyproject.toml` para empaquetar el proyecto con layout `src`.
* `.env.example` con las variables previstas para la serie `v1.x`.
* `src/ig_orchestrator/__init__.py`.
* `src/ig_orchestrator/__main__.py`.
* `src/ig_orchestrator/main.py`.
* `tests/test_package_smoke.py`.
* `data/.gitkeep`, `logs/.gitkeep` y `reports/.gitkeep`.
* `.vscode/launch.json` con configuraciones para depurar `ig_orchestrator` y ejecutar `pytest`.

### Modificado

* `README.md` con uso inicial.
* `requirements.txt` con dependencias base documentadas en el plan.
* `.gitignore` para proteger `.env`, sesiones de Telethon, SQLite y logs sin bloquear carpetas base.
* `tasks/Tarea1.md` para incluir `launch.json` en el alcance de la tarea.

### Resumen

El paquete se puede importar y ejecutar con `python -m ig_orchestrator`, mostrando
una salida minima sin implementar todavia logica de Telegram ni negocio. Tambien
queda disponible una configuracion compartida de VS Code para ejecutar y depurar
la aplicacion o los tests.

### Pruebas ejecutadas

* `python -m pytest`
* `python -m ig_orchestrator`
* `python -m json.tool .vscode\launch.json`

## Planificacion - Versionado por tarea

Fecha: 2026-06-13

### Modificado

* `tasks/Tarea1.md` a `tasks/Tarea24.md`: cada tarea ahora apunta a su minor propio, de `v1.1.0` a `v1.24.0`.
* `PLAN.md`: agregada convencion de versionado minor por tarea y patch por correccion.
* `Agents.md`: agregada instruccion para responder con comandos sugeridos de commit y tag.
* `.github/copilot-instructions.md`: agregada convencion de versionado por tarea.

## v1.0.1 - Planificacion inicial

Fecha: 2026-06-13

### Creado

* `Agents.md` con instrucciones base para IA.
* `.github/copilot-instructions.md` con instrucciones resumidas para Copilot.
* `tasks/Tarea1.md` a `tasks/Tarea24.md`.
* `config/batch.example.json` como ejemplo de entrada por lotes.
* `config/app.example.json` como ejemplo de configuracion operativa persistible en SQLite.

### Modificado

* `PLAN.md` reestructurado para `v1.0.1`.

### Notas

`v1.0.1` queda centrada en descarga, SQLite, reintentos y reportes. Renombrado, duplicados del renombrador y movimiento final quedan documentados como backlog posterior.
