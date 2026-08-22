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
        if self._text is not None:
            self._text.configure(state="normal")
            self._text.insert(tk.END, text)
            self._text.see(tk.END)
            self._text.configure(state="normal")

    def clear(self) -> None:
        self._buffer.clear()
        if self._text is not None:
            self._text.configure(state="normal")
            self._text.delete("1.0", tk.END)

    def toggle(self) -> None:
        if self._window is not None and self._window.winfo_exists():
            if self._window.state() == "iconic":
                self._window.deiconify()
            self._window.lift()
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
        menu = tk.Menu(window, tearoff=False)
        menu.add_command(label=t("log.copy"), command=lambda: self._copy(False))
        menu.add_command(label=t("log.copy_all"), command=lambda: self._copy(True))
        menu.add_separator()
        menu.add_command(label=t("log.clear"), command=self.clear)
        text.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        self._window = window
        self._text = text

    def _copy(self, entire: bool) -> None:
        if self._text is None:
            return
        try:
            selected = self._text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = ""
        payload = self._text.get("1.0", tk.END) if entire or not selected else selected
        self._master.clipboard_clear()
        self._master.clipboard_append(payload)


__all__ = ["LogWindow"]
