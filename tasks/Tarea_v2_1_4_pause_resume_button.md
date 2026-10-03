# Tarea v2.1.4: Botón Pause/Resume en Ventana Principal

## Resumen

Actualmente para pausar y reanudar una ejecución de batch, el usuario debe:
1. Hacer click en "Stop"
2. Ir a "Batches / runs"
3. Buscar el batch
4. Hacer click en "Resume"

Se requiere un botón "Pause" / "Resume" en la ventana principal que:
- Pause la ejecución actual (sin detener)
- Permita reanudar desde donde se pausó
- Cambie entre estados "Pause" ↔ "Resume" según estado actual
- Esté visible solo cuando hay batch ejecutándose

## Contexto

**Archivos clave**:
- `src/ig_orchestrator/gui/shell/app.py` — Ventana principal y toolbar
- `src/ig_orchestrator/gui/chrome/toolbar.py` — Toolbar con botones
- `src/ig_orchestrator/gui/batch_queue_service.py` — Lógica de pausar/reanudar

Flujo actual:
1. User hace click en "Run" → se inicia batch
2. `process_runner` ejecuta proceso en thread separado
3. User hace click en "Stop" → interrumpe proceso
4. Para continuar: "Batches / runs" → Resume

Funciones existentes en `batch_queue_service.py`:
```python
def pause_queue(connection: Connection, queue_id: int) -> None:
    """Pausa una queue sin marcarla como completada."""

def start_or_resume_queue(connection: Connection, queue_id: int) -> None:
    """Inicia o continúa una queue pausada."""
```

## Cambios Esperados

### 1. Agregar Botón al Toolbar

**Archivo**: `src/ig_orchestrator/gui/chrome/toolbar.py`

```python
class ToolbarMixin:
    def _build_run_controls(self) -> None:
        """Botones Run, Stop, Pause/Resume."""
        
        # Botón existente: Run
        self.run_button = icon_button(
            self.toolbar,
            self.icons.play_icon,
            self.run_batch,
            tooltip=t("toolbar.run")
        )
        
        # Botón existente: Stop
        self.stop_button = icon_button(
            self.toolbar,
            self.icons.stop_icon,
            self.stop_batch,
            tooltip=t("toolbar.stop")
        )
        
        # ← NUEVO: Botón Pause/Resume
        self.pause_button = icon_button(
            self.toolbar,
            self.icons.pause_icon,
            self._toggle_pause_resume,
            tooltip=t("toolbar.pause")
        )
        self.pause_button.pack(side=tk.LEFT, padx=2)
        self.pause_state = "pause"  # "pause" o "resume"
```

### 2. Toggle Pause ↔ Resume

**Archivo**: `src/ig_orchestrator/gui/shell/app.py` (en mixin o clase principal)

```python
def _toggle_pause_resume(self) -> None:
    """Toggle entre Pause y Resume."""
    if not self.active_queue_id:
        messagebox.showwarning(
            t("warning"),
            t("toolbar.no_running_batch"),
            parent=self.root
        )
        return
    
    if self.pause_state == "pause":
        self._pause_batch()
    else:
        self._resume_batch()

def _pause_batch(self) -> None:
    """Pausa batch actual."""
    try:
        pause_queue(self.connection, self.active_queue_id)
        self.pause_state = "resume"
        self._update_pause_button()
        self._log(t("toolbar.batch_paused"))
    except Exception as e:
        messagebox.showerror(
            t("error"),
            f"{t('toolbar.pause_failed')}: {e}",
            parent=self.root
        )

def _resume_batch(self) -> None:
    """Reanuda batch pausado."""
    try:
        start_or_resume_queue(self.connection, self.active_queue_id)
        self.pause_state = "pause"
        self._update_pause_button()
        self._log(t("toolbar.batch_resumed"))
    except Exception as e:
        messagebox.showerror(
            t("error"),
            f"{t('toolbar.resume_failed')}: {e}",
            parent=self.root
        )

def _update_pause_button(self) -> None:
    """Actualiza ícono y tooltip del botón según estado."""
    if self.pause_state == "pause":
        # Mostrar ícono de pause
        self.pause_button.config(
            image=self.icons.pause_icon,
            tooltip=t("toolbar.pause")
        )
    else:
        # Mostrar ícono de resume (play)
        self.pause_button.config(
            image=self.icons.resume_icon,
            tooltip=t("toolbar.resume")
        )
```

### 3. Estados de Habilitación del Botón

El botón Pause/Resume debe:
- **Deshabilitado** si no hay batch ejecutándose
- **Habilitado (Pause)** si batch está en ejecución
- **Habilitado (Resume)** si batch está pausado

```python
def _update_button_states(self) -> None:
    """Actualiza estado de habilitación de botones según ejecución."""
    is_running = self.active_queue_id is not None
    
    if not is_running:
        self.run_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.pause_state = "pause"
    else:
        self.run_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.pause_button.config(state=tk.NORMAL)
```

### 4. Sincronizar Estado con Queue

Cuando se reanuda un batch desde "Batches / runs" o CLI, el estado visual debe actualizarse:

```python
def _refresh_queue_status(self) -> None:
    """Actualiza estado de queue desde SQLite."""
    queue = get_open_queue(self.connection)
    if queue is None:
        self.active_queue_id = None
        self.pause_state = "pause"
        self._update_button_states()
        return
    
    self.active_queue_id = queue.id
    
    # Detectar si está pausado
    if queue.status == QueueStatus.PAUSED.value:
        self.pause_state = "resume"
    else:
        self.pause_state = "pause"
    
    self._update_button_states()
    self._update_pause_button()
```

### 5. Traduciones

**Archivo**: `src/ig_orchestrator/gui/i18n.py`

Agregar keys:
```yaml
toolbar:
  pause: "Pause"
  resume: "Resume"
  batch_paused: "Batch paused"
  batch_resumed: "Batch resumed"
  no_running_batch: "No batch running"
  pause_failed: "Failed to pause batch"
  resume_failed: "Failed to resume batch"
```

### 6. Ícono de Resume

**Archivo**: `src/ig_orchestrator/gui/icons.py`

Verificar que existan ícones:
- `pause_icon` (pausa ⏸)
- `resume_icon` (play ▶) — puede ser igual a `play_icon`

## Archivos a Modificar

- `src/ig_orchestrator/gui/chrome/toolbar.py` — Agregar botón Pause/Resume
- `src/ig_orchestrator/gui/shell/app.py` — Agregar lógica de toggle y estados
- `src/ig_orchestrator/gui/batch_queue_service.py` — Revisar funciones `pause_queue()` y `start_or_resume_queue()`
- `src/ig_orchestrator/gui/i18n.py` — Agregar keys de traducción
- `src/ig_orchestrator/gui/icons.py` — Verificar ícones

## Criterios de Aceptación

- [ ] Botón Pause/Resume está en toolbar junto a Run/Stop
- [ ] Botón está deshabilitado cuando no hay batch ejecutándose
- [ ] Botón muestra "Pause" cuando batch está en ejecución
- [ ] Botón muestra "Resume" cuando batch está pausado
- [ ] Click en Pause pausa batch sin cerrarlo
- [ ] Click en Resume continúa desde donde se pausó
- [ ] Estado sincronizado entre ventana principal y "Batches / runs"
- [ ] Logs muestran "Batch paused" / "Batch resumed"
- [ ] Error en pausar/reanudar muestra mensaje descriptivo
- [ ] Cambio de estado es instantáneo en UI

## Testing

```bash
# GUI manual:
# 1. Crear batch con 20+ URLs
# 2. Click en "Run" → comienza ejecución
# 3. Esperar a que descargue al menos 2-3 URLs
# 4. Click en botón Pause → debe pausar
#    - Verificar tooltip cambió a "Resume"
#    - Verificar logs muestran "Batch paused"
# 5. Esperar 5 segundos → debe estar realmente pausado (sin descargas)
# 6. Click en botón Resume → debe continuar
#    - Verificar tooltip cambió a "Pause"
#    - Verificar logs muestran "Batch resumed"
# 7. Descargas deben continuar desde donde se pausaron
# 8. Cerrar app e ir a "Batches / runs" → estado debe estar correcto
# 9. Reabrir app → estado debe sincronizarse

python -m ig_orchestrator gui
```

## Notas de Implementación

- `pause_queue()` y `start_or_resume_queue()` ya existen; revisar si funcionan
- Pausar != Detener (Stop interrumpe; Pause suspende)
- Estado de pause se persiste en SQLite (`queue.status`)
- Verificar que `process_runner` respeta estado pausado
- Considerar si hay cambios necesarios en `orchestration/orquestadores.py`
- Tooltip debe actualizarse cuando cambia estado

## Referencias

- CLAUDE.md: Secciones sobre GUI v2 y ejecución
- Queue service: `src/ig_orchestrator/gui/batch_queue_service.py`
- Toolbar: `src/ig_orchestrator/gui/chrome/toolbar.py`
- Lógica de orquestación: `src/ig_orchestrator/orchestration/orquestadores.py`

---

**Estado**: Pendiente research
**Versión Target**: v2.1.4
**Rama**: v2/gui-ux-stories
