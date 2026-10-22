"""Mixin: library synchronisation (quick / category / account / complete) run on demand."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import messagebox

from ig_orchestrator.db import connect
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.scan_findings_dialog import open_findings
from ig_orchestrator.library.scanner import (
    ACCOUNT,
    ALL,
    CATEGORY,
    LibraryScanner,
    ScanError,
    ScanReport,
    last_scan_age_days,
)


def deep_estimate_seconds(conn) -> float | None:
    row = conn.execute("SELECT seconds FROM scan_runs WHERE scope = 'DEEP' AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return float(row[0]) if row is not None and row[0] else None


class LibraryScanActionsMixin:
    _scan_running = False

    # ------------------------------------------------------------ plumbing
    def _scan_guard(self) -> bool:
        if self._scan_running:
            messagebox.showinfo(t("scan.title"), t("scan.running"), parent=self.root)
            return False
        if self.process_runner.is_running():
            messagebox.showinfo(t("scan.title"), t("fsops.busy_process"), parent=self.root)
            return False
        if not self._fsops_online():
            messagebox.showinfo(t("scan.title"), t("fsops.offline"), parent=self.root)
            return False
        return True

    def _run_scan(self, scope: str, *, rel_scope: str = "", account_id: int | None = None, deep: bool = False) -> None:
        if not self._scan_guard():
            return
        self._scan_running = True
        self._scan_cancel = threading.Event()
        results: queue.Queue = queue.Queue()
        gui_db = Path(self.settings.sqlite_gui_db_path)
        self._set_status(t("scan.working"))
        self._write_console(t("scan.working") + "\n")

        def progress(_stage: str, done: int, total: int) -> None:
            results.put(("progress", (done, total)))

        def work() -> None:
            try:
                connection = connect(gui_db)
                try:
                    report = LibraryScanner(connection).scan(
                        scope, rel_scope=rel_scope, account_id=account_id, deep=deep,
                        cancel_event=self._scan_cancel, progress=progress,
                    )
                finally:
                    connection.close()
                results.put(("done", report))
            except ScanError as exc:
                results.put(("error", str(exc)))
            except Exception as exc:  # noqa: BLE001 - shown to the user
                results.put(("error", f"{type(exc).__name__}: {exc}"))

        def poll() -> None:
            try:
                while True:
                    kind, payload = results.get_nowait()
                    if kind == "progress":
                        done, total = payload
                        self._set_status(t("scan.progress", done=done, total=total))
                        continue
                    self._scan_running = False
                    if kind == "error":
                        self._set_status(payload)
                        messagebox.showerror(t("scan.title"), payload, parent=self.root)
                    else:
                        self._finish_scan(payload)
                    return
            except queue.Empty:
                pass
            self.root.after(200, poll)

        threading.Thread(target=work, name="library-scan", daemon=True).start()
        self.root.after(200, poll)

    def _finish_scan(self, report: ScanReport) -> None:
        text = report.summary()
        self._set_status(text)
        self._write_console(f"Sincronizacion: {text}\n")
        self._reload_catalog()
        if report.findings:
            open_findings(self)
        else:
            messagebox.showinfo(t("scan.title"), t("scan.done_clean", summary=text), parent=self.root)

    # --------------------------------------------------------------- actions
    def _sync_quick(self) -> None:
        self._run_scan(ALL)

    def _sync_category(self) -> None:
        folder_id = self._selected_catalog_folder_id()
        if folder_id is None:
            messagebox.showinfo(t("scan.title"), t("scan.select_folder"), parent=self.root)
            return
        folder = self._fsops_service().folder(folder_id)
        self._run_scan(CATEGORY, rel_scope=folder.rel_path)

    def _sync_account(self) -> None:
        account_id = self._selected_catalog_account_id()
        if account_id is None:
            messagebox.showinfo(t("scan.title"), t("scan.select_account"), parent=self.root)
            return
        self._run_scan(ACCOUNT, account_id=account_id)

    def _sync_deep(self) -> None:
        estimate = deep_estimate_seconds(self.connection)
        text = t("scan.deep_estimate", minutes=f"{estimate / 60:.0f}") if estimate else t("scan.deep_estimate_unknown")
        if messagebox.askyesno(t("scan.title"), t("scan.deep_confirm", estimate=text), parent=self.root):
            self._run_scan(ALL, deep=True)

    def _open_scan_findings(self) -> None:
        open_findings(self)

    def _scan_reminder(self) -> str:
        age = last_scan_age_days(self.connection)
        return t("scan.never") if age is None else t("scan.age", days=f"{age:.0f}")
