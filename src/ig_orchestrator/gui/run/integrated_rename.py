"""Mixin: run the integrated renamer from the main window (preview -> run in background -> result)."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import messagebox

from ig_orchestrator.db import connect
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.run.rename_preview_dialog import show_rename_dialog
from ig_orchestrator.renaming import NewAccountSpec, RenameJob, RenamePreview, RenameResult, RenameService
from ig_orchestrator.renaming.settings import preview_required


def describe_result(result: RenameResult) -> str:
    lines = [t("rename.result.summary", summary=result.summary())]
    for account in result.accounts:
        flags = []
        if account.moved:
            flags.append(t("rename.result.moved"))
        if account.deleted_duplicates:
            flags.append(t("rename.result.deleted", count=account.deleted_duplicates))
        detail = f" - {account.detail}" if account.detail else ""
        lines.append(
            f"  @{account.username}: {account.status} · {account.renamed} renombrados · {account.duplicated} duplicados"
            + (f" · {', '.join(flags)}" if flags else "")
            + detail
        )
        lines.extend(f"      ! {w}" for w in account.warnings[:3])
    return "\n".join(lines)


class IntegratedRenameMixin:
    _rename_cancel: threading.Event | None = None

    def _start_integrated_rename(self, start_now_date: str, new_accounts: tuple) -> None:
        working = str(self.settings.working_folder)
        if preview_required(self.connection):
            show_rename_dialog(
                self.root,
                self.connection,
                working_folder=working,
                start_now_date=start_now_date,
                new_accounts=new_accounts,
                on_execute=self._run_integrated_rename,
            )
            return
        specs = tuple(NewAccountSpec(a.username, a.owner_id, a.start_init_date, a.destination_path) for a in new_accounts)
        try:
            preview = RenameService(self.connection).preview(RenameJob(working, start_now_date, specs))
        except ValueError as exc:
            messagebox.showerror(t("rename.dialog.title"), str(exc), parent=self.root)
            return
        self._run_integrated_rename(preview)

    def _run_integrated_rename(self, preview: RenamePreview) -> None:
        gui_db = Path(self.settings.sqlite_gui_db_path)
        results: queue.Queue = queue.Queue()
        self._rename_cancel = threading.Event()
        self.active_process_kind = "rename"
        self._set_process_running(True)
        self._set_status(t("rename.running"))
        self._write_console(
            t("rename.start_console", source=preview.job.source_folder, date=preview.job.start_now_date, seed=preview.seed) + "\n"
        )

        def progress(index: int, total: int, username: str) -> None:
            results.put(("progress", f"[{index}/{total}] @{username}"))

        def work() -> None:
            try:
                connection = connect(gui_db)
                try:
                    results.put(("done", RenameService(connection).run(preview, progress=progress, cancel_event=self._rename_cancel)))
                finally:
                    connection.close()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                results.put(("error", f"{type(exc).__name__}: {exc}"))

        def poll() -> None:
            try:
                while True:
                    kind, payload = results.get_nowait()
                    if kind == "progress":
                        self._write_console(payload + "\n")
                        self._set_status(t("rename.running") + " " + payload)
                        continue
                    if kind == "error":
                        self._write_console(payload + "\n")
                        messagebox.showerror(t("rename.dialog.title"), payload, parent=self.root)
                        self._handle_rename_complete(1)
                    else:
                        self._finish_integrated_rename(payload)
                    return
            except queue.Empty:
                pass
            self.root.after(200, poll)

        threading.Thread(target=work, name="integrated-rename", daemon=True).start()
        self.root.after(200, poll)

    def _finish_integrated_rename(self, result: RenameResult) -> None:
        text = describe_result(result)
        self._write_console(text + "\n")
        self._reload_catalog()
        self._rename_cancel = None
        self._handle_rename_complete(0 if result.ok else 1)
        if result.cancelled:
            messagebox.showinfo(t("rename.dialog.title"), t("rename.result.cancelled"), parent=self.root)
        elif result.problems:
            messagebox.showwarning(t("rename.dialog.title"), text, parent=self.root)
