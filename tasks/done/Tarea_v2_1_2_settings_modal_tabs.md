# Tarea v2.1.2: Refactorizar Settings Modal con Pestañas y Guardar/Cancelar

## Resumen

La modal de Settings debe transformarse de una larga lista a una interfaz con pestañas, incluir botones "Save" y "Cancel" para permitir confirmar o descartar cambios.

Cambios:
1. Reorganizar configuraciones en pestañas (General, Telegram, Paths, Download, Advanced)
2. Agregar botón "Save" para aplicar cambios
3. Agregar botón "Cancel" para descartar cambios sin guardar
4. Validar configuraciones antes de guardar
5. Mostrar mensaje de confirmación si hay cambios sin guardar

## Contexto

**Archivo actual**: `src/ig_orchestrator/gui/settings/dialog.py`

Estructura actual:
- Modal larga con múltiples campos (Telegram API ID/Hash, paths, timeouts, etc.)
- Solo botón "Close" (sin guardar/cancelar explícitos)
- Los cambios se aplican directamente sin confirmación

Settings en `src/ig_orchestrator/settings.py`:
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
- Paths: `TELEGRAM_DESKTOP_DOWNLOAD_FOLDER`, `WORKING_FOLDER`, `REPORTS_FOLDER`
- Timeouts: `DOWNLOAD_WAIT_TIMEOUT_SECONDS`, `DOWNLOAD_STABLE_SECONDS`
- Reintentos: `MAX_RETRIES`, `RETRY_BASE_SECONDS`, `RETRY_MAX_SECONDS`
- Opcionales: `POST_PROCESS_ENABLED`, `POST_PROCESS_COMMAND`

## Cambios Esperados

### 1. Refactorizar `SettingsDialogMixin`

**Archivo**: `src/ig_orchestrator/gui/settings/dialog.py`

Cambiar estructura:
```python
class SettingsDialogMixin:
    def open_settings_dialog(self) -> None:
        """Abre diálogo de settings con pestañas."""
        dialog = SettingsDialogWithTabs(self.root, self.settings, self.connection)
        self.root.wait_window(dialog.dialog)
        if dialog.saved:  # ← Nuevo flag
            self._on_settings_saved()
```

### 2. Nueva clase: `SettingsDialogWithTabs`

**Archivo**: `src/ig_orchestrator/gui/settings/dialog.py`

Estructura:
```python
class SettingsDialogWithTabs:
    def __init__(self, parent: tk.Tk, settings: Settings, connection: Connection):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(t("settings.title"))
        self.settings = settings
        self.connection = connection
        self.saved = False
        self._original_values = deepcopy(settings.__dict__)  # Para rollback
        
        # Crear notebook (ttk.Notebook)
        self.notebook = ttk.Notebook(self.dialog)
        self._build_general_tab()
        self._build_telegram_tab()
        self._build_paths_tab()
        self._build_download_tab()
        self._build_advanced_tab()
        
        # Botones: Save, Cancel
        self._build_buttons()
```

### 3. Pestañas

#### Tab 1: General
- Idioma (dropdown: Español, English)
- Posición de ventana (new, Tarea v2.1.1): Left/Center/Right
- Tema (Light/Dark/Auto)
- Sonido de finalización (checkbox)

#### Tab 2: Telegram
- Telegram API ID (Entry, masked o mostrar)
- Telegram API Hash (Entry, masked o mostrar)
- Bot Username (Entry, ej: @example_bot)
- Session Name (Entry, ej: telegram_user_session)
- Botón "Test Connection" (envía mensaje de prueba)

#### Tab 3: Paths
- Telegram Desktop Download Folder (Path selector button + Entry)
- Working Folder (Path selector button + Entry)
- Reports Folder (Path selector button + Entry)
- SQLite DB Path (Path selector button + Entry)
- GUI SQLite DB Path (Path selector button + Entry)

#### Tab 4: Download
- Max Retries (Spinbox: 1-10)
- Retry Base Seconds (Spinbox: 10-300)
- Retry Max Seconds (Spinbox: 100-3600)
- Download Wait Timeout (Spinbox: 60-900)
- Download Stable Seconds (Spinbox: 5-60)

#### Tab 5: Advanced
- Post Process Enabled (Checkbox)
- Post Process Command (Path selector + Entry, habilitado si checkbox)
- Stories First (Checkbox)
- Log Level (Dropdown: DEBUG, INFO, WARNING, ERROR)
- Clear Logs on Startup (Checkbox)

### 4. Validación de Cambios

```python
def _validate_settings(self) -> tuple[bool, str]:
    """Valida campos requeridos y rangos permitidos."""
    errors = []
    
    # Validar API ID/Hash no vacías
    if not self.telegram_api_id_entry.get().strip():
        errors.append(t("settings.error.api_id_required"))
    
    # Validar paths existen
    for path_var, label in self.path_fields:
        if not Path(path_var.get()).exists():
            errors.append(f"{label}: {t('settings.error.path_not_found')}")
    
    # Validar spinboxes están en rango
    # ...
    
    if errors:
        return False, "\n".join(errors)
    return True, ""
```

### 5. Botones: Save y Cancel

```python
def _build_buttons(self) -> None:
    button_frame = ttk.Frame(self.dialog)
    
    save_button = ttk.Button(
        button_frame,
        text=t("settings.save"),
        command=self._on_save
    )
    cancel_button = ttk.Button(
        button_frame,
        text=t("settings.cancel"),
        command=self._on_cancel
    )
    
    save_button.pack(side=tk.RIGHT, padx=5)
    cancel_button.pack(side=tk.RIGHT, padx=5)

def _on_save(self) -> None:
    """Guarda cambios y cierra diálogo."""
    is_valid, error_msg = self._validate_settings()
    if not is_valid:
        messagebox.showerror(t("settings.error"), error_msg, parent=self.dialog)
        return
    
    # Aplicar cambios a Settings
    self._apply_changes_to_settings()
    self.settings.save()  # Persistir en .env
    
    self.saved = True
    self.dialog.destroy()

def _on_cancel(self) -> None:
    """Descarta cambios y cierra diálogo."""
    # Restaurar valores originales
    self.settings.__dict__ = deepcopy(self._original_values)
    self.dialog.destroy()
```

### 6. Traduciones

**Archivo**: `src/ig_orchestrator/gui/i18n.py` (o locales)

Agregar keys:
```yaml
settings:
  title: "Settings"
  save: "Save"
  cancel: "Cancel"
  tabs:
    general: "General"
    telegram: "Telegram"
    paths: "Paths"
    download: "Download"
    advanced: "Advanced"
  error:
    api_id_required: "Telegram API ID is required"
    api_hash_required: "Telegram API Hash is required"
    path_not_found: "Path does not exist"
    validation_failed: "Settings validation failed"
  test_connection: "Test Connection"
  connection_success: "Connected successfully!"
  connection_failed: "Connection failed"
```

## Archivos a Modificar

- `src/ig_orchestrator/gui/settings/dialog.py` — Refactorizar con ttk.Notebook y botones Save/Cancel
- `src/ig_orchestrator/gui/i18n.py` — Agregar nuevas keys de traducción
- `src/ig_orchestrator/gui/shell/app.py` — Opcional: agregar callback `_on_settings_saved()`
- `src/ig_orchestrator/settings.py` — Agregar método `save()` si no existe

## Criterios de Aceptación

- [ ] Settings modal tiene 5 pestañas navegables
- [ ] Cada pestaña agrupa configuraciones relacionadas
- [ ] Botón "Save" persiste cambios en `.env` y Settings
- [ ] Botón "Cancel" descarta cambios sin guardar
- [ ] Validación impide guardar configuraciones inválidas
- [ ] Mensaje de error descriptivo si hay problemas
- [ ] Cambios en Settings toman efecto inmediatamente en GUI (ej: idioma, tema)
- [ ] No mostrar "unsaved changes" warning si no hay cambios
- [ ] Modal posicionada según Tarea v2.1.1 (centrada en padre)

## Testing

```bash
# Verificar que Settings.save() persiste en .env
python -c "
from ig_orchestrator.settings import Settings
s = Settings()
# ... hacer cambios ...
s.save()
# Verificar .env actualizado
"

# GUI manual:
# 1. Abrir Settings desde menú
# 2. Cambiar valores en diferentes pestañas
# 3. Presionar Cancel → valores deben revertirse
# 4. Cambiar valores nuevamente
# 5. Presionar Save → valores deben persistir
# 6. Cerrar y abrir Settings nuevamente → valores guarдано
# 7. Intentar guardar con API ID vacía → error

python -m ig_orchestrator gui
```

## Notas de Implementación

- Usar `deepcopy()` para guardar estado original de Settings
- Usar `ttk.Notebook` para pestañas (tema automático)
- Botones en frame separado debajo de notebook
- Validar **antes** de aplicar cambios
- Si hay errores, mantener dialog abierto
- Usar `parent=self.dialog` en messageboxes para modalidad correcta
- Considerar checkbutton para campos condicionales (ej: Post Process Command si enabled)

## Referencias

- CLAUDE.md: Secciones sobre Settings y GUI v2
- Archivo actual: `src/ig_orchestrator/gui/settings/dialog.py`
- Módulo Settings: `src/ig_orchestrator/settings.py`
- Translations: `src/ig_orchestrator/gui/i18n.py`

---

**Estado**: Pendiente research
**Versión Target**: v2.1.2
**Rama**: v2/gui-ux-stories
