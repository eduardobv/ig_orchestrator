"""Clipboard helpers and a consistent right-click edit menu for Tk fields."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from ig_orchestrator.gui.i18n import t


def read_clipboard(widget: tk.Misc) -> str | None:
    try:
        value = widget.clipboard_get()
    except tk.TclError:
        return None
    if value is None:
        return None
    return str(value)


def first_clipboard_line(raw: str) -> str:
    """Return the first non-empty stripped line (usernames must stay single-line)."""

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return raw.strip()


def _is_text_widget(widget: tk.Misc) -> bool:
    return isinstance(widget, tk.Text)


def _is_readonly(widget: tk.Misc) -> bool:
    try:
        state = str(widget.cget("state"))
    except (tk.TclError, AttributeError):
        return False
    return state in {"disabled", "readonly"}


def selection_range(widget: tk.Misc) -> tuple[object, object] | None:
    try:
        return (widget.index("sel.first"), widget.index("sel.last"))
    except tk.TclError:
        return None


def _get_range(widget: tk.Misc, start: object, end: object) -> str:
    getter = widget.get
    try:
        return str(getter(start, end))
    except TypeError:
        text = str(getter())
        start_i = int(widget.index(start))
        end_spec = str(end)
        if end_spec in {tk.END, "end"}:
            return text[start_i:]
        return text[start_i : int(widget.index(end))]


def selected_text(widget: tk.Misc) -> str | None:
    rng = selection_range(widget)
    if rng is None:
        return None
    return _get_range(widget, rng[0], rng[1])


def copy_selection(widget: tk.Misc) -> bool:
    text = selected_text(widget)
    if not text:
        return False
    widget.clipboard_clear()
    widget.clipboard_append(text)
    return True


def delete_selection(widget: tk.Misc) -> bool:
    if _is_readonly(widget):
        return False
    rng = selection_range(widget)
    if rng is None:
        return False
    widget.delete(rng[0], rng[1])
    return True


def cut_selection(widget: tk.Misc) -> bool:
    if not copy_selection(widget):
        return False
    return delete_selection(widget)


def paste_at_insert(widget: tk.Misc, text: str) -> bool:
    if _is_readonly(widget):
        return False
    delete_selection(widget)
    widget.insert(tk.INSERT, text)
    return True


def select_all(widget: tk.Misc) -> None:
    if _is_text_widget(widget):
        widget.tag_add(tk.SEL, "1.0", "end-1c")
        widget.mark_set(tk.INSERT, "end-1c")
        widget.see(tk.INSERT)
        return
    widget.selection_range(0, tk.END)
    try:
        widget.icursor(tk.END)
    except (tk.TclError, AttributeError):
        pass


def bind_edit_context_menu(
    widget: tk.Widget,
    *,
    after_change: Callable[[], None] | None = None,
) -> tk.Menu:
    """Attach Cut/Copy/Paste/Delete/Select all. ``break`` avoids a native duplicate."""

    menu = tk.Menu(widget, tearoff=False)
    cut_label = t("edit.cut")
    copy_label = t("edit.copy")
    paste_label = t("edit.paste")
    delete_label = t("edit.delete")
    select_all_label = t("edit.select_all")

    def _changed() -> None:
        if after_change is not None:
            after_change()

    def _cut() -> None:
        if cut_selection(widget):
            _changed()

    def _copy() -> None:
        copy_selection(widget)

    def _paste() -> None:
        text = read_clipboard(widget)
        if text is None:
            return
        if paste_at_insert(widget, text):
            _changed()

    def _delete() -> None:
        if delete_selection(widget):
            _changed()

    def _select_all() -> None:
        select_all(widget)

    menu.add_command(label=cut_label, command=_cut)
    menu.add_command(label=copy_label, command=_copy)
    menu.add_command(label=paste_label, command=_paste)
    menu.add_command(label=delete_label, command=_delete)
    menu.add_separator()
    menu.add_command(label=select_all_label, command=_select_all)

    def _popup(event: tk.Event) -> str:
        widget.focus_set()
        readonly = _is_readonly(widget)
        has_sel = bool(selected_text(widget))
        has_clip = read_clipboard(widget) is not None
        menu.entryconfigure(cut_label, state="normal" if has_sel and not readonly else "disabled")
        menu.entryconfigure(copy_label, state="normal" if has_sel else "disabled")
        menu.entryconfigure(
            paste_label, state="normal" if has_clip and not readonly else "disabled"
        )
        menu.entryconfigure(
            delete_label, state="normal" if has_sel and not readonly else "disabled"
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    for sequence in ("<Button-3>", "<Shift-F10>"):
        widget.bind(sequence, _popup)
    return menu


__all__ = [
    "bind_edit_context_menu",
    "copy_selection",
    "cut_selection",
    "delete_selection",
    "first_clipboard_line",
    "paste_at_insert",
    "read_clipboard",
    "select_all",
    "selected_text",
    "selection_range",
]
