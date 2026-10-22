"""Destination-path field with live suggestions (type ``models-d`` and pick from the matches)."""

from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk

_NUMERIC_PREFIX = re.compile(r"^\d+\.")
MAX_SUGGESTIONS = 200


def _segments(path: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", path) if part]


def _name(segment: str) -> str:
    """Folder name without the ``00.`` ordering prefix, case-folded."""

    return _NUMERIC_PREFIX.sub("", segment).casefold()


def rank_destination_paths(
    paths: Sequence[str],
    query: str,
    containers: Sequence[str] = (),
) -> list[str]:
    """Suggestions for *query* among the catalog *paths*.

    Empty query: the *containers* first (``00.MODELS-A``, ``00.MODELS-B``...), then every
    other path alphabetically, which keeps each account folder under its container.

    With a query (matched against folder names, ignoring the ``00.`` prefix and case):
    the folder that is the query itself, then folders whose name starts with it, then
    everything inside a folder that matches, then any other path containing it. Each
    group is alphabetical.
    """

    unique: dict[str, str] = {}
    for path in [*containers, *paths]:
        text = str(path).strip()
        if text:
            unique.setdefault(text.casefold(), text)
    ordered = sorted(unique.values(), key=str.casefold)
    needle = query.strip().casefold().rstrip("\\/")
    if not needle:
        container_keys = {str(c).strip().casefold() for c in containers}
        head = [p for p in ordered if p.casefold() in container_keys]
        tail = [p for p in ordered if p.casefold() not in container_keys]
        return head + tail
    needle_name = _name(needle)
    ranked: list[tuple[int, str]] = []
    for path in ordered:
        names = [_name(part) for part in _segments(path)]
        last = names[-1] if names else ""
        if path.casefold() == needle or last == needle_name:
            tier = 0
        elif last.startswith(needle_name):
            tier = 1
        elif any(name.startswith(needle_name) for name in names[:-1]):
            tier = 2
        elif needle in path.casefold():
            tier = 3
        else:
            continue
        ranked.append((tier, path))
    ranked.sort(key=lambda item: item[0])  # stable: alphabetical inside each tier
    return [path for _tier, path in ranked]


class PathSuggestEntry(ttk.Frame):
    """Entry plus a drop-down list that filters while typing.

    ``Down``/``Up`` move through the list, ``Enter``/click choose, ``Esc`` closes.
    The ▾ button lists the default order (containers first).
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        values: Sequence[str] = (),
        containers: Sequence[str] = (),
        width: int = 56,
    ) -> None:
        super().__init__(parent)
        self.variable = textvariable
        self._paths = list(values)
        self._containers = list(containers)
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(self, textvariable=textvariable, width=width)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.button = ttk.Button(self, text="▾", width=3, command=self._toggle_all)
        self.button.grid(row=0, column=1, padx=(2, 0))
        self.entry.bind("<KeyRelease>", self._on_key, add="+")
        self.entry.bind("<Down>", self._on_down, add="+")
        self.entry.bind("<Up>", self._on_up, add="+")
        self.entry.bind("<Return>", self._on_return, add="+")
        self.entry.bind("<Escape>", lambda _e: self._close(), add="+")
        self.entry.bind("<FocusOut>", lambda _e: self.after(200, self._close_if_unfocused), add="+")

    # ------------------------------------------------------------ data
    def set_values(self, values: Sequence[str], containers: Sequence[str] | None = None) -> None:
        self._paths = list(values)
        if containers is not None:
            self._containers = list(containers)

    def suggestions(self, query: str | None = None) -> list[str]:
        text = self.variable.get() if query is None else query
        return rank_destination_paths(self._paths, text, self._containers)

    # ----------------------------------------------------------- popup
    def _toggle_all(self) -> None:
        if self._popup is not None:
            self._close()
            return
        self.entry.focus_set()
        self._open(self.suggestions(""))

    def _open(self, items: list[str]) -> None:
        items = items[:MAX_SUGGESTIONS]
        if not items:
            self._close()
            return
        if self._popup is None:
            popup = tk.Toplevel(self)
            popup.wm_overrideredirect(True)
            popup.attributes("-topmost", True)
            frame = ttk.Frame(popup, borderwidth=1, relief="solid")
            frame.pack(fill=tk.BOTH, expand=True)
            listbox = tk.Listbox(frame, height=10, exportselection=False, activestyle="none")
            scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
            listbox.configure(yscrollcommand=scroll.set)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            listbox.bind("<ButtonRelease-1>", self._on_click)
            self._popup, self._listbox = popup, listbox
        listbox = self._listbox
        assert listbox is not None and self._popup is not None
        listbox.delete(0, tk.END)
        listbox.insert(tk.END, *items)
        listbox.configure(height=min(10, len(items)))
        self.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        self._popup.geometry(f"{max(self.winfo_width(), 320)}x{listbox.winfo_reqheight() + 4}+{x}+{y}")

    def _close(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
        self._popup = self._listbox = None

    def _close_if_unfocused(self) -> None:
        try:
            if self._popup is not None and self.focus_get() not in (self.entry, self._listbox):
                self._close()
        except (tk.TclError, KeyError):
            self._close()

    # ---------------------------------------------------------- events
    def _on_key(self, event: tk.Event) -> None:
        if event.keysym in {"Down", "Up", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"}:
            return
        text = self.variable.get().strip()
        self._open(self.suggestions(text) if text else [])

    def _on_down(self, _event: tk.Event) -> str:
        if self._popup is None:
            self._open(self.suggestions())
        self._move(1)
        return "break"

    def _on_up(self, _event: tk.Event) -> str:
        self._move(-1)
        return "break"

    def _move(self, step: int) -> None:
        listbox = self._listbox
        if listbox is None or listbox.size() == 0:
            return
        current = listbox.curselection()
        index = (current[0] + step) if current else (0 if step > 0 else listbox.size() - 1)
        index = max(0, min(listbox.size() - 1, index))
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(index)
        listbox.see(index)

    def _on_return(self, _event: tk.Event) -> str | None:
        if self._listbox is not None and self._listbox.curselection():
            self._choose(self._listbox.get(self._listbox.curselection()[0]))
            return "break"
        self._close()
        return None

    def _on_click(self, _event: tk.Event) -> None:
        if self._listbox is not None and self._listbox.curselection():
            self._choose(self._listbox.get(self._listbox.curselection()[0]))

    def _choose(self, path: str) -> None:
        self.variable.set(path)
        self._close()
        self.entry.focus_set()
        self.entry.icursor(tk.END)


__all__ = ["PathSuggestEntry", "rank_destination_paths"]
