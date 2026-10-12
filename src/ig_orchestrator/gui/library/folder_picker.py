"""Modal picker for a destination catalog folder (category / group tree)."""

from __future__ import annotations

import tkinter as tk
from sqlite3 import Connection
from tkinter import messagebox, simpledialog, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.fsops_plan import validate_name


def folder_tree_rows(connection: Connection) -> list[tuple[int, int | None, str]]:
    rows = connection.execute(
        "SELECT id, parent_id, name FROM catalog_folders ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [(int(r["id"]), r["parent_id"], str(r["name"])) for r in rows]


def _fill_tree(tree: ttk.Treeview, connection: Connection) -> None:
    rows = folder_tree_rows(connection)
    known = {folder_id for folder_id, _p, _n in rows}
    pending = list(rows)
    inserted: set[int] = set()
    while pending:
        progressed = False
        for folder_id, parent_id, name in list(pending):
            if parent_id is None or parent_id not in known:
                tree.insert("", tk.END, iid=str(folder_id), text=name, open=True)
            elif parent_id in inserted:
                tree.insert(str(parent_id), tk.END, iid=str(folder_id), text=name)
            else:
                continue
            inserted.add(folder_id)
            pending.remove((folder_id, parent_id, name))
            progressed = True
        if not progressed:
            break


def _build_window(parent: tk.Misc, connection: Connection, title: str):
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    window.geometry("420x520")
    frame = ttk.Frame(window, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.rowconfigure(1, weight=1)
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text=t("picker.hint")).grid(row=0, column=0, sticky="w", pady=(0, 6))
    tree = ttk.Treeview(frame, show="tree", selectmode="browse")
    tree.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    _fill_tree(tree, connection)
    buttons = ttk.Frame(frame)
    buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
    return window, tree, buttons


def pick_folder(parent: tk.Misc, connection: Connection, title: str) -> int | None:
    """Return the chosen ``catalog_folders.id`` or ``None`` if cancelled."""

    window, tree, buttons = _build_window(parent, connection, title)
    result: dict[str, int | None] = {"id": None}

    def _ok() -> None:
        selection = tree.selection()
        if selection:
            result["id"] = int(selection[0])
            window.destroy()

    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text=t("picker.choose"), command=_ok).pack(side=tk.RIGHT)
    tree.bind("<Double-Button-1>", lambda _e: _ok())
    bind_escape_close(window, on_close=window.destroy)
    window.grab_set()
    window.wait_window()
    return result["id"]


def pick_destination(parent: tk.Misc, connection: Connection, title: str) -> str | None:
    """Choose an existing folder **or a new one** under it; returns its relative path.

    A new folder is only named here; it is created when the operation runs.
    """

    window, tree, buttons = _build_window(parent, connection, title)
    result: dict[str, str | None] = {"rel": None}

    def selected_rel() -> str | None:
        selection = tree.selection()
        if not selection:
            return None
        row = connection.execute(
            "SELECT rel_path FROM catalog_folders WHERE id = ?", (int(selection[0]),)
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else None

    def _ok() -> None:
        rel = selected_rel()
        if not rel:
            messagebox.showinfo(title, t("picker.not_root"), parent=window)
            return
        result["rel"] = rel
        window.destroy()

    def _new() -> None:
        base = selected_rel()
        if base is None:
            messagebox.showinfo(title, t("picker.select_parent"), parent=window)
            return
        name = simpledialog.askstring(t("fsops.new_folder"), t("fsops.new_folder_name"), parent=window)
        if not name:
            return
        name = name.strip()
        problem = validate_name(name)
        if problem:
            messagebox.showerror(title, problem, parent=window)
            return
        result["rel"] = f"{base}\\{name}" if base else name
        window.destroy()

    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text=t("picker.choose"), command=_ok).pack(side=tk.RIGHT)
    ttk.Button(buttons, text=t("picker.new_here"), command=_new).pack(side=tk.RIGHT, padx=(0, 6))
    tree.bind("<Double-Button-1>", lambda _e: _ok())
    bind_escape_close(window, on_close=window.destroy)
    window.grab_set()
    window.wait_window()
    return result["rel"]
