"""Dialog: history of disk operations with Undo."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError


def open_history(app) -> None:
    """Open the operations history; ``app`` provides connection, root and refresh hooks."""

    existing = getattr(app, "_fsops_history_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                return
        except tk.TclError:
            app._fsops_history_window = None

    window = tk.Toplevel(app.root)
    window.title(t("ops.title"))
    window.geometry("900x440")
    app._fsops_history_window = window
    service = FsOperationService(app.connection)

    frame = ttk.Frame(window, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    columns = ("when", "type", "steps", "from", "to", "status")
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
    for column, width in zip(columns, (150, 130, 50, 260, 260, 90), strict=True):
        tree.heading(column, text=t(f"ops.col.{column}"))
        tree.column(column, width=width, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status, wraplength=840).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def load() -> None:
        tree.delete(*tree.get_children())
        for row in service.history():
            label = row["op_types"] + (" (deshacer)" if row["is_undo"] else "")
            tree.insert(
                "",
                tk.END,
                iid=str(row["op_group"]),
                values=(
                    str(row["created_at"])[:19].replace("T", " "),
                    label,
                    row["steps"],
                    row["src_rel"] or "-",
                    row["dst_rel"] or "-",
                    row["status"],
                ),
            )

    def undo() -> None:
        selection = tree.selection()
        if not selection:
            return
        group = selection[0]
        ok, reason = service.can_undo(group)
        if not ok:
            messagebox.showinfo(t("ops.title"), reason, parent=window)
            return
        if not messagebox.askyesno(t("ops.title"), t("ops.confirm_undo"), parent=window):
            return
        try:
            service.undo(group)
            AccountLifecycleService(app.connection).restore_after_undo(group)
        except FsOpsError as exc:
            messagebox.showerror(t("ops.title"), str(exc), parent=window)
            return
        status.set(t("ops.undone"))
        load()
        app._after_fsops_change()

    buttons = ttk.Frame(frame)
    buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(buttons, text=t("ops.undo"), command=undo).pack(side=tk.LEFT)
    ttk.Button(buttons, text=t("audit.close"), command=window.destroy).pack(side=tk.RIGHT)
    window.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, "_fsops_history_window", None), window.destroy()))
    bind_escape_close(window, on_close=window.destroy)
    load()
