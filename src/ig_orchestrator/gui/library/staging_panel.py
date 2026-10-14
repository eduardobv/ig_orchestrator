"""Panel "Pendiente de volcar": renamed accounts waiting in the staging area and the dump into the library."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from sqlite3 import Connection
from tkinter import messagebox, ttk

from ig_orchestrator.db import connect
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.staging import StagingService
from ig_orchestrator.staging.service import DumpResult

KIND_LABELS = {"NUEVA": "staging.kind.new", "FUSIONAR": "staging.kind.merge", "CONFLICTO": "staging.kind.conflict", "FALTA": "staging.kind.missing"}


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def staging_status_text(connection: Connection) -> str:
    """One line for the status bar / menu: ``'14 cuentas · 3.2 GB pendientes'`` or ``''``."""

    try:
        accounts, _files, size = StagingService(connection).summary()
    except Exception:  # noqa: BLE001 - v1 database or no staging yet
        return ""
    return t("staging.status", accounts=accounts, size=human_size(size)) if accounts else ""


class StagingPanelMixin:
    def _refresh_staging_hint(self) -> None:
        """Status-bar text ``Almacen: N cuenta(s) · size pendientes · G: desconectada`` (empty when nothing waits)."""

        hint = staging_status_text(self.connection)
        if hint:
            try:
                online = StagingService(self.connection).fs.is_online()
            except Exception:  # noqa: BLE001
                online = False
            hint += "" if online else " · " + t("staging.hint_offline")
            if online and not getattr(self, "_staging_offered", False):
                self._staging_offered = True
                self._write_console(t("staging.hint_ready") + "\n")
        self._staging_hint = hint
        self._set_status(self.status_var.get())

    def _open_staging_panel(self) -> None:
        connection: Connection = self.connection
        service = StagingService(connection)
        try:
            service.staging_root()
        except ValueError as exc:
            messagebox.showinfo(t("staging.title"), str(exc), parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title(t("staging.title"))
        window.geometry("980x520")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        info = tk.StringVar()
        ttk.Label(frame, textvariable=info, wraplength=920, justify="left").pack(anchor="w")
        columns = ("files", "size", "kind", "status", "target")
        tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="extended")
        tree.heading("#0", text=t("staging.col.account"))
        tree.column("#0", width=200)
        for column, width in zip(columns, (70, 90, 110, 100, 360), strict=True):
            tree.heading(column, text=t(f"staging.col.{column}"))
            tree.column(column, width=width, anchor="w")
        tree.pack(fill=tk.BOTH, expand=True, pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)
        items: dict[str, object] = {}

        def refresh() -> None:
            tree.delete(*tree.get_children())
            items.clear()
            online = service.fs.is_online()
            plan = service.plan()
            for item in plan:
                iid = str(item.staged_id)
                items[iid] = item
                kind = t(KIND_LABELS.get(item.kind, "staging.kind.new"))
                tree.insert("", tk.END, iid=iid, text="@" + item.username,
                            values=(item.files, human_size(item.bytes), kind, item.status, item.detail or item.target_path))
            accounts, files, size = service.summary()
            info.set(t("staging.info", accounts=accounts, files=files, size=human_size(size),
                       library=t("staging.library_on") if online else t("staging.library_off")))

        def start(selected_only: bool) -> None:
            ids = [int(i) for i in tree.selection()] if selected_only else None
            if selected_only and not ids:
                return
            if not service.fs.is_online():
                messagebox.showwarning(t("staging.title"), t("staging.offline"), parent=window)
                return
            plan = [i for i in items.values() if ids is None or i.staged_id in ids]
            summary = t("staging.confirm", accounts=len(plan), merge=sum(i.kind == "FUSIONAR" for i in plan),
                        new=sum(i.kind == "NUEVA" for i in plan), conflict=sum(i.kind == "CONFLICTO" for i in plan))
            if not plan or not messagebox.askyesno(t("staging.title"), summary, parent=window):
                return
            self._run_dump(window, ids, refresh)

        ttk.Button(buttons, text=t("staging.refresh"), command=refresh).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("staging.dump_selected"), command=lambda: start(True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text=t("staging.dump_all"), command=lambda: start(False)).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("staging.forget"), command=lambda: (service.forget_dumped(), refresh())).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text=t("plan.cancel"), command=window.destroy).pack(side=tk.RIGHT)
        bind_escape_close(window, on_close=window.destroy)
        refresh()

    def _run_dump(self, window: tk.Toplevel, ids: list[int] | None, on_done) -> None:
        gui_db = Path(self.settings.sqlite_gui_db_path)
        results: queue.Queue = queue.Queue()
        self._set_status(t("staging.running"))

        def work() -> None:
            try:
                conn = connect(gui_db)
                try:
                    results.put(("done", StagingService(conn).dump(
                        ids, progress=lambda i, n, name: results.put(("progress", f"[{i}/{n}] @{name}")))))
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001 - shown to the user
                results.put(("error", f"{type(exc).__name__}: {exc}"))

        def poll() -> None:
            try:
                while True:
                    kind, payload = results.get_nowait()
                    if kind == "progress":
                        self._write_console(payload + "\n")
                        continue
                    if kind == "error":
                        messagebox.showerror(t("staging.title"), payload, parent=window)
                    else:
                        result: DumpResult = payload
                        self._write_console(result.summary() + "\n")
                        self._refresh_staging_hint()
                        for outcome in result.problems:
                            self._write_console(f"  @{outcome.username}: {outcome.status} - {outcome.detail}\n")
                        self._reload_catalog()
                        (messagebox.showwarning if result.problems else messagebox.showinfo)(
                            t("staging.title"), result.summary(), parent=window)
                    self._set_status(t("staging.done"))
                    on_done()
                    return
            except queue.Empty:
                pass
            self.root.after(200, poll)

        threading.Thread(target=work, name="staging-dump", daemon=True).start()
        self.root.after(200, poll)
