"""Dialog: read-only library audit (bdapp vs accounts_lite/complete vs disk)."""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.db import connect_readonly
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import _open_path_in_explorer, bind_escape_close
from ig_orchestrator.gui.stories.settings import STORIES_DB_SETTING
from ig_orchestrator.gui.shared.helpers import _gui_setting
from ig_orchestrator.library.audit import run_audit
from ig_orchestrator.library.audit_cli import default_complete_path
from ig_orchestrator.library.audit_report import (
    AuditReport,
    Finding,
    render_csv,
    render_markdown,
)

ALL_CODES = "(all)"


def run_audit_in_thread(
    gui_db_path: Path,
    lite: Path,
    complete: Path | None,
    result_queue: "queue.Queue[tuple[str, object]]",
) -> threading.Thread:
    """Run the audit off the Tk thread with its own read-only connection."""

    def _work() -> None:
        try:
            connection = connect_readonly(gui_db_path)
            try:
                report = run_audit(connection, lite, complete)
            finally:
                connection.close()
            result_queue.put(("done", report))
        except Exception as exc:  # surfaced to the user in the dialog
            result_queue.put(("error", exc))

    thread = threading.Thread(target=_work, name="library-audit", daemon=True)
    thread.start()
    return thread


class LibraryAuditMixin:
    """Mixin: Catálogo → Auditar biblioteca…"""

    def _open_library_audit(self) -> None:
        existing = getattr(self, "_library_audit_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return
            except tk.TclError:
                self._library_audit_window = None

        window = tk.Toplevel(self.root)
        window.title(t("audit.title"))
        window.geometry("980x560")
        window.minsize(720, 400)
        self._library_audit_window = window

        saved_lite = _gui_setting(self.connection, STORIES_DB_SETTING, "")
        lite_var = tk.StringVar(value=saved_lite)
        complete_var = tk.StringVar(
            value=str(default_complete_path(Path(saved_lite))) if saved_lite else ""
        )
        filter_var = tk.StringVar(value=t("audit.all"))
        state: dict[str, object] = {"report": None, "queue": queue.Queue()}

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        for row, (label_key, var) in enumerate(
            (("audit.lite", lite_var), ("audit.complete", complete_var))
        ):
            ttk.Label(frame, text=t(label_key)).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8)
            ttk.Button(
                frame,
                text=t("audit.browse"),
                command=lambda v=var: _browse_file(window, v),
            ).grid(row=row, column=2)

        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        run_button = ttk.Button(bar, text=t("audit.run"))
        run_button.pack(side=tk.LEFT)
        ttk.Label(bar, text=t("audit.filter")).pack(side=tk.LEFT, padx=(12, 4))
        filter_box = ttk.Combobox(bar, textvariable=filter_var, state="readonly", width=24)
        filter_box.pack(side=tk.LEFT)
        status_var = tk.StringVar()
        ttk.Label(bar, textvariable=status_var).pack(side=tk.LEFT, padx=12)

        columns = ("code", "severity", "username", "paths", "detail")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column, width in zip(columns, (150, 70, 180, 380, 260), strict=True):
            tree.heading(column, text=t(f"audit.col.{column}"))
            tree.column(column, width=width, anchor="w")
        tree.grid(row=3, column=0, columnspan=2, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.grid(row=3, column=2, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(
            actions,
            text=t("audit.export_md"),
            command=lambda: self._export_audit(window, state, "md", status_var),
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text=t("audit.export_csv"),
            command=lambda: self._export_audit(window, state, "csv", status_var),
        ).pack(side=tk.LEFT, padx=8)
        ttk.Button(
            actions,
            text=t("audit.open_folder"),
            command=lambda: _open_selected_folder(tree, window),
        ).pack(side=tk.LEFT)
        ttk.Button(actions, text=t("audit.close"), command=window.destroy).pack(side=tk.RIGHT)

        def _populate(*_args: object) -> None:
            report = state["report"]
            tree.delete(*tree.get_children())
            if not isinstance(report, AuditReport):
                return
            wanted = filter_var.get()
            for finding in report.findings:
                if wanted != t("audit.all") and finding.code != wanted:
                    continue
                tree.insert("", tk.END, values=_row(finding))

        def _poll() -> None:
            try:
                kind, payload = state["queue"].get_nowait()
            except queue.Empty:
                window.after(150, _poll)
                return
            run_button.configure(state="normal")
            if kind == "error":
                status_var.set(t("audit.failed", error=payload))
                return
            report = payload
            state["report"] = report
            codes = [t("audit.all"), *report.summary().keys()]
            filter_box.configure(values=codes)
            filter_var.set(t("audit.all"))
            _populate()
            status_var.set(t("audit.done", total=len(report.findings)))

        def _run() -> None:
            lite_text = lite_var.get().strip()
            if not lite_text:
                messagebox.showerror(t("audit.title"), t("audit.paths_required"), parent=window)
                return
            complete_text = complete_var.get().strip()
            run_button.configure(state="disabled")
            status_var.set(t("audit.running"))
            run_audit_in_thread(
                Path(self.settings.sqlite_gui_db_path),
                Path(lite_text),
                Path(complete_text) if complete_text else None,
                state["queue"],
            )
            window.after(150, _poll)

        run_button.configure(command=_run)
        filter_var.trace_add("write", _populate)

        def _on_close() -> None:
            self._library_audit_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _on_close)
        bind_escape_close(window, on_close=_on_close)

    def _export_audit(
        self,
        window: tk.Toplevel,
        state: dict[str, object],
        kind: str,
        status_var: tk.StringVar,
    ) -> None:
        report = state["report"]
        if not isinstance(report, AuditReport):
            return
        extension = ".md" if kind == "md" else ".csv"
        chosen = filedialog.asksaveasfilename(
            parent=window,
            defaultextension=extension,
            initialfile=f"audit-library{extension}",
        )
        if not chosen:
            return
        body = render_markdown(report) if kind == "md" else render_csv(report)
        Path(chosen).write_text(body, encoding="utf-8")
        status_var.set(t("audit.exported", path=chosen))


def _row(finding: Finding) -> tuple[str, str, str, str, str]:
    return (
        finding.code,
        finding.severity.value,
        finding.username,
        " | ".join(finding.paths),
        finding.detail,
    )


def _open_selected_folder(tree: ttk.Treeview, window: tk.Toplevel) -> None:
    selection = tree.selection()
    if not selection:
        return
    paths = str(tree.item(selection[0], "values")[3]).split(" | ")
    for raw in paths:
        candidate = Path(raw)
        while candidate != candidate.parent and not candidate.is_dir():
            candidate = candidate.parent
        if candidate.is_dir():
            try:
                _open_path_in_explorer(candidate)
            except OSError as exc:
                messagebox.showerror(t("audit.title"), str(exc), parent=window)
            return


def _browse_file(parent: tk.Misc, variable: tk.StringVar) -> None:
    chosen = filedialog.askopenfilename(
        parent=parent,
        filetypes=[("SQLite", "*.sqlite *.db *.sqlite3"), ("All files", "*.*")],
    )
    if chosen:
        variable.set(chosen)
