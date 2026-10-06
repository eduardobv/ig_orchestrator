# Tarea v2.1.3: Copiar URLs al Portapapeles en Panel de Errores

## Resumen

En el panel "Accounts in Current Batch", cuando un account tiene URLs con errores, actualmente solo se puede abrir la URL en Chrome con un botón.

Se requiere:
1. Botón "Copy URL" junto al botón de Chrome
2. Click derecho (context menu) en la URL para copiar
3. Permitir seleccionar más de una url a la vez y copiarla.
4. Copiar múltiples URLs si hay más de una con error
5. Notificación visual que confirme la copia ("Copied!")

## Contexto

**Archivo actual**: `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`

Estructura actual:
- Mixin `ProblemUrlsMixin` que abre modal de errores
- Modal lista URLs con error
- Botón "Open in Chrome" abre cada URL en navegador
- No hay opción para copiar URL

Flujo actual:
1. Usuario ve account con estado de error (ej: "Stories not found")
2. Hace click en el status → se abre modal `problem_urls`
3. Modal muestra lista de URLs con errores
4. Botón "Open in Chrome" abre cada una

## Cambios Esperados

### 1. Modificar Estructura de la Modal de Errores

**Archivo**: `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`

Cambiar de lista simple a tabla o frame con acciones por URL:

```python
class ProblemUrlsDialog:
    def __init__(self, parent, account_name, problem_urls_with_errors):
        self.dialog = tk.Toplevel(parent)
        self.problem_urls = problem_urls_with_errors  # [(url, error_type, error_msg), ...]
        
        # Frame con acciones por URL
        self._build_urls_list()
        self._build_buttons()
```

### 2. Cada URL como Fila Seleccionable

Para cada URL, agregar:
- Label con URL truncada o completa
- Botón "Copy"
- Botón "Open Chrome"
- Context menu (click derecho)

Opción A: Tabla (ttk.Treeview)
```python
tree = ttk.Treeview(self.dialog, columns=("URL", "Error", "Actions"))
for url, error_type, error_msg in self.problem_urls:
    tree.insert("", "end", values=(url, error_type))
```

Opción B: Frame por URL (más flexible)
```python
for url, error_type, error_msg in self.problem_urls:
    url_frame = ttk.Frame(urls_container)
    
    # Label seleccionable (para copiar con Ctrl+C)
    url_label = tk.Label(
        url_frame,
        text=url,
        fg="blue",
        cursor="hand2",
        wraplength=400
    )
    url_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    # Botón Copy
    copy_btn = icon_button(
        url_frame,
        icons.copy_icon,
        lambda u=url: self._copy_to_clipboard(u),
        tooltip=t("problem_urls.copy")
    )
    copy_btn.pack(side=tk.RIGHT, padx=5)
    
    # Botón Chrome
    chrome_btn = icon_button(
        url_frame,
        icons.chrome_icon,
        lambda u=url: _open_chrome_tab(u),
        tooltip=t("problem_urls.open_chrome")
    )
    chrome_btn.pack(side=tk.RIGHT, padx=5)
```

### 3. Función: Copiar al Portapapeles

**Archivo**: `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`

```python
def _copy_to_clipboard(self, url: str) -> None:
    """Copia URL al portapapeles y muestra notificación."""
    try:
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(url)
        self.dialog.update()  # Hacer disponible antes de cerrar dialog
        
        # Mostrar notificación visual
        self._show_copy_notification(url)
    except Exception as e:
        messagebox.showerror(
            t("error"),
            f"{t('problem_urls.copy_failed')}: {e}",
            parent=self.dialog
        )

def _show_copy_notification(self, url: str) -> None:
    """Muestra notificación temporal 'Copied!'"""
    # Opción 1: Tooltip temporal
    tooltip = Tooltip(widget, t("problem_urls.copied"), duration=1500)
    
    # Opción 2: Label en status bar (si existe)
    # Opción 3: Toast (si hay framework de notifications)
    
    # Opción 4: Cambiar color del botón temporalmente
    # ... implementar según preferencia UI
```

### 4. Context Menu (Click Derecho)

**Archivo**: `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`

```python
def _bind_context_menu(self, url_label: tk.Label, url: str) -> None:
    """Agrega context menu a etiqueta de URL."""
    context_menu = tk.Menu(self.dialog, tearoff=False)
    context_menu.add_command(
        label=t("problem_urls.copy"),
        command=lambda u=url: self._copy_to_clipboard(u)
    )
    context_menu.add_command(
        label=t("problem_urls.open_chrome"),
        command=lambda u=url: _open_chrome_tab(u)
    )
    context_menu.add_separator()
    context_menu.add_command(
        label=t("problem_urls.copy_all"),
        command=self._copy_all_urls
    )
    
    def show_context_menu(event):
        context_menu.post(event.x_root, event.y_root)
    
    url_label.bind("<Button-3>", show_context_menu)  # Button-3 = click derecho
```

### 5. Copiar Todas las URLs

```python
def _copy_all_urls(self) -> None:
    """Copia todas las URLs al portapapeles, una por línea."""
    try:
        all_urls = "\n".join(url for url, _, _ in self.problem_urls)
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(all_urls)
        self.dialog.update()
        
        messagebox.showinfo(
            t("success"),
            f"{t('problem_urls.copied_count')}: {len(self.problem_urls)}",
            parent=self.dialog
        )
    except Exception as e:
        messagebox.showerror(
            t("error"),
            f"{t('problem_urls.copy_failed')}: {e}",
            parent=self.dialog
        )
```

### 6. Traduciones

**Archivo**: `src/ig_orchestrator/gui/i18n.py`

Agregar keys:
```yaml
problem_urls:
  title: "Problem URLs"
  copy: "Copy URL"
  open_chrome: "Open in Chrome"
  copy_all: "Copy All URLs"
  copied: "Copied!"
  copied_count: "Copied {count} URLs"
  copy_failed: "Failed to copy to clipboard"
  error_title: "Error"
  account: "Account"
  url: "URL"
  error_type: "Error Type"
```

### 7. Mejora de UX: URL Seleccionable

Hacer URL copiable con **Ctrl+C** si está seleccionada:

```python
def _bind_copy_shortcut(self) -> None:
    """Permite Ctrl+C para copiar URL seleccionada."""
    def on_ctrl_c(event):
        try:
            # Obtener texto seleccionado del widget
            selected_text = event.widget.selection_get()
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append(selected_text)
            self.dialog.update()
            self._show_copy_notification(selected_text)
        except tk.TclError:
            pass  # Sin selección
    
    self.dialog.bind("<Control-c>", on_ctrl_c)
```

## Archivos a Modificar

- `src/ig_orchestrator/gui/batch_accounts/problem_urls.py` — Agregar botones, context menu, copy functions
- `src/ig_orchestrator/gui/i18n.py` — Agregar keys de traducción
- `src/ig_orchestrator/gui/icons.py` — Agregar ícono de copy si no existe
- Opcional: `src/ig_orchestrator/gui/theme.py` — Mejorar tooltip si se usa

## Criterios de Aceptación

- [ ] Modal de errores muestra URLs con botones Copy y Open Chrome por cada una
- [ ] Botón Copy abre portapapeles con la URL
- [ ] Click derecho en URL abre context menu con opciones
- [ ] Context menu incluye "Copy URL", "Open Chrome", "Copy All URLs"
- [ ] Notificación visual ("Copied!") confirma copia exitosa
- [ ] Ctrl+C copia URL seleccionada con el mouse
- [ ] Error en copiar (sin clipboard) muestra mensaje descriptivo
- [ ] "Copy All URLs" copia todas con salto de línea
- [ ] Modal posicionada según Tarea v2.1.1 (centrada)

## Testing

```bash
# GUI manual:
# 1. Crear batch con URLs que generan errores conocidos
# 2. Ejecutar batch parcialmente hasta que al menos 1 account tenga errores
# 3. Click en account con errores → abre modal
# 4. Verificar botones Copy y Open Chrome presentes
# 5. Click en Copy → verifica portapapeles:
#    - Abrir Notepad (Win+R, notepad)
#    - Ctrl+V → debe aparecer la URL
# 6. Click derecho en URL → verifica context menu
# 7. Click derecho → "Copy All URLs"
# 8. Ctrl+V en Notepad → debe aparecer todas las URLs separadas por salto de línea
# 9. Cerrar modal y reabrir → cambios persisten

python -m ig_orchestrator gui
```

## Notas de Implementación

- Usar `dialog.clipboard_clear()` y `dialog.clipboard_append()` antes de `dialog.update()`
- Limpiar clipboard después de cierto tiempo (puede ser política)
- Context menu con `Button-3` en Linux/Mac es `Button-2` o varía; usar `event_generate()`
- URLs pueden contener caracteres especiales; escapar si es necesario para navegadores
- Si URL está truncada visualmente, mostrar tooltip con URL completa
- Frame con scrollbar si hay muchas URLs (10+)

## Referencias

- CLAUDE.md: Secciones sobre GUI v2 y UX
- Archivo actual: `src/ig_orchestrator/gui/batch_accounts/problem_urls.py`
- Chrome opener: `src/ig_orchestrator/gui/shared/helpers.py:_open_chrome_tab()`
- Clipboard: `src/ig_orchestrator/gui/text_edit.py` (puede tener helpers)

---

**Estado**: Pendiente research
**Versión Target**: v2.1.3
**Rama**: v2/gui-ux-stories
