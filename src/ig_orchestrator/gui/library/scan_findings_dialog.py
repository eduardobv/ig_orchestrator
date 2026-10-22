"""Dialog: findings of the library synchronisation (accept / ignore)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.scanner import ScanError, accept_finding, ignore_finding, list_findings

KINDS = ("NEW_FOLDER", "MOVED_FOLDER", "MISSING_FOLDER", "OWNER_CHANGED", "USERNAME_DUP")


def kind_text(kind: str) -> str:
    return t(f"scan.kind.{kind}")


def open_findings(app) -> None:
    existing = getattr(app, "_scan_findings_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                return
        except tk.TclError:
            app._scan_findings_window = None
    window = tk.Toplevel(app.root)
    window.title(t("scan.findings_title"))
    window.geometry("940x480")
    app._scan_findings_window = window
    frame = ttk.Frame(window, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.rowconfigure(1, weight=1)
    frame.columnconfigure(0, weight=1)
    top = ttk.Frame(frame)
    top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(top, text=t("scan.filter")).pack(side=tk.LEFT)
    all_label = t("audit.all")
    filter_var = tk.StringVar(value=all_label)
    box = ttk.Combobox(top, textvariable=filter_var, state="readonly", width=28,
                       values=[all_label, *(kind_text(k) for k in KINDS)])
    box.pack(side=tk.LEFT, padx=6)
    columns = ("kind", "account", "path", "detail")
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
    for column, width in zip(columns, (170, 130, 300, 300), strict=True):
        tree.heading(column, text=t(f"scan.col.{column}"))
        tree.column(column, width=width, anchor="w")
    tree.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status, wraplength=880).grid(row=2, column=0, sticky="w", pady=(6, 0))

    def load() -> None:
        tree.delete(*tree.get_children())
        wanted = filter_var.get()
        for row in list_findings(app.connection):
            label = kind_text(str(row["kind"]))
            if wanted != all_label and label != wanted:
                continue
            tree.insert("", tk.END, iid=str(row["id"]),
                        values=(label, row["username"] or "-", row["rel_path"] or "-", row["detail"] or ""))
        status.set(t("scan.findings_count", count=len(tree.get_children())))

    def selected() -> list[int]:
        return [int(i) for i in tree.selection()]

    def accept() -> None:
        ids = selected()
        if not ids or not messagebox.askyesno(t("scan.findings_title"), t("scan.accept_confirm", count=len(ids)), parent=window):
            return
        messages = []
        for finding_id in ids:
            try:
                messages.append(accept_finding(app.connection, finding_id))
            except (ScanError, Exception) as exc:  # noqa: BLE001 - shown to the user
                messages.append(f"#{finding_id}: {exc}")
        status.set(" · ".join(messages[:3]))
        app._reload_catalog()
        load()

    def ignore() -> None:
        for finding_id in selected():
            ignore_finding(app.connection, finding_id)
        load()

    box.bind("<<ComboboxSelected>>", lambda _e: load())
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(buttons, text=t("scan.accept"), command=accept).pack(side=tk.LEFT)
    ttk.Button(buttons, text=t("scan.ignore"), command=ignore).pack(side=tk.LEFT, padx=8)
    ttk.Button(buttons, text=t("owners.refresh"), command=load).pack(side=tk.LEFT)
    ttk.Button(buttons, text=t("audit.close"), command=window.destroy).pack(side=tk.RIGHT)
    window.protocol("WM_DELETE_WINDOW", lambda: (setattr(app, "_scan_findings_window", None), window.destroy()))
    bind_escape_close(window, on_close=window.destroy)
    load()
