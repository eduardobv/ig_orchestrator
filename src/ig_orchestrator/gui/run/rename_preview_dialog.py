"""Dialog: where are the files, preview of the rename, run (integrated renamer)."""

from __future__ import annotations

import os
import random
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from sqlite3 import Connection
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.db.instances_repository import InstanceRepository
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.audit_cli import native_path_text
from ig_orchestrator.renaming import NewAccountSpec, RenameJob, RenamePreview, RenameService
from ig_orchestrator.renaming.service import NEW_ACCOUNT, SKIPPED

MAX_FILES_SHOWN = 400


def source_choices(connection: Connection, working_folder: str) -> list[tuple[str, str]]:
    """``(label, path)`` options for "where are the files": own working folder + registered instances."""

    choices = [(t("rename.src.working"), working_folder)]
    for instance in InstanceRepository(connection).list():
        for label, path in (
            (t("rename.src.instance_working", name=instance.name), instance.working_path),
            (t("rename.src.instance_exchange", name=instance.name), instance.exchange_path),
        ):
            if path and path != working_folder and (label, path) not in choices:
                choices.append((label, path))
    return choices


def account_status_text(plan) -> str:
    if plan.status == SKIPPED:
        return t("rename.status.skipped")
    return t("rename.status.new") if plan.status == NEW_ACCOUNT else t("rename.status.rename")


def move_text(plan) -> str:
    if plan.pending_move:
        return t("rename.move.pending")
    if plan.move is None:
        return "-"
    if plan.move.status == "MOVED":
        return os.path.dirname(plan.move.destination) or plan.move.destination
    return t("rename.move.conflict")


def show_rename_dialog(
    parent: tk.Misc,
    connection: Connection,
    *,
    working_folder: str,
    start_now_date: str,
    new_accounts: tuple,
    on_execute: Callable[[RenamePreview], None],
    root: str | None = None,
) -> None:
    """Interactive preview. ``on_execute(preview)`` is called when the user confirms."""

    service = RenameService(connection, root=root)
    specs = tuple(NewAccountSpec(a.username, a.owner_id, a.start_init_date, a.destination_path) for a in new_accounts)
    window = tk.Toplevel(parent)
    window.title(t("rename.dialog.title"))
    window.geometry("1000x620")
    window.minsize(760, 480)
    window.transient(parent)
    state: dict[str, object] = {"preview": None, "seed": None}
    choices = source_choices(connection, working_folder)
    source_var = tk.StringVar(value=working_folder)
    choice_var = tk.StringVar(value=choices[0][0])
    dedupe_var = tk.BooleanVar(value=True)
    move_var = tk.BooleanVar(value=True)
    index_var = tk.BooleanVar(value=False)
    info = tk.StringVar()

    frame = ttk.Frame(window, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(4, weight=1)
    ttk.Label(frame, text=t("rename.dialog.where")).grid(row=0, column=0, sticky="w")
    box = ttk.Combobox(frame, textvariable=choice_var, values=[c[0] for c in choices], state="readonly", width=34)
    box.grid(row=0, column=1, sticky="w", padx=8)
    ttk.Label(frame, text=t("rename.dialog.date", date=start_now_date)).grid(row=0, column=2, sticky="e")
    ttk.Entry(frame, textvariable=source_var).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    ttk.Button(frame, text=t("audit.browse"), command=lambda: browse()).grid(row=1, column=2, sticky="e", pady=(6, 0))
    options = ttk.Frame(frame)
    options.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
    ttk.Checkbutton(options, text=t("rename.dialog.dedupe"), variable=dedupe_var).pack(side=tk.LEFT)
    ttk.Checkbutton(options, text=t("rename.dialog.move"), variable=move_var).pack(side=tk.LEFT, padx=12)
    ttk.Checkbutton(options, text=t("rename.dialog.use_index"), variable=index_var).pack(side=tk.LEFT)
    ttk.Button(options, text=t("rename.dialog.compute"), command=lambda: compute(None)).pack(side=tk.LEFT, padx=12)
    ttk.Button(options, text=t("rename.dialog.reseed"), command=lambda: compute(random.SystemRandom().randrange(1, 2**31))).pack(side=tk.LEFT)
    ttk.Label(frame, textvariable=info, wraplength=940, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 4))

    tree = ttk.Treeview(frame, columns=("status", "old", "new", "date"), show="tree headings")
    tree.heading("#0", text=t("rename.col.account"))
    tree.column("#0", width=250)
    for column, width in zip(("status", "old", "new", "date"), (130, 230, 300, 140), strict=True):
        tree.heading(column, text=t(f"rename.col.{column}"))
        tree.column(column, width=width, anchor="w")
    tree.grid(row=4, column=0, columnspan=3, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=4, column=3, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=3, sticky="e", pady=(10, 0))
    run = ttk.Button(buttons, text=t("plan.execute"), state="disabled")

    def browse() -> None:
        chosen = filedialog.askdirectory(parent=window, initialdir=source_var.get() or None)
        if chosen:
            source_var.set(native_path_text(chosen))
            compute(None)

    def on_choice(_event=None) -> None:
        for label, path in choices:
            if label == choice_var.get():
                source_var.set(path)
        compute(None)

    box.bind("<<ComboboxSelected>>", on_choice)

    def compute(seed: int | None) -> None:
        tree.delete(*tree.get_children())
        run.configure(state="disabled")
        source = native_path_text(source_var.get())
        job = RenameJob(source, start_now_date, specs, dedupe_var.get(), move_var.get(), "index" if index_var.get() else "auto")
        try:
            preview = service.preview(job, seed=seed or state["seed"])
        except ValueError as exc:
            info.set(str(exc))
            return
        state["preview"], state["seed"] = preview, preview.seed
        total_renamed = total_dups = skipped = 0
        for plan in preview.accounts:
            node = tree.insert("", tk.END, text=plan.username,
                               values=(account_status_text(plan), plan.reason or (t("rename.ref.index") + " · " if plan.reference == "INDEX" else "") + move_text(plan), "", ""), open=False)
            skipped += plan.status == SKIPPED
            total_renamed += plan.renamed
            total_dups += plan.duplicated
            for action in plan.actions[:MAX_FILES_SHOWN]:
                kind = t("rename.kind.dup") if action.kind == "DUPLICATE" else t("rename.kind.rename")
                tree.insert(node, tk.END, text="", values=(kind, os.path.basename(action.old), os.path.basename(action.new), action.date))
            if len(plan.actions) > MAX_FILES_SHOWN:
                tree.insert(node, tk.END, text="", values=("...", t("rename.more", count=len(plan.actions) - MAX_FILES_SHOWN), "", ""))
            for note in [*plan.tree.warnings, *plan.tree.errors][:5]:
                tree.insert(node, tk.END, text="", values=("!", note, "", ""))
            if plan.move is not None and plan.move.status != "MOVED":
                tree.insert(node, tk.END, text="", values=("✖", plan.move.detail or t("rename.move.conflict"), "", ""))
        info.set(t("rename.dialog.summary", accounts=len(preview.accounts), renamed=total_renamed, dups=total_dups,
                   skipped=skipped, seed=preview.seed))
        run.configure(state="normal" if preview.runnable else "disabled")

    def execute() -> None:
        preview = state["preview"]
        if preview is None:
            return
        if not messagebox.askyesno(t("rename.dialog.title"), t("rename.dialog.confirm", seed=preview.seed), parent=window):
            return
        window.destroy()
        on_execute(preview)  # type: ignore[arg-type]

    ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT, padx=(6, 0))
    run.configure(command=execute)
    run.pack(side=tk.RIGHT)
    bind_escape_close(window, on_close=window.destroy)
    if not Path(source_var.get()).is_dir():
        info.set(t("rename.dialog.no_source"))
    else:
        compute(None)
