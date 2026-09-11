# Módulo: gui

Índice de la interfaz Tk. Lee `docs/modularizacion_v2.md` primero.

| Quiero cambiar… | Paquete |
|---|---|
| Arranque / composition root | `gui/shell` |
| Menú, toolbar, consola | `gui/chrome` |
| Catálogo | `gui/catalog` |
| Editor de cuenta/URLs | `gui/editor` |
| Tabla de cuentas del lote | `gui/batch_accounts` |
| Ejecutar / detener | `gui/run` |
| Diálogo Lotes | `gui/batches` |
| Cola de secuencia | `gui/queue` |
| Configuración | `gui/settings` |
| Draft en memoria/SQLite | `gui/draft` |
| i18n, iconos, tema, helpers | `gui/shared` |

`gui/app.py` es un shim. La clase vive en `gui/shell/app.py`.

No introducir event-bus. Los paneles hablan por atributos de `InstagramOrchestratorApp`.
