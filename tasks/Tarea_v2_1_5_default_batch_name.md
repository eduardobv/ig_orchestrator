# Tarea v2.1.5: Nombre de Batch por Defecto con Timestamp

## Resumen

Actualmente, al inicializar la aplicación, el nombre del batch es el del último batch ejecutado.

Se requiere:
1. Nombre de batch por defecto sea `descargas_YYYY_MM_DD_HH_MM_SS`
2. Generar nuevo nombre cada vez que se inicia la app
3. Cambiar botón "New Batch" para usar el mismo formato
4. Permitir editar el nombre manualmente antes de ejecutar

## Contexto

**Archivos clave**:
- `src/ig_orchestrator/gui/shared/helpers.py:_latest_executed_batch_name()` — Obtiene último batch
- `src/ig_orchestrator/gui/shared/helpers.py:_suggest_batch_name()` — Sugiere nombre
- `src/ig_orchestrator/gui/shell/app.py` — Inicialización de GUI
- `src/ig_orchestrator/gui/batch_draft.py` — Modelo de batch en edición

Flujo actual:
```python
# En app.py.__init__()
self.batch_name_var = tk.StringVar(value=_latest_executed_batch_name(self.connection))
```

Esto reutiliza el nombre del último batch ejecutado. El usuario debe cambiar manualmente si quiere otro nombre.

## Cambios Esperados

### 1. Nueva Función: Generar Nombre por Defecto

**Archivo**: `src/ig_orchestrator/gui/shared/helpers.py`

```python
from datetime import datetime

def _generate_default_batch_name() -> str:
    """
    Genera nombre de batch con timestamp actual.
    
    Formato: descargas_YYYY_MM_DD_HH_MM_SS
    Ejemplo: descargas_2026_10_03_14_30_45
    
    Returns:
        Nombre formateado con timestamp actual
    """
    now = datetime.now()
    return now.strftime("descargas_%Y_%m_%d_%H_%M_%S")

# Pruebas:
# >>> _generate_default_batch_name()
# 'descargas_2026_10_03_14_30_45'
```

### 2. Modificar Inicialización en `app.py`

**Archivo**: `src/ig_orchestrator/gui/shell/app.py` (línea ~278 aprox.)

Cambiar de:
```python
# Antes
self.batch_name_var = tk.StringVar(value=_latest_executed_batch_name(self.connection))
```

A:
```python
# Después
self.batch_name_var = tk.StringVar(value=_generate_default_batch_name())
```

### 3. Modificar Botón "New Batch"

**Archivo**: `src/ig_orchestrator/gui/shell/app.py` o `src/ig_orchestrator/gui/batch_draft_service.py`

Función actual (probablemente):
```python
def new_batch(self) -> None:
    """Crea nuevo batch limpiando editor."""
    self.batch_name_var.set("")
    self.batch_urls_var.set("")
    self._refresh_table()
```

Cambiar a:
```python
def new_batch(self) -> None:
    """Crea nuevo batch con nombre por defecto."""
    self.batch_name_var.set(_generate_default_batch_name())
    self.batch_urls_var.set("")
    self._refresh_table()
    self._log(t("batch.new_batch_created", name=self.batch_name_var.get()))
```

### 4. Verificar Unicidad del Nombre

Aunque el timestamp es único, validar que el nombre no exista ya en SQLite:

**Archivo**: `src/ig_orchestrator/gui/shell/app.py`

```python
def _validate_batch_name(self, batch_name: str) -> bool:
    """
    Valida que el nombre de batch sea válido y único.
    
    Returns:
        True si es válido, False si ya existe
    """
    batch_name = batch_name.strip()
    
    if not batch_name:
        messagebox.showwarning(
            t("warning"),
            t("batch.error.empty_name"),
            parent=self.root
        )
        return False
    
    # Verificar que no existe batch con este nombre
    from ig_orchestrator.db.batch_repository import get_batch_by_name
    existing = get_batch_by_name(self.connection, batch_name)
    if existing:
        messagebox.showwarning(
            t("warning"),
            t("batch.error.name_already_exists", name=batch_name),
            parent=self.root
        )
        return False
    
    return True
```

Usar esta validación en:
- Antes de ejecutar batch (Run)
- Antes de guardar como DRAFT

### 5. UI: Mostrar Sugerencia de Nombre

En el editor de batch, junto al campo de nombre, mostrar:
```
Batch Name: [descargas_2026_10_03_14_30_45]
            (Auto-generated with timestamp)
```

O un botón "Generate New Name":
```python
def _build_batch_name_section(self) -> None:
    name_frame = ttk.Frame(self.editor_panel)
    
    ttk.Label(name_frame, text=t("batch.name")).pack(side=tk.LEFT)
    ttk.Entry(name_frame, textvariable=self.batch_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    # Botón para generar nuevo nombre
    generate_btn = icon_button(
        name_frame,
        self.icons.refresh_icon,
        self._generate_new_batch_name,
        tooltip=t("batch.generate_new_name")
    )
    generate_btn.pack(side=tk.LEFT, padx=5)

def _generate_new_batch_name(self) -> None:
    """Genera nuevo nombre de batch con timestamp."""
    new_name = _generate_default_batch_name()
    self.batch_name_var.set(new_name)
    self._log(f"New batch name: {new_name}")
```

### 6. Traducciones

**Archivo**: `src/ig_orchestrator/gui/i18n.py`

Agregar keys:
```yaml
batch:
  name: "Batch Name"
  generate_new_name: "Generate New Name"
  new_batch_created: "New batch created: {name}"
  error:
    empty_name: "Batch name cannot be empty"
    name_already_exists: "Batch '{name}' already exists in database"
    validation_failed: "Batch name validation failed"
```

### 7. Comportamiento del Editor

El flujo debe ser:
1. App inicia → nombre por defecto es `descargas_YYYY_MM_DD_HH_MM_SS`
2. Usuario paste URLs
3. Click "Run" → valida nombre único, crea batch
4. Si quiere otro batch: Click "New Batch" → nuevo nombre generado
5. Si quiere editar nombre: puede escribir manualmente
6. Si quiere timestamp nuevo: Click en botón "Generate New Name"

## Archivos a Modificar

- `src/ig_orchestrator/gui/shared/helpers.py` — Agregar `_generate_default_batch_name()`
- `src/ig_orchestrator/gui/shell/app.py` — Usar `_generate_default_batch_name()` en init y botón "New Batch"
- `src/ig_orchestrator/gui/batch_draft_service.py` — Cambiar lógica de "New Batch" si aplica
- `src/ig_orchestrator/gui/i18n.py` — Agregar keys de traducción
- Opcional: `src/ig_orchestrator/db/batch_repository.py` — Verificar función `get_batch_by_name()`

## Criterios de Aceptación

- [ ] Al inicializar app, nombre de batch es `descargas_YYYY_MM_DD_HH_MM_SS` (timestamp actual)
- [ ] Cada vez que se abre la app, nombre generado es diferente (timestamp diferente)
- [ ] Botón "New Batch" genera nuevo nombre con timestamp actual
- [ ] Usuario puede editar nombre manualmente
- [ ] Botón "Generate New Name" cambia nombre a nuevo timestamp
- [ ] Validación previene crear batch con nombre duplicado
- [ ] Mensaje de error si nombre está vacío
- [ ] Mensaje de error si nombre ya existe en base de datos
- [ ] Cambio de nombre se refleja inmediatamente en UI
- [ ] Nombre se persiste en SQLite cuando se ejecuta batch

## Testing

```bash
# Testing manual:
# 1. Inicializar app → verificar nombre en campo es descargas_YYYY_MM_DD_HH_MM_SS
# 2. Anotar el nombre
# 3. Cerrar app
# 4. Esperar 2 segundos
# 5. Abrir app nuevamente → nombre debe ser diferente (timestamp más reciente)
# 6. Click "New Batch" → nombre cambia a nuevo timestamp
# 7. Editar nombre manualmente a "test_batch_123"
# 8. Agregar URLs
# 9. Click "Run" → debe ejecutar con nombre custom
# 10. Esperar a que termine o pausar
# 11. Ir a "Batches / runs" → debe mostrar "test_batch_123"
# 12. Volver a "Draft"
# 13. Click "New Batch" → nombre es nuevo timestamp
# 14. Intentar ejecutar 2 batches sin cambiar nombre entre ejecuciones → debe fallar con error de duplicado

# Testing unitario:
python -c "
from ig_orchestrator.gui.shared.helpers import _generate_default_batch_name
import time

name1 = _generate_default_batch_name()
print(f'Name 1: {name1}')
assert name1.startswith('descargas_')

time.sleep(1)
name2 = _generate_default_batch_name()
print(f'Name 2: {name2}')

assert name1 != name2, 'Names should be different'
print('Test passed!')
"

python -m ig_orchestrator gui
```

## Notas de Implementación

- Usar `datetime.now()` (hora local) no `datetime.utcnow()`
- Formato: `YYYY_MM_DD_HH_MM_SS` con underscores como separador
- Ejemplo válido: `descargas_2026_10_03_14_30_45`
- Considerar que si user hace click "New Batch" muy rápido (dentro del mismo segundo), timestamp será igual; no es problema, pero puede ser confuso
- Validación de nombre único debe ocurrir **antes** de SQLite insert
- Si nombre es vacío, campo debe tener valor por defecto al abrir editor

## Referencias

- CLAUDE.md: Secciones sobre GUI v2 y batches
- Helper actual: `src/ig_orchestrator/gui/shared/helpers.py:_latest_executed_batch_name()`
- Inicialización: `src/ig_orchestrator/gui/shell/app.py` (línea ~278)
- Database: `src/ig_orchestrator/db/batch_repository.py`

---

**Estado**: Pendiente research
**Versión Target**: v2.1.5
**Rama**: v2/gui-ux-stories
