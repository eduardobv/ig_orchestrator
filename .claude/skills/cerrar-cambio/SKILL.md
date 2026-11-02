---
name: cerrar-cambio
description: Checklist para cerrar un feat o fix de ig_orchestrator: archivos de versión, documentación obligatoria, formato de commit y tag. Úsala al terminar un feat/fix, o cuando el usuario pida versionar, commitear o cerrar un cambio. También da el prefijo de commit (feat/fix/docs/chore/refactor/test) cuando el usuario ordene commitear cualquier cambio. No aplica a consulta, análisis, spike ni poc (no se commitean).
---

# Cerrar un feat o fix

Los pasos 1-3 son para **feat** (minor) y **fix** (patch); `docs`/`chore`/`refactor`/`test` solo usan el paso 5 (prefijo, sin versión ni tag). Ver la tabla de «Tipo de petición» en `CLAUDE.md`. Si el usuario dijo «sin commit» / «déjame verlo», haz los pasos 1-4 y **para antes del commit**.

## 1. Versión

Siguiente versión: feat → minor (`v4.18.1` → `v4.19.0`); fix → patch (`v4.18.1` → `v4.18.2`). Si el usuario indicó una, usa esa. Actualiza en el mismo cambio:

- `pyproject.toml` (`version`)
- `src/ig_orchestrator/__init__.py` (`__version__`)
- `tests/test_package_smoke.py` (los dos `assert` con la versión, incluida la cadena `ig_orchestrator vX.Y.Z`)
- `CLAUDE.md` raíz, sección «Estado» (versión actual)
- `docs/arquitectura-v3.md` (estado/versión)

## 2. Documentación (revisar todo; editar lo que cambie)

- `CHANGELOG.md`: versión, fecha, archivos creados y modificados, comportamiento, pruebas ejecutadas.
- `docs/manual-usuario.md`: obligatorio si cambia un menú, menú contextual, modal, botón o ajuste de la GUI.
- `docs/tutorial-v3.md`: sección del feat (dónde está, campos, ejemplos, cómo probarlo).
- `docs/arquitectura-v3.md`: si cambia arquitectura, modelo de datos, ajustes o limitaciones.
- `MODULE.md` y `CLAUDE.md` del paquete tocado; `README.md` si cambia lo visible.
- Feat: crear `tasks/done/v3/feat-<área>-<n>.md` (objetivo, qué se hizo, qué no, «Resultado de la implementación») y añadir fila en `docs/plan-v3-features.md`. Fix: anotar el cambio en el `feat-*.md` del feat corregido.
- Si hay que hacer algo a mano en otras instancias: entrada en `inst_sync/CAMBIOS.md`; cambio de datos en `inst_sync/sql/NNN_*.sql`.
- No editar `AGENTS.md` / `Agents.md` (los mantiene el usuario para otras IAs).

## 3. Pruebas

`python -m pytest -q` (o el subconjunto relevante si la suite completa no cabe) y anota en el CHANGELOG lo que se ejecutó y lo que no se pudo probar (p. ej. Telegram real o `G:` real).

## 4. Revisión de lo que entra

`git status` y `git diff --stat`: nada de `.env`, `*.session*`, bases `data/*.sqlite*` ni secretos. No incluyas archivos ajenos al cambio (p. ej. `data/orchestrator_gui.sqlite.bak_*`).

## 5. Commit y tag (solo si no se pidió revisar antes)

```bash
git add <archivos del cambio>
git commit -m "feat: v4.19.0 <resumen en inglés> (feat-<área>-<n>)"   # feat
git commit -m "fix: <resumen en inglés> (v4.18.2)"                    # fix
git tag v4.19.0
```

Añade al final del mensaje la línea de co-autoría que indique el entorno. **No** hagas `push`, merge ni cambio de rama.

### Prefijo según el tipo (también para lo que no es feat/fix)

| Prefijo | Cuándo | Versión / tag | Ejemplo del historial |
|---|---|---|---|
| `feat:` | capacidad nueva | `vX.Y.0` en el mensaje + tag | `feat: v4.18.0 inst_sync, replicate the code to another instance (feat-uc4-7)` |
| `fix:` | corrección o retoque de algo entregado | `(vX.Y.Z)` al final + tag | `fix: restart batch on the GUI database (v4.12.1)` |
| `docs:` | solo documentación (incl. reorganizar `CLAUDE.md`/`MODULE.md`) | no | `docs: architecture guide and session-start protocol` |
| `chore:` | mantenimiento, cierre de serie, dependencias | no (salvo cierre de serie) | `chore: v3.26.0 close v3 series` |
| `refactor:` | reorganización sin cambio de comportamiento | no | — |
| `test:` | solo tests | no | `test: update smoke version to 3.17.1` |

Un commit = un tipo. Si el cambio mezcla tipos, manda el mayor (feat > fix > resto) y su documentación va dentro; no partas la documentación propia del feat en un `docs:` aparte.
