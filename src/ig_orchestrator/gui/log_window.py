from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ig_orchestrator.gui.i18n import t


class LogWindow:
    """Non-modal run log with copy/clear. Hidden until opened."""

    def __init__(self, master: tk.Tk) -> None:
        self._master = master
        self._window: tk.Toplevel | None = None
        self._text: tk.Text | None = None
        self._buffer: list[str] = []

    def append(self, text: str) -> None:
        self._buffer.append(text)
        widget = self._live_text()
        if widget is None:
            return
        try:
            widget.configure(state="normal")
            widget.insert(tk.END, text)
            widget.see(tk.END)
            widget.configure(state="disabled")
        except tk.TclError:
            self._forget_window()

    def clear(self) -> None:
        self._buffer.clear()
        widget = self._live_text()
        if widget is None:
            return
        try:
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            widget.configure(state="disabled")
        except tk.TclError:
            self._forget_window()

    def toggle(self) -> None:
        window = self._live_window()
        if window is not None:
            window.deiconify()
            window.lift()
            return
        self._open()

    def _open(self) -> None:
        window = tk.Toplevel(self._master)
        window.title(t("log.title"))
        window.geometry("720x420")
        window.minsize(420, 240)
        frame = ttk.Frame(window, padding=6)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Text(frame, wrap="word", undo=False)
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", "".join(self._buffer))
        text.configure(state="disabled")
        menu = tk.Menu(window, tearoff=False)
        menu.add_command(label=t("log.copy"), command=lambda: self._copy(False))
        menu.add_command(label=t("log.copy_all"), command=lambda: self._copy(True))
        menu.add_separator()
        menu.add_command(label=t("log.clear"), command=self.clear)
        text.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))
        window.protocol("WM_DELETE_WINDOW", self._hide)
        self._window = window
        self._text = text

    def _hide(self) -> None:
        window = self._live_window()
        if window is None:
            return
        window.withdraw()

    def _live_window(self) -> tk.Toplevel | None:
        window = self._window
        if window is None:
            return None
        try:
            if window.winfo_exists():
                return window
        except tk.TclError:
            pass
        self._forget_window()
        return None

    def _live_text(self) -> tk.Text | None:
        if self._live_window() is None:
            return None
        return self._text

    def _forget_window(self) -> None:
        self._window = None
        self._text = None

    def _copy(self, entire: bool) -> None:
        widget = self._live_text()
        if widget is None:
            return
        try:
            selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = ""
        try:
            payload = widget.get("1.0", tk.END) if entire or not selected else selected
            self._master.clipboard_clear()
            self._master.clipboard_append(payload)
        except tk.TclError:
            self._forget_window()


__all__ = ["LogWindow"]
