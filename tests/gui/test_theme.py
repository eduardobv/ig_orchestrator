from __future__ import annotations

import pytest

from ig_orchestrator.gui.app import InstagramOrchestratorApp
from ig_orchestrator.gui.i18n import load_language
from ig_orchestrator.gui.icons import IconSet
from ig_orchestrator.gui.theme import apply_light_theme, compact_icon_button, ui_font_option


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


def test_compact_button_style_is_registered() -> None:
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    try:
        apply_light_theme(root)
        image = tk.PhotoImage(master=root, width=16, height=16)
        button = compact_icon_button(
            root, image=image, command=lambda: None, tooltip="paste"
        )
        assert str(button.cget("style")) == "Compact.TButton"
        ttk.Style(root).lookup("Compact.TButton", "padding")
    finally:
        root.destroy()


def test_editor_layout_places_add_update_on_username_row() -> None:
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    try:
        apply_light_theme(root)
        load_language("es")
        app = object.__new__(InstagramOrchestratorApp)
        app.root = root
        app.icons = IconSet(root)
        app.username_var = tk.StringVar()
        app.stories_var = tk.BooleanVar(value=False)
        app.new_account_var = tk.BooleanVar(value=False)
        app.catalog_update_var = tk.BooleanVar(value=False)
        app.owner_id_var = tk.StringVar()
        app.start_init_date_var = tk.StringVar()
        app.destination_path_var = tk.StringVar()
        app.indicators_var = tk.StringVar()
        app.catalog_entries = []
        app.destination_paths = []
        app._apply_catalog_date = lambda: None
        app._paste_username = lambda: None
        app._clear_username = lambda: None
        app._update_indicators = lambda: None
        app._on_new_account_toggle = lambda: None
        app._on_catalog_update_toggle = lambda: None
        app._paste_and_upsert = lambda: None
        app._upsert_account = lambda: None
        app._paste_urls = lambda: None
        app._normalize_urls = lambda: None
        app._clear_editor = lambda: None
        parent = ttk.Frame(root)
        parent.pack(fill="both", expand=True)
        app._build_editor(parent)
        root.update_idletasks()

        assert str(app.add_update_button.grid_info()["row"]) == "1"
        assert str(app.url_actions.grid_info()["row"]) == "4"
        assert str(app.username_combo.grid_info()["column"]) == "0"
        assert str(app.paste_username_button.grid_info()["column"]) == "1"
        assert str(app.clear_username_button.grid_info()["column"]) == "2"
        assert str(app.clear_username_button.cget("width")) == "3"
        assert str(app.clear_username_button.cget("text")) == "❌"
        url_buttons = list(app.url_actions.pack_slaves())
        assert url_buttons[0] is app.paste_add_button
        assert app.username_combo.bind("<Button-3>")
        assert app.urls_text.bind("<Button-3>")
    finally:
        root.destroy()
