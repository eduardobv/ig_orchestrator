"""Dialog: review a username change (simple rename or merge) before it runs."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.plan_dialog import plan_rows
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.account_rename import MERGE, STATUS_ONLY, AccountRenameService, RenamePlan


def scenario_text(plan: RenamePlan) -> str:
    if plan.scenario == MERGE:
        if plan.orphan_folder:
            return t("rename.scenario_orphan", new=plan.new_username)
        return t("rename.scenario_merge", new=plan.new_username)
    if plan.scenario == STATUS_ONLY:
        return t("rename.scenario_status")
    return t("rename.scenario_simple", old=plan.old_username, new=plan.new_username)


def confirm_rename(
    parent: tk.Misc, service: AccountRenameService, account_id: int, new_username: str
) -> RenamePlan | None:
    """Show the plan; returns the (re-planned) plan to execute, or ``None`` if cancelled."""

    window = tk.Toplevel(parent)
    window.title(t("rename.title"))
    window.transient(parent)
    window.geometry("820x560")
    window.minsize(660, 460)
    survivor_var = tk.StringVar(value="auto")
    confirm_var = tk.BooleanVar(value=False)
    state: dict[str, object] = {"plan": None, "result": None}

    frame = ttk.Frame(window, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(4, weight=1)
    head = tk.StringVar()
    ttk.Label(frame, textvariable=head, font=("Segoe UI", 11, "bold"), wraplength=780, justify="left").grid(
        row=0, column=0, sticky="w"
    )
    info = tk.StringVar()
    ttk.Label(frame, textvariable=info, wraplength=780, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 6))

    merge_box = ttk.LabelFrame(frame, text=t("rename.keep"), padding=8)
    merge_box.grid(row=2, column=0, sticky="ew")
    candidates = ttk.Treeview(merge_box, columns=("user", "folder", "content", "last"), show="headings", height=2)
    for column, width in zip(("user", "folder", "content", "last"), (140, 360, 90, 150), strict=True):
        candidates.heading(column, text=t(f"rename.col.{column}"))
        candidates.column(column, width=width, anchor="w")
    candidates.grid(row=0, column=0, columnspan=3, sticky="ew")
    for column, (text_key, value) in enumerate(
        (("rename.keep_auto", "auto"), ("rename.keep_old", "old"), ("rename.keep_new", "new"))
    ):
        ttk.Radiobutton(
            merge_box, text=t(text_key), value=value, variable=survivor_var, command=lambda: refresh()
        ).grid(row=1, column=column, sticky="w", pady=(6, 0), padx=(0, 12))
    merge_text = tk.StringVar()
    ttk.Label(merge_box, textvariable=merge_text, wraplength=760, justify="left").grid(
        row=2, column=0, columnspan=3, sticky="w", pady=(6, 0)
    )
    confirm_check = ttk.Checkbutton(
        merge_box, text=t("rename.confirm_same"), variable=confirm_var, command=lambda: refresh()
    )

    ttk.Label(frame, text=t("plan.col.action")).grid(row=3, column=0, sticky="w", pady=(8, 0))
    steps = ttk.Treeview(frame, columns=("action", "from", "to"), show="headings", height=4)
    for column, width in zip(("action", "from", "to"), (110, 330, 330), strict=True):
        steps.heading(column, text=t(f"plan.col.{column}"))
        steps.column(column, width=width, anchor="w")
    steps.grid(row=4, column=0, sticky="nsew")
    conflicts = tk.Text(frame, height=4, wrap="word", relief="flat")
    conflicts.grid(row=5, column=0, sticky="ew", pady=(6, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, sticky="e", pady=(10, 0))
    run = ttk.Button(buttons, text=t("plan.execute"))

    def refresh() -> None:
        plan = service.plan_rename(
            account_id, new_username, survivor=survivor_var.get(), confirm_unverified=confirm_var.get()
        )
        state["plan"] = plan
        head.set(scenario_text(plan))
        extra = []
        if plan.rewrite_urls:
            extra.append(t("rename.urls", count=plan.rewrite_urls))
        info.set(" · ".join(extra))
        is_merge = plan.scenario == MERGE
        if is_merge:
            merge_box.grid()
            candidates.delete(*candidates.get_children())
            for c in plan.candidates:
                candidates.insert("", tk.END, values=(c.username, c.rel_path or "-", c.content, c.last_media_at or "-"))
            merge_text.set(plan.merge_report.summary() if plan.merge_report else t("rename.nothing_to_merge"))
            if plan.needs_confirmation:
                confirm_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
            else:
                confirm_check.grid_remove()
        else:
            merge_box.grid_remove()
        steps.delete(*steps.get_children())
        for row in plan_rows(plan.plan):
            steps.insert("", tk.END, values=row)
        conflicts.configure(state="normal", foreground="#b00020")
        conflicts.delete("1.0", tk.END)
        for conflict in plan.plan.conflicts:
            conflicts.insert(tk.END, ("✖ " if conflict.blocking else "! ") + conflict.message + "\n")
        conflicts.configure(state="disabled")
        run.configure(state="normal" if plan.can_execute else "disabled")

    def _ok() -> None:
        state["result"] = state["plan"]
        window.destroy()

    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    run.configure(command=_ok)
    run.pack(side=tk.RIGHT)
    bind_escape_close(window, on_close=window.destroy)
    refresh()
    window.grab_set()
    window.wait_window()
    return state["result"]  # type: ignore[return-value]
