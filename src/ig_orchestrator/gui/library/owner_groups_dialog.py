"""Dialog: review accounts that share one Instagram id and resolve them."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.owner_groups import OwnerGroup, find_owner_groups, ignore_group


def hint_text(hint: str) -> str:
    return t(f"owners.hint.{hint}")


def pick_current(parent: tk.Misc, group: OwnerGroup) -> str | None:
    """Ask which member's username is the current one."""

    window = tk.Toplevel(parent)
    window.title(t("owners.pick_title"))
    window.transient(parent)
    window.geometry("420x320")
    result: dict[str, str | None] = {"name": None}
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text=t("owners.pick_hint"), wraplength=380, justify="left").pack(anchor="w")
    box = tk.Listbox(frame, exportselection=False)
    for member in group.members:
        box.insert(tk.END, f"{member.username}   [{member.rel_path or '-'}]")
        if member.username == group.suggested_current:
            box.selection_set(tk.END)
    box.pack(fill=tk.BOTH, expand=True, pady=8)

    def _ok() -> None:
        selection = box.curselection()
        if selection:
            result["name"] = group.members[selection[0]].username
            window.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X)
    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text=t("picker.choose"), command=_ok).pack(side=tk.RIGHT)
    bind_escape_close(window, on_close=window.destroy)
    window.grab_set()
    window.wait_window()
    return result["name"]


def open_owner_groups(app) -> None:
    existing = getattr(app, "_owner_groups_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                return
        except tk.TclError:
            app._owner_groups_window = None
    window = tk.Toplevel(app.root)
    window.title(t("owners.title"))
    window.geometry("960x560")
    app._owner_groups_window = window
    frame = ttk.Frame(window, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.rowconfigure(1, weight=1)
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text=t("owners.hint"), wraplength=900, justify="left").grid(row=0, column=0, sticky="w", pady=(0, 6))
    columns = ("hint", "folder", "last", "content")
    tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="browse")
    tree.heading("#0", text=t("owners.col.group"))
    tree.column("#0", width=300)
    for column, width in zip(columns, (170, 330, 130, 70), strict=True):
        tree.heading(column, text=t(f"owners.col.{column}"))
        tree.column(column, width=width, anchor="w")
    tree.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status).grid(row=2, column=0, sticky="w", pady=(6, 0))
    groups: dict[str, OwnerGroup] = {}

    def load() -> None:
        tree.delete(*tree.get_children())
        groups.clear()
        found = find_owner_groups(app.connection)
        for group in found:
            groups[group.owner_id] = group
            names = ", ".join(m.username for m in group.members)
            tree.insert("", tk.END, iid=f"g:{group.owner_id}", text=f"{group.owner_id}  ·  {names}",
                        values=(hint_text(group.hint), "", "", ""), open=False)
            for member in group.members:
                tree.insert(f"g:{group.owner_id}", tk.END, text=member.username,
                            values=("★ " + t("owners.suggested") if member.username == group.suggested_current else "",
                                    member.rel_path or "-", member.last_media_at or "-", member.content))
        status.set(t("owners.count", count=len(found)))

    def selected_group() -> OwnerGroup | None:
        selection = tree.selection()
        if not selection:
            return None
        iid = selection[0]
        if not iid.startswith("g:"):
            iid = tree.parent(iid)
        return groups.get(iid[2:])

    def resolve() -> None:
        group = selected_group()
        if group is None:
            return
        current = pick_current(window, group)
        if current:
            app._resolve_owner_group(group, current)
            load()

    def not_rename() -> None:
        group = selected_group()
        if group is None:
            return
        if messagebox.askyesno(t("owners.title"), t("owners.confirm_ignore", owner=group.owner_id), parent=window):
            ignore_group(app.connection, group.owner_id, "no es renombrado")
            load()

    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(buttons, text=t("owners.resolve"), command=resolve).pack(side=tk.LEFT)
    ttk.Button(buttons, text=t("owners.ignore"), command=not_rename).pack(side=tk.LEFT, padx=8)
    ttk.Button(buttons, text=t("owners.refresh"), command=load).pack(side=tk.LEFT)
    ttk.Button(buttons, text=t("audit.close"), command=window.destroy).pack(side=tk.RIGHT)
    window.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, "_owner_groups_window", None), window.destroy()))
    bind_escape_close(window, on_close=window.destroy)
    load()
