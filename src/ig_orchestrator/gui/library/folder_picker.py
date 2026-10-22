"""Modal picker for a destination catalog folder (category / group tree)."""

from __future__ import annotations

import tkinter as tk
from sqlite3 import Connection
from tkinter import messagebox, simpledialog, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.folder_suggestions import Suggestion, find_folder_matches, suggest_destinations
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError
from ig_orchestrator.library.fsops_plan import validate_name
from ig_orchestrator.library.paths import parent_rel


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


def _open_to(tree: ttk.Treeview, iid: str) -> None:
    """Expand the ancestors of ``iid``, select it and scroll to it."""

    parent = tree.parent(iid)
    while parent:
        tree.item(parent, open=True)
        parent = tree.parent(parent)
    tree.selection_set(iid)
    tree.focus(iid)
    tree.see(iid)


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


def pick_folder(
    parent: tk.Misc,
    connection: Connection,
    title: str,
    *,
    account_ids: list[int] | None = None,
) -> int | None:
    """Return the chosen ``catalog_folders.id`` or ``None`` if cancelled.

    Besides the tree it offers: up to three **suggested** folders (the inverse of where the accounts are
    now: ``X`` -> ``X-Deleted`` / ``X-Inactive`` and back), a **search box** that finds folders by name in
    the tree, and **New folder here** (created right away; it can be undone from the disk operations history).
    """

    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    window.geometry("520x640")
    frame = ttk.Frame(window, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(4, weight=1)
    result: dict[str, int | None] = {"id": None}
    service = FsOperationService(connection)

    ttk.Label(frame, text=t("picker.hint"), font=("Segoe UI", 10, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    suggestion_box = ttk.LabelFrame(frame, text=t("picker.suggested"), padding=6)
    suggestion_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 6))
    search_var = tk.StringVar()
    status = tk.StringVar()
    search_row = ttk.Frame(frame)
    search_row.grid(row=2, column=0, columnspan=2, sticky="ew")
    search_row.columnconfigure(1, weight=1)
    ttk.Label(search_row, text=t("picker.search")).grid(row=0, column=0, padx=(0, 6))
    search = ttk.Entry(search_row, textvariable=search_var)
    search.grid(row=0, column=1, sticky="ew")
    ttk.Label(frame, textvariable=status, foreground="#666666").grid(
        row=3, column=0, columnspan=2, sticky="w", pady=(2, 4)
    )
    tree = ttk.Treeview(frame, show="tree", selectmode="browse")
    tree.grid(row=4, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=4, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
    matches: list[int] = []
    state = {"index": 0}

    def reload_tree(select_id: int | None = None) -> None:
        tree.delete(*tree.get_children())
        _fill_tree(tree, connection)
        if select_id is not None and tree.exists(str(select_id)):
            _open_to(tree, str(select_id))

    def choose(folder_id: int) -> None:
        result["id"] = folder_id
        window.destroy()

    def create_folder(parent_id: int, name: str) -> int | None:
        plan = service.plan_mkdir(parent_id, name)
        if not plan.can_execute:
            messagebox.showerror(
                title, "; ".join(c.message for c in plan.blocking) or t("picker.cannot_create"), parent=window
            )
            return None
        try:
            service.execute(plan)
        except FsOpsError as exc:
            messagebox.showerror(title, str(exc), parent=window)
            return None
        return service.folder_id_for_rel(plan.steps[0].dst_rel)

    def use_suggestion(suggestion: Suggestion) -> None:
        if suggestion.folder_id is not None:
            choose(suggestion.folder_id)
            return
        where = parent_rel(suggestion.rel)
        parent_id = service.folder_id_for_rel(where) if where else None
        if parent_id is None:
            return
        if not messagebox.askyesno(
            title, t("picker.create_suggested", name=suggestion.label, parent=where), parent=window
        ):
            return
        created = create_folder(parent_id, suggestion.label)
        if created is not None:
            choose(created)

    suggestions = suggest_destinations(connection, account_ids or []) if account_ids else []
    if suggestions:
        for suggestion in suggestions:
            text = (
                suggestion.label
                if suggestion.folder_id is not None
                else t("picker.suggested_create", name=suggestion.label)
            )
            ttk.Button(suggestion_box, text=text, command=lambda s=suggestion: use_suggestion(s)).pack(
                fill=tk.X, pady=1
            )
            ttk.Label(
                suggestion_box,
                text="  " + t(f"picker.reason.{suggestion.reason}") + " - " + suggestion.rel,
                foreground="#666666",
            ).pack(anchor="w")
    else:
        ttk.Label(suggestion_box, text=t("picker.no_suggestions"), foreground="#666666").pack(anchor="w")

    def go_to(index: int) -> None:
        if not matches:
            return
        state["index"] = index % len(matches)
        iid = str(matches[state["index"]])
        if tree.exists(iid):
            _open_to(tree, iid)
        status.set(t("picker.matches", current=state["index"] + 1, total=len(matches)))

    all_folders = [
        (int(r["id"]), str(r["name"]), str(r["rel_path"] or ""))
        for r in connection.execute("SELECT id, name, rel_path FROM catalog_folders")
    ]

    def on_search(*_args) -> None:
        matches[:] = find_folder_matches(all_folders, search_var.get())
        if not search_var.get().strip():
            status.set("")
        elif not matches:
            status.set(t("picker.no_matches"))
        else:
            go_to(0)

    def next_match(_event=None) -> str:
        if len(matches) > 1:
            go_to(state["index"] + 1)
        return "break"

    def previous_match(_event=None) -> str:
        if len(matches) > 1:
            go_to(state["index"] - 1)
        return "break"

    search_var.trace_add("write", on_search)
    search.bind("<Return>", next_match)
    search.bind("<Down>", next_match)
    search.bind("<Up>", previous_match)

    def ok() -> None:
        selection = tree.selection()
        if selection:
            choose(int(selection[0]))

    def new_folder() -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(title, t("picker.select_parent"), parent=window)
            return
        name = simpledialog.askstring(t("fsops.new_folder"), t("fsops.new_folder_name"), parent=window)
        if not name:
            return
        problem = validate_name(name.strip())
        if problem:
            messagebox.showerror(title, problem, parent=window)
            return
        created = create_folder(int(selection[0]), name.strip())
        if created is not None:
            reload_tree(created)

    reload_tree()
    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text=t("picker.choose"), command=ok).pack(side=tk.RIGHT)
    ttk.Button(buttons, text=t("picker.new_here"), command=new_folder).pack(side=tk.RIGHT, padx=(0, 6))
    tree.bind("<Double-Button-1>", lambda _e: ok())
    bind_escape_close(window, on_close=window.destroy)
    search.focus_set()
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
