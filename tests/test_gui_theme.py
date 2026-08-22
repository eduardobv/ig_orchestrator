from __future__ import annotations

import pytest

from ig_orchestrator.gui.theme import apply_light_theme, ui_font_option


def test_ui_font_option_braces_segoe_ui() -> None:
    spec = ui_font_option("Segoe UI", 10)
    assert spec == "{Segoe UI} 10"
    assert "Segoe UI 10" != spec


def test_apply_light_theme_can_create_menu() -> None:
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    try:
        apply_light_theme(root)
        menubar = tk.Menu(root)
        menubar.add_command(label="File")
        root.config(menu=menubar)
        root.update_idletasks()
    finally:
        root.destroy()
