"""Dialog: review (and edit) where deleted accounts will be moved, then confirm."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.folder_picker import pick_destination
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService, LifecyclePlan


def reason_text(reason: str) -> str:
    return t(f"life.reason.{reason}")


def destination_rows(
    service: AccountLifecycleService, account_ids: list[int], lifecycle: LifecyclePlan
) -> list[tuple[int, str, str, str, str]]:
    """``(account_id, username, from, to, reason)`` rows for the table."""

    sources = {
        int(r["id"]): (str(r["username"]), str(r["rel_path"] or "-"))
        for r in service._accounts(account_ids)
    }
    actions = {a.account_id: a for a in lifecycle.actions}
    rows = []
    for account_id in account_ids:
        username, src = sources.get(account_id, ("?", "-"))
        dest, reason = lifecycle.destinations.get(account_id, ("", ""))
        action = actions.get(account_id)
        shown = t("life.status_only") if action is not None and action.dst_rel is None else (dest or "-")
        rows.append((account_id, username, src, shown, reason_text(reason) if reason else ""))
    return rows


def choose_delete_plan(parent: tk.Misc, service: AccountLifecycleService, account_ids: list[int]) -> LifecyclePlan | None:
    """Show the suggested destinations; the user may change them. Returns the plan to run."""

    window = tk.Toplevel(parent)
    window.title(t("life.dest_title"))
    window.transient(parent)
    window.geometry("900x470")
    window.minsize(700, 380)
    overrides: dict[int, str] = {}
    suffix_var = tk.BooleanVar(value=False)
    state: dict[str, object] = {"plan": None, "result": None}

    frame = ttk.Frame(window, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    ttk.Label(frame, text=t("life.dest_hint"), wraplength=860, justify="left").grid(row=0, column=0, sticky="w", pady=(0, 6))

    columns = ("user", "from", "to", "why")
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
    for column, width in zip(columns, (150, 280, 280, 170), strict=True):
        tree.heading(column, text=t(f"life.dest.col.{column}"))
        tree.column(column, width=width, anchor="w")
    tree.grid(row=1, column=0, sticky="nsew")

    tools = ttk.Frame(frame)
    tools.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    info = tk.Text(frame, height=4, wrap="word", relief="flat")
    info.grid(row=3, column=0, sticky="ew", pady=(6, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, sticky="e", pady=(10, 0))
    run = ttk.Button(buttons, text=t("plan.execute"))

    def selected_ids() -> list[int]:
        return [int(i) for i in tree.selection()]

    def refresh() -> None:
        lifecycle = service.plan_mark_deleted(
            account_ids, suffix_on_conflict=suffix_var.get(), dest_overrides=dict(overrides)
        )
        state["plan"] = lifecycle
        keep = set(tree.selection())
        tree.delete(*tree.get_children())
        for account_id, username, src, dest, why in destination_rows(service, account_ids, lifecycle):
            tree.insert("", tk.END, iid=str(account_id), values=(username, src, dest, why))
        for item in keep:
            if tree.exists(item):
                tree.selection_add(item)
        info.configure(state="normal", foreground="#b00020")
        info.delete("1.0", tk.END)
        for conflict in lifecycle.plan.conflicts:
            info.insert(tk.END, ("✖ " if conflict.blocking else "! ") + conflict.message + "\n")
        info.configure(state="disabled")
        run.configure(state="normal" if lifecycle.can_execute else "disabled")

    def change() -> None:
        ids = selected_ids()
        if not ids:
            return
        rel = pick_destination(window, service.conn, t("life.dest_pick"))
        if rel:
            for account_id in ids:
                overrides[account_id] = rel
            refresh()

    def use_deleted_folder() -> None:
        for account_id in selected_ids():
            overrides[account_id] = service.deleted_folder
        refresh()

    def reset() -> None:
        for account_id in selected_ids():
            overrides.pop(account_id, None)
        refresh()

    def _ok() -> None:
        state["result"] = state["plan"]
        window.destroy()

    ttk.Button(tools, text=t("life.dest_change"), command=change).pack(side=tk.LEFT)
    ttk.Button(tools, text=t("life.dest_use_deleted"), command=use_deleted_folder).pack(side=tk.LEFT, padx=6)
    ttk.Button(tools, text=t("life.dest_reset"), command=reset).pack(side=tk.LEFT)
    ttk.Checkbutton(tools, text=t("life.dest_suffix"), variable=suffix_var, command=refresh).pack(side=tk.LEFT, padx=14)
    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    run.configure(command=_ok)
    run.pack(side=tk.RIGHT)
    bind_escape_close(window, on_close=window.destroy)
    refresh()
    if len(account_ids) == 1 and tree.get_children():
        tree.selection_set(tree.get_children()[0])
    window.grab_set()
    window.wait_window()
    return state["result"]  # type: ignore[return-value]
