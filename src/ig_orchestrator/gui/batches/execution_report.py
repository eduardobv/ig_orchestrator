"""«Informe de ejecución» modal (feat-run-36): reads the telemetry of one batch."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from sqlite3 import Connection
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close, center_modal_on_parent
from ig_orchestrator.telemetry.report import (
    PHASES,
    BatchReport,
    attempts_to_csv,
    build_batch_report,
    explain,
    report_to_markdown,
    _fmt_seconds,
    _n,
)


def latest_batch_with_telemetry(connection: Connection) -> int | None:
    try:
        row = connection.execute(
            "SELECT batch_id FROM url_job_attempts WHERE batch_id IS NOT NULL "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    except Exception:
        return None
    return int(row[0]) if row else None


def open_execution_report(parent: tk.Misc, connection: Connection, batch_id: int | None) -> None:
    """Open the report of ``batch_id`` (or of the latest measured batch)."""

    if batch_id is None:
        batch_id = latest_batch_with_telemetry(connection)
    if batch_id is None:
        messagebox.showinfo(t("report.title"), t("report.none"), parent=parent)
        return
    report = build_batch_report(connection, batch_id)
    if not report.attempts:
        messagebox.showinfo(t("report.title"), t("report.no_data"), parent=parent)
        return

    window = tk.Toplevel(parent)
    window.title(f"{t('report.title')} — {report.batch_name}")
    window.geometry("1000x640")
    window.transient(parent)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    bind_escape_close(window)

    notebook = ttk.Notebook(window)
    notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
    _summary_tab(notebook, report)
    _table_tab(
        notebook, t("report.tab.slowest"),
        ("#", "Cuenta", "Tipo", "Total", "Por qué"), (40, 180, 110, 90, 520),
        [
            (i, a.account, a.publication_type, _fmt_seconds(a.total_ms / 1000), explain(a))
            for i, a in enumerate(report.slowest, start=1)
        ],
    )
    _table_tab(
        notebook, t("report.tab.by_type"),
        ("Tipo", "N", "1ª resp. p50", "p90", "máx", "Total p50", "p90", "máx"),
        (160, 60, 100, 80, 80, 100, 80, 80),
        [
            (s.label, s.count, _n(s.first_p50), _n(s.first_p90), _n(s.first_max),
             _n(s.total_p50), _n(s.total_p90), _n(s.total_max))
            for s in report.by_type
        ],
    )
    _table_tab(
        notebook, t("report.tab.errors"),
        ("Código", "N", "Hasta mensaje (s)", "Reintentos", "Tiempo perdido"),
        (240, 60, 140, 100, 140),
        [
            (e.code, e.count,
             _n(e.avg_first_response_ms and e.avg_first_response_ms / 1000),
             e.retries_used, _fmt_seconds(e.lost_ms / 1000))
            for e in report.errors
        ],
    )
    _table_tab(
        notebook, t("report.tab.retries"),
        ("Intento", "Intentos", "Completados", "Éxito"), (100, 100, 120, 100),
        [
            (r.attempt_no, r.attempts, r.completed,
             f"{100 * r.completed / r.attempts:.0f} %" if r.attempts else "—")
            for r in report.retries
        ],
    )
    _recommendations_tab(notebook, report)

    buttons = ttk.Frame(window)
    buttons.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
    ttk.Button(
        buttons, text=t("report.export_md"),
        command=lambda: _export(window, report, "md"),
    ).pack(side=tk.LEFT)
    ttk.Button(
        buttons, text=t("report.export_csv"),
        command=lambda: _export(window, report, "csv"),
    ).pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(buttons, text=t("report.close"), command=window.destroy).pack(side=tk.RIGHT)
    center_modal_on_parent(window, parent, False)


def _summary_tab(notebook: ttk.Notebook, report: BatchReport) -> None:
    frame = ttk.Frame(notebook, padding=12)
    notebook.add(frame, text=t("report.tab.summary"))
    per_hour = report.urls_per_hour
    ttk.Label(
        frame,
        text=(
            f"{report.accounts} cuentas · {report.urls} URLs · {len(report.attempts)} intentos\n"
            f"Duración {_fmt_seconds(report.wall_seconds)} · activo "
            f"{_fmt_seconds(report.active_seconds)}"
            + (f" · {per_hour:.0f} URLs/h" if per_hour else "")
        ),
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(0, 8))
    percents = report.phase_percent()
    table = ttk.Treeview(frame, columns=("phase", "pct", "time"), show="headings", height=8)
    for column, title, width in (("phase", "Fase", 260), ("pct", "%", 80), ("time", "Tiempo", 140)):
        table.heading(column, text=title)
        table.column(column, width=width, anchor="w" if column == "phase" else "e")
    for name, label in PHASES:
        table.insert(
            "", tk.END,
            values=(label, f"{percents[name]:.0f}", _fmt_seconds(report.phase_ms[name] / 1000)),
        )
    table.pack(anchor="w")


def _table_tab(notebook, title, columns, widths, rows) -> None:
    frame = ttk.Frame(notebook, padding=6)
    notebook.add(frame, text=title)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree = ttk.Treeview(frame, columns=columns, show="headings")
    for column, width in zip(columns, widths):
        tree.heading(column, text=column)
        tree.column(column, width=width, anchor="w")
    for row in rows:
        tree.insert("", tk.END, values=row)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    if not rows:
        ttk.Label(frame, text=t("report.empty")).place(relx=0.5, rely=0.4, anchor="center")


def _recommendations_tab(notebook: ttk.Notebook, report: BatchReport) -> None:
    frame = ttk.Frame(notebook, padding=12)
    notebook.add(frame, text=t("report.tab.recommendations"))
    text = "\n\n".join(f"• {item}" for item in report.recommendations) or t("report.no_advice")
    ttk.Label(frame, text=text, wraplength=900, justify=tk.LEFT).pack(anchor="nw")


def _export(window: tk.Toplevel, report: BatchReport, kind: str) -> None:
    extension = ".md" if kind == "md" else ".csv"
    path = filedialog.asksaveasfilename(
        parent=window,
        defaultextension=extension,
        initialfile=f"informe_lote_{report.batch_id}{extension}",
        filetypes=[("Markdown" if kind == "md" else "CSV", f"*{extension}")],
    )
    if not path:
        return
    content = report_to_markdown(report) if kind == "md" else attempts_to_csv(report)
    Path(path).write_text(content, encoding="utf-8")
    messagebox.showinfo(t("report.title"), t("report.exported").format(path=path), parent=window)


__all__ = ["latest_batch_with_telemetry", "open_execution_report"]
