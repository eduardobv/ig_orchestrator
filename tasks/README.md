# Tareas v2.1 - GUI UX Improvements

Conjunto de 5 tareas independientes para mejorar la experiencia de usuario de la GUI v2.

## Tareas

### 1. [Tarea_v2_1_1_window_positioning.md](Tarea_v2_1_1_window_positioning.md)

**Posicionamiento Configurable de Ventanas**

- Ventana principal se abre configurable: izquierda, centro o derecha
- Modales se abren centradas en ventana padre
- Setting: `window_position` (left/center/right)
- Versión: v2.1.1

**Archivos principales**:
- `src/ig_orchestrator/settings.py`
- `src/ig_orchestrator/gui/shared/helpers.py`
- `src/ig_orchestrator/gui/shell/app.py`
- `src/ig_orchestrator/gui/settings/dialog.py`

---

### 2. [Tarea_v2_1_2_settings_modal_tabs.md](Tarea_v2_1_2_settings_modal_tabs.md)

**Refactorizar Settings Modal con Pestañas y Guardar/Cancelar**

- Modal con 5 pestañas: General, Telegram, Paths, Download, Advanced
- Botón "Save" para aplicar cambios
- Botón "Cancel" para descartar cambios
- Validación antes de guardar
- Versión: v2.1.2

**Archivos principales**:
- `src/ig_orchestrator/gui/settings/dialog.py`
- `src/ig_orchestrator/settings.py`
- `src/ig_orchestrator/gui/i18n.py`

---

### 3. [Tarea_v2_1_3_copy_urls_feature.md](Tarea_v2_1_3_copy_urls_feature.md)

**Copiar URLs al Portapapeles en Panel de Errores**

- Botón "Copy URL" en modal de errores
- Context menu (click derecho) para copiar
- Opción "Copy All URLs"
- Notificación visual al copiar
- Versión: v2.1.3

**Archivos principales**:
- `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`
- `src/ig_orchestrator/gui/i18n.py`
- `src/ig_orchestrator/gui/icons.py`

---

### 4. [Tarea_v2_1_4_pause_resume_button.md](Tarea_v2_1_4_pause_resume_button.md)

**Botón Pause/Resume en Ventana Principal**

- Botón en toolbar que cambia entre Pause ↔ Resume
- Pausar batch sin cerrarlo
- Reanudar desde donde se pausó
- Habilitación/deshabilitación contextual
- Versión: v2.1.4

**Archivos principales**:
- `src/ig_orchestrator/gui/chrome/toolbar.py`
- `src/ig_orchestrator/gui/shell/app.py`
- `src/ig_orchestrator/gui/batch_queue_service.py`
- `src/ig_orchestrator/gui/i18n.py`

---

### 5. [Tarea_v2_1_5_default_batch_name.md](Tarea_v2_1_5_default_batch_name.md)

**Nombre de Batch por Defecto con Timestamp**

- Nombre por defecto: `descargas_YYYY_MM_DD_HH_MM_SS`
- Genera nuevo nombre cada vez que se abre la app
- Botón "Generate New Name" para nuevo timestamp
- Validación de nombre único
- Versión: v2.1.5

**Archivos principales**:
- `src/ig_orchestrator/gui/shared/helpers.py`
- `src/ig_orchestrator/gui/shell/app.py`
- `src/ig_orchestrator/gui/batch_draft_service.py`
- `src/ig_orchestrator/gui/i18n.py`

---

## Dependencias Entre Tareas

```
1 (window_positioning)      ← Independiente
2 (settings_tabs)           ← Depende de 1 (modal se posiciona según posición)
3 (copy_urls)               ← Independiente
4 (pause_resume)            ← Independiente
5 (default_batch_name)      ← Independiente
```

**Orden recomendado de ejecución**:
1. Tarea v2.1.5 (más simple, sin dependencias)
2. Tarea v2.1.1 (necesario para colocar modales correctamente)
3. Tarea v2.1.2 (depende de v2.1.1 para posicionamiento)
4. Tarea v2.1.3 (independiente, se integra bien con cualquier orden)
5. Tarea v2.1.4 (independiente, no depende de otras)

---

## Workflow por Tarea

Cada tarea sigue este flujo:

1. **Research**: Explorar archivos existentes y entender contexto
2. **Plan**: Diseñar cambios y validar con código existente
3. **Implement**: Escribir código modificando archivos listados
4. **Review**: Verificar que cambios son correctos y completos
5. **Archive**: Marcar tarea como completada en este README

### Estado de Tareas

- [ ] Tarea v2.1.1: Window Positioning
- [ ] Tarea v2.1.2: Settings Modal Tabs
- [ ] Tarea v2.1.3: Copy URLs Feature
- [ ] Tarea v2.1.4: Pause/Resume Button
- [ ] Tarea v2.1.5: Default Batch Name

---

## Notas Importantes

- **Rama**: `v2/gui-ux-stories` (activa)
- **Versión Base**: v2.1.0
- **Target**: v2.1.5 (después de todas las tareas)
- **No usar SQLite v1**: Todas las tareas deben usar SQLite v2 (`data/orchestrator_gui.sqlite`)
- **Testing**: Incluido en cada tarea
- **Translations**: Cada tarea incluye keys en `i18n.py`

---

## Recursos

- `CLAUDE.md` — Instrucciones generales del proyecto
- `AGENTS.md` — Instrucciones para IA
- `docs/modularizacion_v2.md` — Arquitectura GUI v2
- `src/ig_orchestrator/gui/MODULE.md` — Documentación de módulos GUI

---

**Creado**: 2026-10-03
**Estado**: Todas pendientes
**Rama**: v2/gui-ux-stories
