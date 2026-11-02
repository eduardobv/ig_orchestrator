# feat-gui-28 · Pegado con salto de línea y «Abrir en Chrome» en la tabla del lote (v4.19.0)

## Objetivo
1. En el cuadro de URLs del Editor, Ctrl+V, *Pegar* del clic derecho y el botón Pegar añaden un salto de línea tras lo pegado.
2. En «Cuentas del lote actual», clic derecho → **Abrir en Chrome** y doble clic abren el perfil de Instagram de la cuenta.

## Resultado de la implementación
* `gui/editor/text_edit.py`: `with_trailing_newline` y parámetro `paste_newline` de `bind_edit_context_menu` (enlaza Ctrl+V / `<<Paste>>` con `break`); usado solo por `urls_text`. `_paste_urls` también lo aplica.
* `gui/batch_accounts/problem_urls.py`: `_open_selected_account_in_chrome` y `_on_batch_double_click` (ignora doble clic fuera de una fila); entrada nueva en `batch_menu` (`panel.py`).
* El doble clic ya no abre *Ver URLs…*; sigue en el clic derecho.

## No se hizo
* No se probó con Chrome/pantalla real en esta sesión (solo tests).
