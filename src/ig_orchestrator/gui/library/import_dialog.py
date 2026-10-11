"""Dialog: import accounts_complete/accounts_lite into bdapp (dry-run first)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.db import connect
from ig_orchestrator.db.gui_migrations import backup_database
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import _gui_setting, bind_escape_close
from ig_orchestrator.gui.stories.settings import STORIES_DB_SETTING
from ig_orchestrator.library.audit_cli import default_complete_path, native_path_text
from ig_orchestrator.library.import_bdsc1 import import_from_bdsc1


def run_import_in_thread(
    gui_db_path: Path,
    lite: Path | None,
    complete: Path | None,
    *,
    dry_run: bool,
    include_media: bool,
    result_queue: "queue.Queue[tuple[str, object]]",
) -> threading.Thread:
    """Run the import off the Tk thread with its own connection (backup first if real)."""

    def _work() -> None:
        try:
            connection = connect(gui_db_path)
            try:
                backup = None if dry_run else backup_database(connection, "pre_import")
                report = import_from_bdsc1(
                    connection,
                    lite,
                    complete,
                    dry_run=dry_run,
                    include_media=include_media,
                )
            finally:
                connection.close()
            result_queue.put(("done", (report, backup)))
        except Exception as exc:  # surfaced to the user in the dialog
            result_queue.put(("error", exc))

    thread = threading.Thread(target=_work, name="library-import", daemon=True)
    thread.start()
    return thread


class LibraryImportMixin:
    """Mixin: Catálogo → Importar desde bdsc1…"""

    def _open_library_import(self) -> None:
        existing = getattr(self, "_library_import_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return
            except tk.TclError:
                self._library_import_window = None

        window = tk.Toplevel(self.root)
        window.title(t("import.title"))
        window.geometry("820x520")
        window.minsize(620, 380)
        self._library_import_window = window

        saved_lite = native_path_text(_gui_setting(self.connection, STORIES_DB_SETTING, ""))
        lite_var = tk.StringVar(value=saved_lite)
        complete_var = tk.StringVar(
            value=str(default_complete_path(Path(saved_lite))) if saved_lite else ""
        )
        media_var = tk.BooleanVar(value=True)
        status_var = tk.StringVar()
        results: queue.Queue = queue.Queue()
        last_report: dict[str, object] = {}

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text=t("import.step0"), wraplength=760, justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        for row, (label_key, var) in enumerate(
            (("audit.lite", lite_var), ("audit.complete", complete_var)), start=1
        ):
            ttk.Label(frame, text=t(label_key)).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8)
            ttk.Button(
                frame, text=t("audit.browse"), command=lambda v=var: _browse_file(window, v)
            ).grid(row=row, column=2)
        ttk.Checkbutton(frame, text=t("import.include_media"), variable=media_var).grid(
            row=3, column=1, sticky="w", pady=(4, 0)
        )

        report_box = tk.Text(frame, wrap="word", height=14, state="disabled")
        report_box.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(8, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        simulate = ttk.Button(actions, text=t("import.simulate"))
        simulate.pack(side=tk.LEFT)
        apply_button = ttk.Button(actions, text=t("import.apply"))
        apply_button.pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text=t("import.save_report"), command=lambda: save_report()).pack(
            side=tk.LEFT
        )
        ttk.Label(actions, textvariable=status_var).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text=t("audit.close"), command=window.destroy).pack(side=tk.RIGHT)

        def show(text: str) -> None:
            report_box.configure(state="normal")
            report_box.delete("1.0", tk.END)
            report_box.insert("1.0", text)
            report_box.configure(state="disabled")

        def set_busy(busy: bool) -> None:
            state = "disabled" if busy else "normal"
            simulate.configure(state=state)
            apply_button.configure(state=state)

        def poll() -> None:
            try:
                kind, payload = results.get_nowait()
            except queue.Empty:
                window.after(200, poll)
                return
            set_busy(False)
            if kind == "error":
                status_var.set(t("import.failed"))
                show(str(payload))
                return
            report, backup = payload
            last_report["report"] = report
            text = report.render()
            if backup is not None:
                text += f"\n\n{t('import.backup', path=backup)}"
            show(text)
            status_var.set(t("import.done_dry") if report.dry_run else t("import.done"))
            if not report.dry_run:
                self._reload_catalog()
                self._write_console(text + "\n")

        def save_report() -> None:
            report = last_report.get("report")
            if report is None:
                return
            chosen = filedialog.asksaveasfilename(
                parent=window, defaultextension=".txt", initialfile="import-bdsc1.txt"
            )
            if chosen:
                Path(chosen).write_text(report.render(full=True), encoding="utf-8")
                status_var.set(t("audit.exported", path=chosen))

        def start(dry_run: bool) -> None:
            lite_text = native_path_text(lite_var.get())
            complete_text = native_path_text(complete_var.get())
            lite_var.set(lite_text)
            complete_var.set(complete_text)
            if not lite_text and not complete_text:
                messagebox.showerror(t("import.title"), t("audit.paths_required"), parent=window)
                return
            if not dry_run and not messagebox.askyesno(
                t("import.title"), t("import.confirm"), parent=window
            ):
                return
            set_busy(True)
            status_var.set(t("import.running"))
            run_import_in_thread(
                Path(self.settings.sqlite_gui_db_path),
                Path(lite_text) if lite_text else None,
                Path(complete_text) if complete_text else None,
                dry_run=dry_run,
                include_media=media_var.get(),
                result_queue=results,
            )
            window.after(200, poll)

        simulate.configure(command=lambda: start(True))
        apply_button.configure(command=lambda: start(False))

        def _on_close() -> None:
            self._library_import_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _on_close)
        bind_escape_close(window, on_close=_on_close)


def _browse_file(parent: tk.Misc, variable: tk.StringVar) -> None:
    chosen = filedialog.askopenfilename(
        parent=parent,
        filetypes=[("SQLite", "*.sqlite *.db *.sqlite3"), ("All files", "*.*")],
    )
    if chosen:
        variable.set(native_path_text(chosen))
