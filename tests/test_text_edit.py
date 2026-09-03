from __future__ import annotations

from pathlib import Path

import pytest

import tkinter as tk

from ig_orchestrator.gui.i18n import load_language, t
from ig_orchestrator.gui.text_edit import (
    bind_edit_context_menu,
    copy_selection,
    cut_selection,
    delete_selection,
    first_clipboard_line,
    paste_at_insert,
    read_clipboard,
    select_all,
    selected_text,
)


class FakeEntry:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.sel: tuple[int, int] | None = None
        self.insert_at = len(value)
        self._clipboard = ""
        self.state = "normal"
        self.focused = False

    def cget(self, key: str) -> str:
        if key == "state":
            return self.state
        raise tk.TclError(key)

    def get(self, start: object = None, end: object = None) -> str:
        if start is None and end is None:
            return self.value
        raise TypeError("get() takes 1 positional argument")

    def index(self, spec: object) -> int:
        token = str(spec)
        if token in {tk.INSERT, "insert"}:
            return self.insert_at
        if token in {tk.END, "end"}:
            return len(self.value)
        if token in {tk.SEL_FIRST, "sel.first"}:
            if self.sel is None:
                raise tk.TclError("no selection")
            return self.sel[0]
        if token in {tk.SEL_LAST, "sel.last"}:
            if self.sel is None:
                raise tk.TclError("no selection")
            return self.sel[1]
        return int(token)

    def delete(self, start: object, end: object | None = None) -> None:
        i0 = self.index(start)
        i1 = self.index(end) if end is not None else i0 + 1
        self.value = self.value[:i0] + self.value[i1:]
        self.sel = None
        self.insert_at = i0

    def insert(self, index: object, text: str) -> None:
        i0 = self.index(index)
        self.value = self.value[:i0] + text + self.value[i0:]
        self.insert_at = i0 + len(text)

    def selection_range(self, start: object, end: object) -> None:
        self.sel = (self.index(start), self.index(end))

    def icursor(self, index: object) -> None:
        self.insert_at = self.index(index)

    def focus_set(self) -> None:
        self.focused = True

    def clipboard_clear(self) -> None:
        self._clipboard = ""

    def clipboard_append(self, text: str) -> None:
        self._clipboard += text

    def clipboard_get(self) -> str:
        if not self._clipboard:
            raise tk.TclError("CLIPBOARD")
        return self._clipboard


def test_first_clipboard_line_uses_first_non_empty_stripped_line() -> None:
    assert first_clipboard_line("  amberlure_\nextra") == "amberlure_"
    assert first_clipboard_line("\n\t user \n") == "user"
    assert first_clipboard_line("   ") == ""


def test_cut_copy_paste_delete_and_select_all_on_entry() -> None:
    widget = FakeEntry("abcdef")
    widget.sel = (1, 4)
    widget.insert_at = 4

    assert selected_text(widget) == "bcd"
    assert copy_selection(widget) is True
    assert widget._clipboard == "bcd"

    assert delete_selection(widget) is True
    assert widget.value == "aef"

    widget.sel = (0, 1)
    assert cut_selection(widget) is True
    assert widget.value == "ef"
    assert widget._clipboard == "a"

    widget.insert_at = 1
    assert paste_at_insert(widget, "XY") is True
    assert widget.value == "eXYf"

    select_all(widget)
    assert widget.sel == (0, 4)
    assert selected_text(widget) == "eXYf"


def test_paste_replaces_selection() -> None:
    widget = FakeEntry("hello")
    widget.sel = (0, 5)
    assert paste_at_insert(widget, "world") is True
    assert widget.value == "world"


def test_readonly_entry_rejects_mutations() -> None:
    widget = FakeEntry("keep")
    widget.state = "disabled"
    widget.sel = (0, 4)
    assert delete_selection(widget) is False
    assert paste_at_insert(widget, "x") is False
    assert widget.value == "keep"
    assert copy_selection(widget) is True


def test_read_clipboard_returns_none_when_empty() -> None:
    widget = FakeEntry()
    assert read_clipboard(widget) is None
    widget._clipboard = "ok"
    assert read_clipboard(widget) == "ok"


def test_clipboard_black_icon_asset_exists() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ig_orchestrator"
        / "gui"
        / "static"
        / "icons"
        / "clipboard_black.png"
    )
    assert path.is_file()


def test_edit_locale_keys_exist() -> None:
    load_language("es")
    assert t("edit.cut") == "Cortar"
    assert t("tooltip.paste_username") == "Pegar username"
    load_language("en")
    assert t("edit.paste") == "Paste"
    assert t("tooltip.clear_username") == "Clear username"
    load_language("es")


def test_context_menu_paste_into_real_entry() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    try:
        from tkinter import ttk

        from ig_orchestrator.gui.theme import apply_light_theme

        apply_light_theme(root)
        entry = ttk.Entry(root)
        entry.insert(0, "abc")
        entry.selection_range(0, 3)
        bind_edit_context_menu(entry)
        root.clipboard_clear()
        root.clipboard_append("XYZ")
        assert paste_at_insert(entry, "XYZ") is True
        assert entry.get() == "XYZ"

        text = tk.Text(root, height=3, undo=True)
        text.insert("1.0", "one\n")
        text.tag_add(tk.SEL, "1.0", "1.3")
        bind_edit_context_menu(text)
        assert selected_text(text) == "one"
        assert cut_selection(text) is True
        assert text.get("1.0", "end-1c") == "\n"
    finally:
        root.destroy()
