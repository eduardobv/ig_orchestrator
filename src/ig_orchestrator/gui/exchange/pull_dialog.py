"""Dialog: pull account folders from another instance into WORKING_FOLDER."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ig_orchestrator.db.instances_repository import InstanceRepository
from ig_orchestrator.exchange import (
    ExchangeFolder,
    ExchangeUnavailableError,
    PullPlan,
    PullPolicy,
    PullResult,
    execute_pull,
    plan_pull,
    scan_exchange,
)
from ig_orchestrator.exchange.compare import (
    compare_with_batch,
    list_recent_batches,
    probe_path,
)
from ig_orchestrator.gui.batch_resume_service import mark_batch_executed_elsewhere
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.shared.helpers import bind_escape_close
from ig_orchestrator.library.audit_cli import native_path_text

STATE_READY = "ready"
STATE_BUSY = "busy"
STATE_EXISTS = "exists"
STATE_EMPTY = "empty"
FREE_PATH = "__free__"


def folder_state(folder: ExchangeFolder, dest_root: Path) -> str:
    """Row state shown in the table (empty > in use > already in destination > ready)."""

    if folder.is_empty:
        return STATE_EMPTY
    if not folder.is_stable:
        return STATE_BUSY
    try:
        exists = any(
            entry.name.casefold() == folder.name.casefold()
            for entry in Path(dest_root).iterdir()
        )
    except OSError:
        exists = False
    return STATE_EXISTS if exists else STATE_READY


def format_mb(total_bytes: int) -> str:
    return f"{total_bytes / (1024 * 1024):.1f}"


class PullDialogMixin:
    """Mixin: Lote -> Traer descargas..."""

    def _open_pull_dialog(self, batch_id: int | None = None) -> None:
        existing = getattr(self, "_pull_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return
            except tk.TclError:
                self._pull_window = None

        dest_root = Path(self.settings.working_folder)
        stable_seconds = float(self.settings.download_stable_seconds) * 3
        instances = InstanceRepository(self.connection).list()
        sources = {i.name: i for i in instances if not i.is_local and i.pull_source}
        batches = list_recent_batches(self.connection)

        window = tk.Toplevel(self.root)
        window.title(t("pull.title"))
        window.geometry("880x560")
        window.minsize(700, 420)
        self._pull_window = window

        state: dict[str, object] = {
            "folders": [],
            "queue": queue.Queue(),
            "cancel": threading.Event(),
            "busy": False,
            "by_item": {},
        }
        instance_var = tk.StringVar(value=next(iter(sources), t("pull.free_path")))
        source_var = tk.StringVar(value=sources[instance_var.get()].pull_source if sources else "")
        keep_var = tk.BooleanVar(value=False)
        batch_choices = [t("pull.no_batch")] + [f"{bid} · {name} ({status})" for bid, name, status in batches]
        batch_var = tk.StringVar(value=batch_choices[0])
        if batch_id is not None:
            for choice, (bid, _n, _s) in zip(batch_choices[1:], batches, strict=True):
                if bid == batch_id:
                    batch_var.set(choice)
        status_var = tk.StringVar()
        compare_var = tk.StringVar()

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text=t("pull.instance")).grid(row=0, column=0, sticky="w")
        instance_box = ttk.Combobox(
            frame,
            textvariable=instance_var,
            values=[*sources, t("pull.free_path")],
            state="readonly",
            width=18,
        )
        instance_box.grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(frame, text=t("pull.source")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frame, textvariable=source_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(6, 0))
        ttk.Button(
            frame, text=t("audit.browse"), command=lambda: _browse_dir(window, source_var)
        ).grid(row=1, column=2, pady=(6, 0))
        ttk.Button(frame, text=t("pull.scan"), command=lambda: _scan()).grid(
            row=1, column=3, padx=(6, 0), pady=(6, 0)
        )

        ttk.Label(frame, text=t("pull.dest")).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(frame, text=str(dest_root)).grid(row=2, column=1, sticky="w", padx=8, pady=(6, 0))
        ttk.Checkbutton(frame, text=t("pull.keep_source"), variable=keep_var).grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(6, 0)
        )

        ttk.Label(frame, text=t("pull.compare")).grid(row=3, column=0, sticky="w", pady=(6, 0))
        batch_box = ttk.Combobox(
            frame, textvariable=batch_var, values=batch_choices, state="readonly", width=48
        )
        batch_box.grid(row=3, column=1, sticky="w", padx=8, pady=(6, 0))

        columns = ("name", "files", "mb", "state")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        for column, width in zip(columns, (260, 80, 90, 200), strict=True):
            tree.heading(column, text=t(f"pull.col.{column}"))
            tree.column(column, width=width, anchor="w")
        tree.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.grid(row=4, column=4, sticky="ns", pady=(8, 0))
        tree.configure(yscrollcommand=scroll.set)

        ttk.Label(frame, textvariable=compare_var, wraplength=820, justify="left").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(6, 0)
        )
        progress = ttk.Progressbar(frame, mode="determinate")
        progress.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        ttk.Label(frame, textvariable=status_var).grid(row=7, column=0, columnspan=4, sticky="w")

        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        pull_selected = ttk.Button(actions, text=t("pull.pull_selected"))
        pull_selected.pack(side=tk.LEFT)
        pull_all = ttk.Button(actions, text=t("pull.pull_all"))
        pull_all.pack(side=tk.LEFT, padx=8)
        cancel_button = ttk.Button(actions, text=t("pull.cancel"), state="disabled")
        cancel_button.pack(side=tk.LEFT)
        ttk.Button(actions, text=t("audit.close"), command=lambda: _close()).pack(side=tk.RIGHT)

        def selected_batch_id() -> int | None:
            index = batch_choices.index(batch_var.get()) if batch_var.get() in batch_choices else 0
            return batches[index - 1][0] if index > 0 else None

        def set_busy(busy: bool) -> None:
            state["busy"] = busy
            normal = "disabled" if busy else "normal"
            pull_selected.configure(state=normal)
            pull_all.configure(state=normal)
            cancel_button.configure(state="normal" if busy else "disabled")

        def on_instance(_event: object = None) -> None:
            chosen = sources.get(instance_var.get())
            if chosen is not None:
                source_var.set(chosen.pull_source)

        instance_box.bind("<<ComboboxSelected>>", on_instance)

        def refresh_table() -> None:
            tree.delete(*tree.get_children())
            by_item: dict[str, ExchangeFolder] = {}
            for folder in state["folders"]:
                item = tree.insert(
                    "",
                    tk.END,
                    values=(
                        folder.name,
                        folder.file_count,
                        format_mb(folder.total_bytes),
                        t(f"pull.state.{folder_state(folder, dest_root)}"),
                    ),
                )
                by_item[item] = folder
            state["by_item"] = by_item
            refresh_compare()

        def refresh_compare() -> None:
            bid = selected_batch_id()
            if bid is None:
                compare_var.set("")
                return
            names = [f.name for f in state["folders"] if not f.is_empty]
            result = compare_with_batch(self.connection, bid, names)
            compare_var.set(
                t(
                    "pull.compare_result",
                    received=len(result.received),
                    total=len(result.received) + len(result.missing),
                    missing=", ".join(result.missing) or "-",
                    extra=", ".join(result.extra) or "-",
                )
            )

        batch_box.bind("<<ComboboxSelected>>", lambda _e: refresh_compare())

        def _scan() -> None:
            source = native_path_text(source_var.get())
            if not source:
                messagebox.showerror(t("pull.title"), t("pull.source_required"), parent=window)
                return
            source_var.set(source)
            status_var.set(t("pull.scanning"))
            set_busy(True)

            def work() -> None:
                try:
                    folders = scan_exchange(Path(source), stable_seconds=stable_seconds)
                    state["queue"].put(("scanned", folders))
                except ExchangeUnavailableError as exc:
                    state["queue"].put(("error", str(exc)))
                except Exception as exc:  # noqa: BLE001 - shown to the user
                    state["queue"].put(("error", str(exc)))

            threading.Thread(target=work, name="pull-scan", daemon=True).start()
            window.after(150, poll)

        def start_pull(only_ready: bool) -> None:
            by_item: dict[str, ExchangeFolder] = state["by_item"]
            if only_ready:
                chosen = [
                    f
                    for f in by_item.values()
                    if folder_state(f, dest_root) in (STATE_READY, STATE_EXISTS)
                ]
            else:
                chosen = [by_item[i] for i in tree.selection() if i in by_item]
            if not chosen:
                messagebox.showinfo(t("pull.title"), t("pull.nothing_selected"), parent=window)
                return
            busy = [f.name for f in chosen if not f.is_stable]
            if busy and not messagebox.askyesno(
                t("pull.title"), t("pull.busy_confirm", names=", ".join(busy)), parent=window
            ):
                return
            plan = plan_pull(
                chosen, dest_root, PullPolicy.MERGE_SKIP_IDENTICAL, keep_source=keep_var.get()
            )
            if not plan.has_enough_space:
                messagebox.showerror(
                    t("pull.title"),
                    t("pull.no_space", need=format_mb(plan.required_bytes), free=format_mb(plan.free_bytes or 0)),
                    parent=window,
                )
                return
            state["cancel"].clear()
            set_busy(True)
            progress.configure(value=0, maximum=max(1, sum(len(p.files) for p in plan.folders)))
            counter = {"done": 0}

            def on_progress(folder: str, _done: int, _total: int) -> None:
                counter["done"] += 1
                state["queue"].put(("progress", (folder, counter["done"])))

            def work() -> None:
                try:
                    result = execute_pull(plan, progress=on_progress, cancel_event=state["cancel"])
                    state["queue"].put(("pulled", (plan, result)))
                except Exception as exc:  # noqa: BLE001 - shown to the user
                    state["queue"].put(("error", str(exc)))

            threading.Thread(target=work, name="pull-run", daemon=True).start()
            window.after(150, poll)

        pull_selected.configure(command=lambda: start_pull(False))
        pull_all.configure(command=lambda: start_pull(True))
        cancel_button.configure(command=lambda: state["cancel"].set())

        def poll() -> None:
            try:
                while True:
                    kind, payload = state["queue"].get_nowait()
                    if kind == "progress":
                        folder, done = payload
                        progress.configure(value=done)
                        status_var.set(t("pull.pulling", folder=folder))
                        continue
                    if kind == "scanned":
                        state["folders"] = payload
                        refresh_table()
                        status_var.set(t("pull.scanned", count=len(payload)))
                        set_busy(False)
                    elif kind == "error":
                        status_var.set(payload)
                        set_busy(False)
                        messagebox.showerror(t("pull.title"), payload, parent=window)
                    elif kind == "pulled":
                        plan, result = payload
                        set_busy(False)
                        self._finish_pull(window, plan, result, selected_batch_id(), status_var)
                        _scan_again()
                    return
            except queue.Empty:
                pass
            if state["busy"]:
                window.after(150, poll)

        def _scan_again() -> None:
            if source_var.get().strip():
                _scan()

        def _close() -> None:
            if state["busy"]:
                state["cancel"].set()
            self._pull_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close)
        bind_escape_close(window, on_close=_close)
        if source_var.get().strip():
            window.after(100, _scan)

    def _offer_pull_before_rename(self) -> bool:
        """Ask to pull first when WORKING is empty but an instance has stable folders.

        Returns True when the user chose to pull (the rename is then postponed).
        """

        working = Path(self.settings.working_folder)
        try:
            if any(entry.is_dir() for entry in working.iterdir()):
                return False
        except OSError:
            return False
        stable_seconds = float(self.settings.download_stable_seconds) * 3
        for instance in InstanceRepository(self.connection).list():
            if instance.is_local or not instance.pull_source:
                continue
            if not probe_path(instance.pull_source, timeout=3.0, check_write=False).ok:
                continue
            try:
                folders = scan_exchange(Path(instance.pull_source), stable_seconds=stable_seconds)
            except ExchangeUnavailableError:
                continue
            if any(f.is_stable and not f.is_empty for f in folders):
                if messagebox.askyesno(
                    t("pull.title"),
                    t("pull.rename_hint", instance=instance.name),
                    parent=self.root,
                ):
                    self._open_pull_dialog(getattr(self, "active_batch_id", None))
                    return True
                return False
        return False

    def _finish_pull(
        self,
        window: tk.Toplevel,
        plan: PullPlan,
        result: PullResult,
        batch_id: int | None,
        status_var: tk.StringVar,
    ) -> None:
        lines = []
        for folder in result.folders:
            if folder.blocked_reason:
                lines.append(f"{folder.name}: {folder.blocked_reason}")
                continue
            lines.append(
                f"{folder.name}: {folder.copied} copiados, {folder.skipped_identical} omitidos, "
                f"{folder.renamed} con sufijo, {len(folder.errors)} errores"
            )
            lines.extend(f"    ! {error}" for error in folder.errors)
        if result.cancelled:
            lines.append("CANCELADO: lo no procesado sigue en el origen.")
        body = "Traer descargas:\n" + "\n".join(lines) + "\n"
        self._write_console(body)
        status_var.set(t("pull.done_cancelled") if result.cancelled else t("pull.done"))
        if result.ok and batch_id is not None:
            if messagebox.askyesno(t("pull.title"), t("pull.offer_mark", batch=batch_id), parent=window):
                try:
                    mark_batch_executed_elsewhere(self.connection, batch_id)
                except ValueError as exc:
                    messagebox.showerror(t("pull.title"), str(exc), parent=window)
                else:
                    self._write_console(
                        f"Batch {batch_id} marcado como AWAITING_RENAME (ejecutado en otra instancia).\n"
                    )
                    self._update_pending_button_label()
                    messagebox.showinfo(t("pull.title"), t("pull.ready_to_rename"), parent=window)
        elif not result.ok:
            messagebox.showwarning(t("pull.title"), body, parent=window)


def _browse_dir(parent: tk.Misc, variable: tk.StringVar) -> None:
    chosen = filedialog.askdirectory(parent=parent, initialdir=variable.get() or None)
    if chosen:
        variable.set(native_path_text(chosen))

