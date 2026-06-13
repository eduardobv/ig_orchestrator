# Tarea 1 - Crear estructura base del proyecto

Version objetivo: `v1.1.0`

## Objetivo

Crear la estructura inicial del proyecto Python sin implementar todavia la logica de negocio.

## Archivos/carpetas esperadas

```text
README.md
PLAN.md
Agents.md
CHANGELOG.md
requirements.txt
.env.example
.gitignore
config/
data/
logs/
reports/
src/ig_orchestrator/__init__.py
src/ig_orchestrator/__main__.py
src/ig_orchestrator/main.py
tests/
```

## Criterios de aceptacion

* Se puede ejecutar `python -m ig_orchestrator`.
* `.env`, `*.session`, bases SQLite y logs sensibles estan en `.gitignore`.
* Existen carpetas base para config, data, logs y reports.
* No se implementa Telegram real en esta tarea.
* Actualizar `CHANGELOG.md`.

## Pruebas

* Ejecutar import basico del paquete.
* Verificar que `python -m ig_orchestrator` muestra una salida minima o ayuda.
