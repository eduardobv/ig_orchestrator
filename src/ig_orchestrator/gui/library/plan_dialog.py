"""Reusable preview dialog for a disk-operation plan (``Ejecutar`` / ``Cancelar``)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.fsops_plan import Plan

STEP_LABELS = {
    "MKDIR": "Crear",
    "MOVE_DIR": "Mover",
    "RENAME_DIR": "Renombrar",
    "RMDIR": "Eliminar vacia",
}


def plan_rows(plan: Plan) -> list[tuple[str, str, str]]:
    return [
        (STEP_LABELS.get(step.op_type.value, step.op_type.value), step.src_rel or "-", step.dst_rel or "-")
        for step in plan.steps
    ]


def confirm_plan(parent: tk.Misc, plan: Plan) -> bool:
    """Show the plan modally; returns True only if the user confirms a runnable plan."""

    window = tk.Toplevel(parent)
    window.title(t("plan.title"))
    window.transient(parent)
    window.geometry("760x380")
    window.minsize(560, 300)
    result = {"ok": False}

    frame = ttk.Frame(window, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)

    ttk.Label(frame, text=plan.title, font=("Segoe UI", 11, "bold"), wraplength=720).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        frame,
        text=t("plan.affected", accounts=plan.affected_accounts, folders=plan.affected_folders),
    ).grid(row=1, column=0, sticky="w", pady=(2, 8))

    columns = ("action", "from", "to")
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=6)
    for column, width in zip(columns, (110, 300, 300), strict=True):
        tree.heading(column, text=t(f"plan.col.{column}"))
        tree.column(column, width=width, anchor="w")
    for row in plan_rows(plan):
        tree.insert("", tk.END, values=row)
    tree.grid(row=2, column=0, sticky="nsew")

    if plan.conflicts:
        box = tk.Text(frame, height=4, wrap="word", foreground="#b00020", relief="flat")
        for conflict in plan.conflicts:
            box.insert(tk.END, ("✖ " if conflict.blocking else "! ") + conflict.message + "\n")
        box.configure(state="disabled")
        box.grid(row=3, column=0, sticky="ew", pady=(8, 0))

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, sticky="e", pady=(10, 0))

    def _ok() -> None:
        result["ok"] = True
        window.destroy()

    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    run = ttk.Button(buttons, text=t("plan.execute"), command=_ok)
    run.pack(side=tk.RIGHT)
    if not plan.can_execute:
        run.configure(state="disabled")
    bind_escape_close(window, on_close=window.destroy)
    window.grab_set()
    window.wait_window()
    return result["ok"]
