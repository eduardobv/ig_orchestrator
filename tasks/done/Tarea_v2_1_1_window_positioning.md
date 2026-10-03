# Tarea v2.1.1: Posicionamiento Configurable de Ventanas

## Resumen

La aplicación se abre siempre a la izquierda del monitor. Se requiere:
1. Configurar en "Settings" la posición inicial: derecha, centro o izquierda
2. Las ventanas modales deben abrirse centradas en la ventana principal
3. Si la ventana principal está maximizada, las modales se abren centradas en pantalla
4. Si la ventana principal está en la derecha, las modales se abren centradas en pantalla

## Contexto

**Archivo clave**: `src/ig_orchestrator/gui/shared/helpers.py:_half_screen_geometry()`

Función actual:
```python
def _half_screen_geometry(screen_width: int, screen_height: int) -> str:
    width = max(860, screen_width // 2)
    height = max(680, screen_height - 80)
    return f"{width}x{height}+0+0"  # Siempre a la izquierda (+0+0)
```

La GUI v2 guarda configuraciones en Settings y SQLite. Las modales están distribuidas en:
- `src/ig_orchestrator/gui/settings/dialog.py`
- `src/ig_orchestrator/gui/batches/dialog.py`
- `src/ig_orchestrator/gui/run/leftovers.py`
- Otras modales en módulos específicos

## Cambios Esperados

### 1. Agregar Setting: `window_position`

**Archivo**: `src/ig_orchestrator/settings.py`

- Nueva propiedad: `window_position: Literal["left", "center", "right"] = "left"`
- Persistencia en `.env` opcional (default: "left")

### 2. Modificar `_half_screen_geometry()`

**Archivo**: `src/ig_orchestrator/gui/shared/helpers.py`

Nueva firma:
```python
def _half_screen_geometry(
    screen_width: int, 
    screen_height: int,
    position: Literal["left", "center", "right"] = "left"
) -> str:
    """
    Posiciona ventana a izquierda, centro o derecha del monitor.
    
    Args:
        screen_width: Ancho total de pantalla
        screen_height: Alto total de pantalla
        position: "left", "center" o "right"
    
    Returns:
        Geometría en formato "WxH+X+Y"
    """
```

Cálculos:
- **Left**: `+0+0` (actual)
- **Center**: `+(screen_width - width) // 2 + y_offset`
- **Right**: `+(screen_width - width)+0`

### 3. Nueva función: `center_modal_on_parent()`

**Archivo**: `src/ig_orchestrator/gui/shared/helpers.py`

```python
def center_modal_on_parent(
    modal: tk.Toplevel,
    parent: tk.Tk | tk.Toplevel,
    is_parent_maximized: bool = False
) -> None:
    """
    Centra una modal en su ventana padre, o en pantalla si padre está maximizado.
    
    Args:
        modal: Ventana modal a posicionar
        parent: Ventana padre (raíz de GUI)
        is_parent_maximized: True si la ventana padre está maximizada
    """
```

### 4. UI de Settings

**Archivo**: `src/ig_orchestrator/gui/settings/dialog.py`

Agregar radiobuttons/combobox para seleccionar posición:
```
☐ Posición de ventana principal
  ◉ Izquierda  ○ Centro  ○ Derecha
```

### 5. Actualizar inicialización en `app.py`

**Archivo**: `src/ig_orchestrator/gui/shell/app.py` (línea ~270)

```python
self.root.geometry(
    _half_screen_geometry(
        self.root.winfo_screenwidth(),
        self.root.winfo_screenheight(),
        self.settings.window_position  # ← Nuevo parámetro
    )
)
```

### 6. Aplicar a todas las modales

Buscar y reemplazar llamadas `.place()` / `.geometry()` en modales. Ejemplo:

```python
# Antes
dialog = tk.Toplevel(self.root)
dialog.geometry("600x400+100+100")

# Después
dialog = tk.Toplevel(self.root)
is_maximized = self.root.state() == 'zoomed'
center_modal_on_parent(dialog, self.root, is_maximized)
```

## Archivos a Modificar

- `src/ig_orchestrator/settings.py` — Agregar `window_position`
- `src/ig_orchestrator/gui/shared/helpers.py` — Modificar `_half_screen_geometry()`, agregar `center_modal_on_parent()`
- `src/ig_orchestrator/gui/shell/app.py` — Pasar `window_position` a `_half_screen_geometry()`
- `src/ig_orchestrator/gui/settings/dialog.py` — UI para seleccionar posición
- `src/ig_orchestrator/gui/batches/dialog.py` — Centrar modal
- `src/ig_orchestrator/gui/run/leftovers.py` — Centrar modal
- Otras modales encontradas (búsqueda exhaustiva)

## Criterios de Aceptación

- [ ] Setting `window_position` persiste en `.env`
- [ ] Ventana principal se abre en posición seleccionada (left/center/right)
- [ ] UI en Settings permite cambiar posición
- [ ] Todas las modales se abren centradas en padre
- [ ] Si padre está maximizado, modal se abre centrada en pantalla
- [ ] Si padre está en derecha, modal se abre centrada en pantalla (no en derecha)
- [ ] Cambio de posición en Settings toma efecto en siguiente apertura
- [ ] No regresar a posición anterior si usuario minimiza/restaura

## Testing

```bash
# Verificar Settings carga/guarda posición
python -c "from ig_orchestrator.settings import Settings; s = Settings(); print(s.window_position)"

# Verificar geometría calculada correctamente
from ig_orchestrator.gui.shared.helpers import _half_screen_geometry
print(_half_screen_geometry(1920, 1080, "left"))    # Izquierda
print(_half_screen_geometry(1920, 1080, "center"))  # Centro
print(_half_screen_geometry(1920, 1080, "right"))   # Derecha

# GUI manual: abrir app, mover ventana, cambiar Settings, reiniciar
python -m ig_orchestrator gui
```

## Notas de Implementación

- Usar `self.root.state() == 'zoomed'` para detectar si ventana está maximizada
- `winfo_width()`, `winfo_height()` solo funcionan post-`update_idletasks()`
- Aplicar `update_idletasks()` antes de llamar `center_modal_on_parent()`
- Las modales pueden tener `transient(parent)` para mejor comportamiento de ventana flotante

## Referencias

- CLAUDE.md: Secciones sobre GUI v2 y Settings
- Función actual: `src/ig_orchestrator/gui/shared/helpers.py:143-146`
- Módulos de modales: batches, settings, run, stories, catalog

---

**Estado**: Pendiente research
**Versión Target**: v2.1.1
**Rama**: v2/gui-ux-stories
