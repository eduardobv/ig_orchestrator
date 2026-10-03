# v1.28.0 - Patch GUI: Abrir carpeta y Ver URLs completadas

## Objetivo

Mejorar el menú contextual de **Cuentas del lote actual** durante (y tras) la
ejecución:

1. **Ver URLs completadas…** — listar jobs `COMPLETED` y abrirlos en Chrome.
2. **Abrir carpeta** — abrir en Explorer la carpeta ya descargada de una cuenta
   en estado `Completada`, aunque el lote siga en curso.

## Detalle

### Menú contextual

Orden:

```text
Completar
────────────────
Ver URLs completadas…
Ver URLs en reintento…
Ver URLs fallidas…
────────────────
Abrir carpeta
```

Enable rules:

* Completadas: `completed_items > 0`
* Reintento / Fallidas: como antes
* Abrir carpeta: `runtime.status == COMPLETED`

### Modal de URLs

* `ProblemUrlKind` incluye `"completed"`.
* Misma ventana no modal; doble click abre Chrome; auto-refresh ~1s si el
  proceso sigue corriendo.
* Doble click en fila **Completada** del lote abre la lista de completadas.

### Resolución de carpeta

`resolve_account_download_folder`:

1. `accounts.working_folder` si existe en disco.
2. `settings.working_folder / username` si existe.
3. `None` sin crear carpetas.

## Archivos principales

* `src/ig_orchestrator/gui/batch_resume_service.py`
* `src/ig_orchestrator/gui/app.py`
* `tests/test_gui_services.py`
* `README.md`, `PLAN.md`, `tasks/task-gui.md`, `CHANGELOG.md`

## Pruebas

* `python -m pytest -q tests/test_gui_services.py -k "problem_urls or download_folder"`
* `python -m pytest -q tests/test_gui_services.py`
* `python -m pytest -q`
