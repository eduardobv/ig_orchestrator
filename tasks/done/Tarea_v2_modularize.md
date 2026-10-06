# T2.MOD — Modularización GUI / persistencia / tests

Estado: **HECHO** (corte de módulos; no es el release `v2.0.0`).

Leer antes: `docs/modularizacion_v2.md`, `Agents.md`, este archivo.

## Objetivo

Trocear el código actual en paquetes por pantalla/dominio **sin cambiar
comportamiento**. El código se mueve; no se reescriben algoritmos, SQL ni
widgets.

## Fases

0. Documentación canónica (`docs/modularizacion_v2.md`, este archivo).
1. Extraer `gui/shared` (helpers, i18n, theme, icons, log, locales, static).
2. Extraer mixins / diálogos de `gui/app.py` a `catalog`, `editor`,
   `batch_accounts`, `chrome`, `settings`, `run`, `batches`, `queue`, `shell`.
3. Mover servicios GUI a subpaquetes; shims en rutas viejas.
4. Partir `db/gui_adapters.py` y agrupar v1/v2; shims.
5. Partir `tests/test_gui_services.py` y agrupar `tests/` por paquete.
6. `MODULE.md` por paquete + CHANGELOG + `Agents.md` + `PLAN.md` §5.
7. Partir `main.py` → `cli/`.

Criterio de hecho de cada fase: `pytest` verde (mismos tests, mismos asserts).

## Fuera de alcance

* Tag / PR `v2.0.0`.
* Cambiar esquema SQLite.
* Escribir en `data/orchestrator.sqlite`.
* Event-bus o rediseño visual.

## Verificación

```text
pytest
python -m ig_orchestrator gui
```

La ventana debe verse y comportarse igual. No hay browser (GUI Tk).
