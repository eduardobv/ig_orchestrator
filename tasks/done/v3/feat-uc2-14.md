# feat-uc2-14 — Estado según carpeta, color unificado de eliminadas y ventanas centradas (v3.14.0)

Feat incremental de v3 (catálogo, UC2) pedido tras probar el movimiento de cuentas.

## Problemas

1. Las cuentas «eliminadas» antiguas (estado *Disabled*) se veían rojas y las marcadas ahora (estado *Eliminada*) casi moradas.
2. Mover una cuenta a una carpeta `-Deleted` no la marcaba como eliminada, y sacarla de ella no la reactivaba.
3. Las modales nuevas se abrían en la esquina superior izquierda; las antiguas, centradas.

## Qué se hizo

- **Color único:** el estado *Eliminada* usa siempre el color de *Disabled* (`#f4cccc`, el de Ajustes → Interfaz), ignorando cualquier valor morado guardado.
- **El estado sigue a la carpeta** (`AccountLifecycleService.sync_with_location`, `preview_status_changes`, `affected_accounts`): tras **mover** (no renombrar) una cuenta o una carpeta con cuentas:
  - a una carpeta cuyo nombre acaba en `-Deleted`/`-Delete`, o a la carpeta de eliminadas configurada (o dentro de ella) → pasa a **Eliminada** (guarda el estado anterior y la ruta anterior, igual que «Marcar como eliminada»);
  - fuera de ellas, si estaba Eliminada → vuelve al **estado que tenía antes** (o Activa si no se conoce).
  La vista previa del plan lista estos cambios («Estado: @cuenta → Eliminada/Reactivada») antes de ejecutar. **Deshacer** en *Operaciones de disco* también devuelve el estado.
- **Ventanas centradas** (`gui/shared/window_position.py`): todas las ventanas (`tk.Toplevel` y diálogos de texto) se abren con **su centro en el centro del monitor donde está la ventana principal**, cualquier resolución o monitor (incluye barra de título y bordes). Nacen transparentes y se muestran al colocarse (sin parpadeo en la esquina). Tooltips y avisos sin borde no se mueven. `center_modal_on_parent` usa la misma función.

## No incluido

- Renombrar una carpeta a `…-Deleted` no cambia el estado de sus cuentas (solo los movimientos).
- `-Inactive` no cambiaba el estado en esta versión (resuelto en `feat-uc2-15`, v3.15.0).
- Mover cuentas fuera de la app (Explorador) lo detecta la sincronización, que no cambia estados.

## Pruebas

`tests/library/test_status_follows_folder.py` (entrar/salir de -Deleted, estado previo, carpeta de eliminadas, deshacer), `tests/gui/test_window_position.py` (fórmula para varias resoluciones y monitores, ventana real centrada, ventanas sin borde, color unificado) y comprobación con la app real: modales centradas con error ≤ 1 px.
