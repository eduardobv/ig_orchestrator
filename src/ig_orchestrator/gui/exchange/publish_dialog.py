"""Mixin: publish finished batches as a package (manual dialog + automatic after a run)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ig_orchestrator.db import connect
from ig_orchestrator.db.instances_repository import InstanceRepository
from ig_orchestrator.exchange.publish import (
    PublishResult,
    local_exchange_root,
    publish_batches,
    read_publish_settings,
    unpublished_batches,
)
from ig_orchestrator.gui.batch_queue_service import BatchQueueError, get_queue
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close


def describe_result(result: PublishResult) -> str:
    if result.ok:
        text = t("publish.done", accounts=result.accounts, files=result.files, path=result.path)
        if result.missing_accounts:
            text += "\n" + t("publish.missing", names=", ".join(result.missing_accounts[:10]))
        return text
    return t("publish.failed", error=result.error)


class PublishDialogMixin:
    # ------------------------------------------------------------ plumbing
    def _publish_context(self) -> tuple[Path, str] | None:
        root = local_exchange_root(self.connection)
        if root is None:
            return None
        local = InstanceRepository(self.connection).get_local()
        return root, (local.name if local is not None else "inst")

    def _run_publish_async(self, batch_ids: list[int], mode: str, on_done) -> None:
        """Publish in a worker thread (own DB connection); ``on_done(result)`` runs on the Tk thread."""

        context = self._publish_context()
        if context is None:
            on_done(PublishResult(error=t("publish.no_exchange")))
            return
        root, instance = context
        results: queue.Queue = queue.Queue()
        gui_db = Path(self.settings.sqlite_gui_db_path)
        working = Path(self.settings.working_folder)

        def work() -> None:
            try:
                connection = connect(gui_db)
                try:
                    results.put(publish_batches(connection, batch_ids, working, root, instance=instance, mode=mode))
                finally:
                    connection.close()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                results.put(PublishResult(error=str(exc)))

        def poll() -> None:
            try:
                result = results.get_nowait()
            except queue.Empty:
                self.root.after(300, poll)
                return
            on_done(result)

        threading.Thread(target=work, name="exchange-publish", daemon=True).start()
        self.root.after(300, poll)

    # ----------------------------------------------------------- automatic
    def _batches_to_publish(self, batch_id: int, queued: bool) -> list[int]:
        ids = [batch_id]
        if queued and getattr(self, "active_queue_id", None) is not None:
            try:
                ids = list(get_queue(self.connection, self.active_queue_id).rename_batch_ids) or ids
            except BatchQueueError:
                pass
        return ids

    def _auto_publish_after_run(self, batch_ids: list[int]) -> None:
        """After a successful run on a WORKER instance with auto-publish on. Never blocks the next batch."""

        try:
            auto, mode = read_publish_settings(self.connection)
        except Exception:  # noqa: BLE001 - never break the run flow
            return
        if not auto:
            return
        publishable = {b for b, _n, _s in unpublished_batches(self.connection)}
        pending = [b for b in batch_ids if b in publishable]
        if not pending:
            return
        self._write_console(f"Publicando {len(pending)} lote(s) en la carpeta compartida…\n")

        def done(result: PublishResult) -> None:
            self._write_console(describe_result(result) + "\n")
            self._set_status(describe_result(result).splitlines()[0])

        self._run_publish_async(pending, mode, done)

    # -------------------------------------------------------------- manual
    def _open_publish_dialog(self) -> None:
        if self._publish_context() is None:
            messagebox.showinfo(t("publish.title"), t("publish.no_exchange"), parent=self.root)
            return
        batches = unpublished_batches(self.connection)
        if not batches:
            messagebox.showinfo(t("publish.title"), t("publish.none"), parent=self.root)
            return
        _auto, default_mode = read_publish_settings(self.connection)
        window = tk.Toplevel(self.root)
        window.title(t("publish.title"))
        window.geometry("620x420")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=t("publish.hint"), wraplength=580, justify="left").grid(row=0, column=0, sticky="w")
        columns = ("id", "name", "status")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        for column, width in zip(columns, (60, 360, 140), strict=True):
            tree.heading(column, text=t(f"publish.col.{column}"))
            tree.column(column, width=width, anchor="w")
        for batch_id, name, status in batches:
            tree.insert("", tk.END, iid=str(batch_id), values=(batch_id, name, status))
        tree.grid(row=1, column=0, sticky="nsew", pady=8)
        tree.selection_set(tree.get_children()[0])
        mode_var = tk.StringVar(value=default_mode)
        options = ttk.Frame(frame)
        options.grid(row=2, column=0, sticky="w")
        ttk.Label(options, text=t("publish.mode")).pack(side=tk.LEFT)
        ttk.Radiobutton(options, text=t("publish.mode_move"), value="MOVE", variable=mode_var).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(options, text=t("publish.mode_copy"), value="COPY", variable=mode_var).pack(side=tk.LEFT)
        status_var = tk.StringVar()
        ttk.Label(frame, textvariable=status_var, wraplength=580, justify="left").grid(row=3, column=0, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e", pady=(10, 0))
        run = ttk.Button(buttons, text=t("publish.run"))

        def _publish() -> None:
            ids = [int(i) for i in tree.selection()]
            if not ids:
                messagebox.showinfo(t("publish.title"), t("publish.nothing_selected"), parent=window)
                return
            run.configure(state="disabled")
            status_var.set("…")

            def done(result: PublishResult) -> None:
                text = describe_result(result)
                self._write_console(text + "\n")
                try:
                    status_var.set(text)
                    run.configure(state="normal")
                    if result.ok:
                        for iid in ids:
                            if tree.exists(str(iid)):
                                tree.delete(str(iid))
                except tk.TclError:
                    pass

            self._run_publish_async(ids, mode_var.get(), done)

        run.configure(command=_publish)
        run.pack(side=tk.RIGHT)
        ttk.Button(buttons, text=t("audit.close"), command=window.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        bind_escape_close(window, on_close=window.destroy)
