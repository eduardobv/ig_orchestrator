# Tarea v2 — Procesamiento stories-first en dos barridas

Fecha: 2026-09-04
Serie: v2.0.0 (en progreso)

## Problema

El lote procesaba cada cuenta entera (stories + reels/posts/highlights +
reintentos) antes de pasar a la siguiente. Las stories caducan; si una cuenta
con muchos reels va primero, las stories del resto del lote pueden expirar.

## Comportamiento objetivo

El orden de importación se mantiene (primero cuentas solo-stories, después
menos a más URLs). Encima de eso, con el modo nuevo:

1. Cuentas con enlaces **solo STORY**.
2. Resto de cuentas que **tienen STORY** (solo se descarga el enlace STORY).
3. Segunda barrida: cuentas cuyas stories ya se procesaron y quedan reels,
   posts o highlights.
4. Segunda barrida: cuentas **sin stories**, solo reels/posts/highlights.

Tras la primera barrida:

* cuentas solo-stories → `COMPLETED` / `PARTIAL` / `FAILED`;
* cuentas mixtas → `INCOMPLETE` (trabajo restante pendiente).

Tras la segunda barrida, el estado final es el de siempre
(`COMPLETED` / `PARTIAL` / `FAILED`).

Configurable en **Configuración** con un check. Desactivado = modo legado
(cuenta entera y luego la siguiente).

## Fases

### Fase 1 — Persistencia y modelo

* Estado de cuenta `INCOMPLETE`.
* Setting `processing.stories_first` (default activo).
* Lookup GUI `batch_account_statuses` id 6.
* Cuentas `INCOMPLETE` reanudables.

### Fase 2 — Política de orden y alcance

* Módulo `processing_policy.py`: alcance `ALL` / `STORIES` / `NON_STORIES`.
* Un job STORY es `publication_type = STORY` (generado o URL de entrada).
* Reintentos de cada barrida solo sobre jobs de ese alcance.

### Fase 3 — Orquestadores

* `AccountOrchestrator.process_account(..., scope=)`.
* `BatchOrchestrator` dos barridas si el setting está activo.
* Modo legado sin cambios de contrato.

### Fase 4 — GUI

* Check en Configuración; un clic guarda y cambia de paradigma.
* Tabla del lote: estado `Incompleta`.

### Fase 5 — Tests y documentación

* Tests de política, orquestadores, setting y migración.
* `PLAN.md`, `Agents.md`, `README.md`, `CHANGELOG.md`.
