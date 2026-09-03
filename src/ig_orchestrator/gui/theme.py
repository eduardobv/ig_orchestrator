from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


SURFACE = "#F7F8FA"
PANEL = "#FFFFFF"
INK = "#1F2933"
ACCENT = "#2563EB"
BORDER = "#E2E5EA"
UI_FONT_FAMILY = "Segoe UI"
UI_FONT_SIZE = 10


def ui_font_option(family: str = UI_FONT_FAMILY, size: int = UI_FONT_SIZE) -> str:
    """Tk option-database font spec. Multi-word families must be braced.

    ``"Segoe UI 10"`` is parsed as family ``Segoe`` and size ``UI``, which
    raises ``TclError: expected integer but got "UI"`` when a Menu is created.
    """

    return f"{{{family}}} {int(size)}"


def _apply_ui_font(root: tk.Tk) -> None:
    spec = ui_font_option()
    try:
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(
                    family=UI_FONT_FAMILY, size=UI_FONT_SIZE
                )
            except tk.TclError:
                continue
        root.option_add("*Font", spec)
    except tk.TclError:
        pass


def apply_light_theme(root: tk.Tk) -> None:
    """Apply a light desktop theme. Prefer sv-ttk; fall back to ttk styling."""

    try:
        import sv_ttk

        sv_ttk.set_theme("light")
    except Exception:
        style = ttk.Style(root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("clam")
        style.configure(".", background=SURFACE, foreground=INK)
        style.configure("TFrame", background=SURFACE)
        style.configure("TLabel", background=SURFACE, foreground=INK)
        style.configure("TButton", padding=4)
        style.configure("TEntry", fieldbackground=PANEL)
        style.configure("TCombobox", fieldbackground=PANEL)
        style.configure("TLabelframe", background=SURFACE, foreground=INK)
        style.configure("TLabelframe.Label", background=SURFACE, foreground=INK)
        style.configure("TPanedwindow", background=SURFACE)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK)
        style.configure("TNotebook", background=SURFACE)
        style.configure("TNotebook.Tab", background=SURFACE)
    root.configure(bg=SURFACE)
    _apply_ui_font(root)
    style = ttk.Style(root)
    style.configure("Visible.Vertical.TScrollbar", width=14)
    style.configure("Compact.TButton", padding=0)


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event: object = None) -> None:
        if self._tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tip,
            text=self.text,
            background="#111827",
            foreground="white",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=3,
            font=("Segoe UI", 8),
        )
        label.pack()
        self._tip = tip

    def _hide(self, _event: object = None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def icon_button(
    parent: tk.Widget,
    *,
    image: tk.PhotoImage,
    command,
    tooltip: str,
) -> ttk.Button:
    button = ttk.Button(parent, image=image, command=command)
    Tooltip(button, tooltip)
    return button


def compact_icon_button(
    parent: tk.Widget,
    *,
    image: tk.PhotoImage,
    command,
    tooltip: str,
) -> ttk.Button:
    """Icon button sized like the catalog/batch ❌ clear controls."""

    button = ttk.Button(
        parent,
        image=image,
        command=command,
        style="Compact.TButton",
        width=3,
    )
    Tooltip(button, tooltip)
    return button


__all__ = [
    "SURFACE",
    "Tooltip",
    "apply_light_theme",
    "compact_icon_button",
    "icon_button",
    "ui_font_option",
]
