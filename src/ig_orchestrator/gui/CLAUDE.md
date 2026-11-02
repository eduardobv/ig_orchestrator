# gui

@MODULE.md

- **No abrir `gui/app.py`** (es un shim); la clase vive en `gui/shell/app.py`. Leer antes `docs/modularizacion_v2.md`.
- Cada subpaquete tiene su `MODULE.md`; léelo antes de tocarlo. No introducir event-bus: los paneles hablan por atributos de `InstagramOrchestratorApp`.
- **Todo menú, menú contextual, modal, botón o ajuste nuevo/cambiado/eliminado** exige actualizar `docs/manual-usuario.md` (qué hace y qué abre) y los textos en `gui/locales`.
- El disco y la red nunca se tocan en el hilo de Tk (hilos de trabajo con su propia conexión SQLite).
- No escribir en SQLite v1 desde la GUI.

## Reglas por área

- **Lotes** (`gui/batches/`): *Reiniciar desde cero…* (`restart.py`, menú Lote y botón/clic derecho **Reiniciar…** del modal de lotes, cualquier estado salvo GUARDADO; v4.11.0–v4.12.1; no toca archivos, solo la base de la GUI). *Informe de ejecución…* (`execution_report.py`, menú Lote y clic derecho del modal de lotes; v4.10.0).
- **Estado de cuentas**: ver `account_status/CLAUDE.md`.
- **Ajustes de ejecución** (*Configuración > Ejecución*): ver `orchestration/CLAUDE.md`.
