from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk


def bind_treeview_sort(
    tree: ttk.Treeview,
    columns: tuple[str, ...],
    *,
    title_for: Callable[[str], str] | None = None,
) -> None:
    """Sort visible rows A↔Z by a column. Does not change underlying data."""

    state = {"column": None, "ascending": True}

    def heading_title(column: str) -> str:
        base = title_for(column) if title_for is not None else column
        if state["column"] != column:
            return base
        return f"{base} {'▲' if state['ascending'] else '▼'}"

    def sort_by(column: str) -> None:
        items = [(tree.set(iid, column), iid) for iid in tree.get_children("")]
        reverse = state["column"] == column and state["ascending"]
        items.sort(key=lambda pair: _sort_key(pair[0]), reverse=reverse)
        for index, (_value, iid) in enumerate(items):
            tree.move(iid, "", index)
        state["column"] = column
        state["ascending"] = not reverse
        for name in columns:
            tree.heading(name, text=heading_title(name), command=lambda c=name: sort_by(c))

    for column in columns:
        tree.heading(column, command=lambda c=column: sort_by(c))


def _sort_key(value: str) -> tuple[int, object]:
    text = str(value).strip()
    if text.isdigit():
        return (0, int(text))
    return (1, text.casefold())


__all__ = ["bind_treeview_sort"]
