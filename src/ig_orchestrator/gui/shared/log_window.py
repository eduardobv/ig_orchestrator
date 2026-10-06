from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ig_orchestrator.gui.shared.helpers import center_modal_on_parent, classify_log_level, bind_escape_close
from ig_orchestrator.gui.shared.i18n import t
from ig_orchestrator.gui.theme import compact_icon_button


class LogWindow:
    """Non-modal run log with copy/clear/filter by level. Hidden until opened."""

    def __init__(self, master: tk.Tk, icons=None) -> None:
        self._master = master
        self._window: tk.Toplevel | None = None
        self._text: tk.Text | None = None
        self._buffer: list[str] = []
        self._filter: str | None = None  # None = all, "warning", "error"
        self._icons = icons

    def append(self, text: str) -> None:
        self._buffer.append(text)
        widget = self._live_text()
        if widget is None:
            return
        self._render_buffer_to_widget(widget)

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

        # Text widget with scrollbar
        text = tk.Text(frame, wrap="word", undo=False)
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scroll.set)

        # Configure text tags for colors
        text.tag_configure("warning", foreground="#b58900")  # Dark yellow
        text.tag_configure("error", foreground="red")
        text.tag_configure("normal", foreground="black")

        # Insert buffered content
        self._render_buffer_to_widget(text)
        text.configure(state="disabled")

        # Right-click context menu
        menu = tk.Menu(window, tearoff=False)
        menu.add_command(label=t("log.copy"), command=lambda: self._copy(False))
        menu.add_command(label=t("log.copy_all"), command=lambda: self._copy(True))
        menu.add_separator()
        menu.add_command(label=t("log.clear"), command=self.clear)
        text.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))

        # Bottom button bar
        button_frame = ttk.Frame(window)
        button_frame.pack(fill=tk.X, padx=6, pady=(6, 0))

        clear_btn = ttk.Button(
            button_frame,
            text=t("log.clear"),
            command=self.clear,
        )
        clear_btn.pack(side=tk.LEFT, padx=(0, 4))

        warning_btn = ttk.Button(
            button_frame,
            text=t("log.warning"),
            command=self._filter_warning,
        )
        warning_btn.pack(side=tk.LEFT, padx=(0, 4))

        error_btn = ttk.Button(
            button_frame,
            text=t("log.error"),
            command=self._filter_error,
        )
        error_btn.pack(side=tk.LEFT, padx=(0, 4))

        close_btn = ttk.Button(
            button_frame,
            text=t("log.close"),
            command=self._hide,
        )
        close_btn.pack(side=tk.LEFT)

        window.protocol("WM_DELETE_WINDOW", self._hide)
        bind_escape_close(window, on_close=self._hide)
        center_modal_on_parent(window, self._master, self._master.state() == "zoomed")
        self._window = window
        self._text = text

    def _render_buffer_to_widget(self, widget: tk.Text) -> None:
        """Re-render buffer to widget, applying filter and tags."""
        try:
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            for line in self._buffer:
                if self._filter is None:
                    # Show all
                    level = classify_log_level(line)
                    widget.insert(tk.END, line, level)
                elif self._filter == "warning" and classify_log_level(line) == "warning":
                    widget.insert(tk.END, line, "warning")
                elif self._filter == "error" and classify_log_level(line) == "error":
                    widget.insert(tk.END, line, "error")
                elif self._filter is None:
                    level = classify_log_level(line)
                    widget.insert(tk.END, line, level)
            widget.see(tk.END)
            widget.configure(state="disabled")
        except tk.TclError:
            self._forget_window()

    def _filter_warning(self) -> None:
        """Toggle warning filter."""
        self._filter = None if self._filter == "warning" else "warning"
        widget = self._live_text()
        if widget is not None:
            self._render_buffer_to_widget(widget)

    def _filter_error(self) -> None:
        """Toggle error filter."""
        self._filter = None if self._filter == "error" else "error"
        widget = self._live_text()
        if widget is not None:
            self._render_buffer_to_widget(widget)

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
        self._filter = None

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
