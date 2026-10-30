"""Dialog: check which accounts of a folder still exist on Instagram, then move them (feat-uc2-26)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from ig_orchestrator.account_status.checker import profile_url
from ig_orchestrator.account_status.service import (
    RUN_COMPLETED,
    RUN_RATE_LIMITED,
    RUN_RUNNING,
    AccountStatusService,
    CheckResult,
    CheckRun,
    reuse_hours,
    run_checks,
)
from ig_orchestrator.db import connect
from ig_orchestrator.gui.i18n import t
from ig_orchestrator.gui.library.folder_picker import pick_folder
from ig_orchestrator.gui.library.fsops_actions import STATUS_TEXT
from ig_orchestrator.gui.library.plan_dialog import confirm_plan
from ig_orchestrator.gui.shared.helpers import _open_path_in_explorer, bind_escape_close
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.compat_lite import lite_path_from_settings, mirror_to_lite
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.orchestration.run_settings import load_run_settings

ICONS = {"AVAILABLE": "✔", "UNAVAILABLE": "✘", "UNKNOWN": "?", "PENDING": "…"}
COLUMNS = ("username", "status", "checked", "moved", "destination", "path")
FILTERS = ("all", "AVAILABLE", "UNAVAILABLE", "UNKNOWN", "PENDING", "MOVED")
MOVED_FLAG = "MOVED"


def run_label(run: CheckRun) -> str:
    return (
        f"#{run.id} · {run.folder_rel or '/'} · {run.created_at[:16].replace('T', ' ')}"
        f" · {t('acs.state.' + run.state)} · {run.total}"
    )


def sort_key(column: str, result: CheckResult):
    if column == "username":
        return result.username.lower()
    if column == "status":
        return result.status
    if column == "checked":
        return result.checked_at or ""
    if column == "moved":
        return int(result.moved)
    if column == "destination":
        return result.destination.lower()
    return result.rel_path.lower()


def checked_text(result: CheckResult) -> str:
    if not result.checked_at:
        return ""
    text = result.checked_at[:16].replace("T", " ")
    return f"{text} (#{result.source_run_id})" if result.reused else text


def movable_ids(results, *, only_status: str | None = None) -> list[int]:
    """Catalog account ids that can still be moved: known account and not moved already."""

    return [
        r.account_id
        for r in results
        if r.account_id and not r.moved and (only_status is None or r.status == only_status)
    ]


class AccountStatusMixin:
    """Folder menu → «Comprobar estado de las cuentas…»; Catálogo → «Revisar análisis de estado…»."""

    def _catalog_check_accounts(self) -> None:
        folder_id = self._selected_catalog_folder_id()
        if folder_id is not None:
            self._open_account_status(folder_id)

    def _review_account_status(self) -> None:
        if not AccountStatusService(self.connection).runs():
            messagebox.showinfo(t("acs.review"), t("acs.no_saved"), parent=self.root)
            return
        self._open_account_status(None)

    def _open_account_status(self, folder_id: int | None) -> None:
        existing = getattr(self, "_account_status_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    if existing.acs_busy():
                        existing.deiconify()
                        existing.lift()
                        return
                    existing.destroy()
            except tk.TclError:
                pass
            self._account_status_window = None

        service = AccountStatusService(self.connection)
        service.recover_interrupted()
        folder_rel = self._fsops_service().folder(folder_id).rel_path if folder_id is not None else ""
        title = t("acs.title", folder=folder_rel or "/") if folder_id is not None else t("acs.title_all")
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("1050x580")
        window.minsize(760, 400)
        self._account_status_window = window

        state: dict = {
            "run": None, "results": {}, "queue": queue.Queue(), "thread": None, "busy": False,
            "stop": threading.Event(), "sort": ("username", False), "runs": [],
        }
        run_var = tk.StringVar()
        filter_var = tk.StringVar(value=t("acs.filter.all"))
        info_var = tk.StringVar()
        selected_var = tk.StringVar(value=t("acs.selected", n=0))
        force_var = tk.BooleanVar(value=False)

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=t("acs.analysis")).grid(row=0, column=0, padx=(0, 6))
        run_box = ttk.Combobox(top, textvariable=run_var, state="readonly")
        run_box.grid(row=0, column=1, sticky="ew")
        new_button = ttk.Button(top, text=t("acs.new"))
        new_button.grid(row=0, column=2, padx=(6, 0))
        delete_button = ttk.Button(top, text=t("acs.delete"))
        delete_button.grid(row=0, column=3, padx=(6, 0))

        progress = ttk.Progressbar(frame, mode="determinate")
        progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        info_row = ttk.Frame(frame)
        info_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(info_row, textvariable=info_var).pack(side=tk.LEFT)
        filter_box = ttk.Combobox(
            info_row, textvariable=filter_var, state="readonly", width=18,
            values=[t(f"acs.filter.{name}") for name in FILTERS],
        )
        filter_box.pack(side=tk.RIGHT)
        ttk.Label(info_row, text=t("acs.filter")).pack(side=tk.RIGHT, padx=(0, 4))
        ttk.Label(info_row, textvariable=selected_var, font=("Segoe UI", 9, "bold")).pack(
            side=tk.RIGHT, padx=(0, 16)
        )

        tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", selectmode="extended")
        for column, width in zip(COLUMNS, (150, 60, 170, 70, 230, 330), strict=True):
            tree.column(column, width=width, anchor="center" if column in ("status", "moved") else "w")
        tree.tag_configure("moved", foreground="#c0392b")
        tree.grid(row=3, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.grid(row=3, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        start_button = ttk.Button(actions, text=t("acs.start"))
        start_button.pack(side=tk.LEFT)
        stop_button = ttk.Button(actions, text=t("acs.stop"), state="disabled")
        stop_button.pack(side=tk.LEFT, padx=6)
        force_check = ttk.Checkbutton(actions, text=t("acs.force"), variable=force_var, state="disabled")
        force_check.pack(side=tk.LEFT)
        select_button = ttk.Button(actions, text=t("acs.select_all"))
        select_button.pack(side=tk.LEFT, padx=(12, 0))
        move_button = ttk.Button(actions, text=t("acs.move"))
        move_button.pack(side=tk.LEFT, padx=6)
        move_gone_button = ttk.Button(actions, text=t("acs.move_disabled"))
        move_gone_button.pack(side=tk.LEFT)
        ttk.Button(actions, text=t("acs.close"), command=lambda: on_close()).pack(side=tk.RIGHT)

        # ------------------------------------------------------------- helpers
        def current_run() -> CheckRun | None:
            return state["run"]

        def is_running() -> bool:
            thread = state["thread"]
            return thread is not None and thread.is_alive()

        def is_busy() -> bool:
            return is_running() or state["busy"]

        window.acs_busy = is_busy  # type: ignore[attr-defined]

        def visible(result: CheckResult) -> bool:
            wanted = FILTERS[[t(f"acs.filter.{n}") for n in FILTERS].index(filter_var.get())]
            if wanted == "all":
                return True
            if wanted == MOVED_FLAG:
                return result.moved
            return result.status == wanted

        def row_values(result: CheckResult) -> tuple[str, str, str, str, str, str]:
            return (
                result.username, ICONS.get(result.status, "?"), checked_text(result),
                MOVED_FLAG if result.moved else "", result.destination, result.rel_path,
            )

        def row_tags(result: CheckResult) -> tuple[str, ...]:
            return ("moved",) if result.moved else ()

        def update_info() -> None:
            run = current_run()
            if run is None:
                info_var.set(t("acs.no_run"))
                progress.configure(maximum=1, value=0)
                return
            results = list(state["results"].values())
            pending = sum(1 for r in results if r.status in ("PENDING", "UNKNOWN"))
            progress.configure(maximum=max(run.total, 1), value=run.total - pending)
            run_state = RUN_RUNNING if is_running() else service.run(run.id).state
            info_var.set(
                t("acs.summary", done=run.total - pending, total=run.total,
                  ok=sum(1 for r in results if r.status == "AVAILABLE"),
                  gone=sum(1 for r in results if r.status == "UNAVAILABLE"),
                  unknown=sum(1 for r in results if r.status == "UNKNOWN"),
                  moved=sum(1 for r in results if r.moved), reused=sum(1 for r in results if r.reused))
                + "  ·  " + t("acs.state." + run_state)
            )

        def update_selected(_event=None) -> None:
            chosen = tree.selection()
            blocked = [i for i in chosen if state["results"][int(i)].moved]
            if blocked:  # moved accounts cannot be selected: they are no longer where the analysis found them
                tree.selection_remove(*blocked)
                chosen = tree.selection()
            selected_var.set(t("acs.selected", n=len(chosen)))

        def fill_tree() -> None:
            tree.delete(*tree.get_children())
            column, reverse = state["sort"]
            ordered = sorted(
                (r for r in state["results"].values() if visible(r)),
                key=lambda r: sort_key(column, r), reverse=reverse,
            )
            for result in ordered:
                tree.insert("", tk.END, iid=str(result.id), values=row_values(result), tags=row_tags(result))
            for name in COLUMNS:
                arrow = (" ▼" if reverse else " ▲") if name == column else ""
                tree.heading(name, text=t(f"acs.col.{name}") + arrow, command=lambda c=name: sort_by(c))
            update_selected()

        def sort_by(column: str) -> None:
            current, reverse = state["sort"]
            state["sort"] = (column, not reverse if current == column else False)
            fill_tree()

        def load_run(run: CheckRun | None) -> None:
            state["run"] = run
            state["results"] = {r.id: r for r in service.results(run.id)} if run is not None else {}
            fill_tree()
            update_info()
            set_buttons()

        def reload_runs(select_id: int | None = None) -> None:
            runs = service.runs(folder_id)
            state["runs"] = runs
            run_box.configure(values=[run_label(r) for r in runs])
            chosen = next((r for r in runs if r.id == select_id), runs[0] if runs else None)
            run_var.set(run_label(chosen) if chosen else "")
            load_run(chosen)

        def set_buttons() -> None:
            running, busy = is_running(), state["busy"]
            idle = not running and not busy
            run = current_run()
            reused = any(r.reused for r in state["results"].values())
            force_check.configure(state="normal" if reused and idle else "disabled")
            if not reused:
                force_var.set(False)
            can_start = run is not None and idle and (run.state != RUN_COMPLETED or force_var.get())
            started = any(r.status != "PENDING" for r in state["results"].values())
            start_button.configure(
                state="normal" if can_start else "disabled",
                text=t("acs.resume") if started else t("acs.start"),
            )
            stop_button.configure(state="normal" if running else "disabled")
            for button in (move_button, move_gone_button, select_button, delete_button):
                button.configure(state="normal" if run is not None and idle else "disabled")
            new_button.configure(state="normal" if idle and folder_id is not None else "disabled")
            run_box.configure(state="readonly" if idle else "disabled")

        def set_busy(flag: bool, text: str = "") -> None:
            state["busy"] = flag
            window.configure(cursor="watch" if flag else "")
            if flag:
                info_var.set(text)
                progress.configure(mode="indeterminate")
                progress.start(12)
            else:
                progress.stop()
                progress.configure(mode="determinate")
                update_info()
            set_buttons()

        def run_job(label: str, work: Callable, done: Callable[[bool, object], None]) -> None:
            """Run ``work(connection)`` off the Tk thread (own connection), then ``done(ok, result)``."""

            set_busy(True, label)
            out: queue.Queue = queue.Queue()
            db_path = self.settings.sqlite_gui_db_path

            def target() -> None:
                connection = connect(db_path)
                try:
                    out.put((True, work(connection)))
                except Exception as exc:  # reported to the user by ``done``
                    out.put((False, exc))
                finally:
                    connection.close()

            threading.Thread(target=target, name="account-status-job", daemon=True).start()

            def check() -> None:
                try:
                    ok, payload = out.get_nowait()
                except queue.Empty:
                    window.after(100, check)
                    return
                set_busy(False)
                done(ok, payload)

            window.after(100, check)

        # ------------------------------------------------------------- actions
        def on_pick_run(_event=None) -> None:
            index = run_box.current()
            if 0 <= index < len(state["runs"]) and not is_busy():
                load_run(state["runs"][index])

        def new_run() -> None:
            if folder_id is None:
                return
            hours = reuse_hours(self.connection)
            created = service.create_run(folder_id, reuse_hours=hours)
            if created.total == 0:
                service.delete_run(created.id)
                messagebox.showinfo(title, t("acs.empty_folder"), parent=window)
                return
            reload_runs(created.id)
            reused = sum(1 for r in state["results"].values() if r.reused)
            if reused:
                messagebox.showinfo(title, t("acs.reused_info", n=reused, total=created.total, hours=hours), parent=window)

        def delete_run() -> None:
            run = current_run()
            if run is None or not messagebox.askyesno(
                t("acs.delete"), t("acs.delete_confirm", id=run.id), parent=window
            ):
                return
            service.delete_run(run.id)
            reload_runs()

        def start() -> None:
            run = current_run()
            if run is None or is_busy():
                return
            if force_var.get():
                service.force_reanalysis(run.id)
                force_var.set(False)
                load_run(service.run(run.id))
                run = current_run()
            options = load_run_settings(self.connection, self.settings)
            state["stop"] = stop_event = threading.Event()
            db_path = self.settings.sqlite_gui_db_path
            out: queue.Queue = state["queue"]

            def work() -> None:
                connection = connect(db_path)
                try:
                    final = run_checks(
                        AccountStatusService(connection), run.id,
                        interval_seconds=options.accountcheck_interval_seconds,
                        timeout_seconds=options.accountcheck_timeout_seconds,
                        stop=stop_event, on_result=lambda r: out.put(("result", r)),
                    )
                    out.put(("done", final))
                except Exception as exc:  # shown to the user in the dialog
                    out.put(("error", exc))
                finally:
                    connection.close()

            thread = threading.Thread(target=work, name="account-status-check", daemon=True)
            state["thread"] = thread
            thread.start()
            set_buttons()
            window.after(200, poll)

        def stop() -> None:
            state["stop"].set()
            stop_button.configure(state="disabled")

        def poll() -> None:
            finished = None
            try:
                while True:
                    kind, payload = state["queue"].get_nowait()
                    if kind == "result":
                        state["results"][payload.id] = payload
                        if tree.exists(str(payload.id)):
                            tree.item(str(payload.id), values=row_values(payload), tags=row_tags(payload))
                        elif visible(payload):
                            fill_tree()
                        update_info()
                    else:
                        finished = (kind, payload)
            except queue.Empty:
                pass
            if finished is None:
                if is_running():
                    window.after(200, poll)
                    return
                finished = ("done", None)
            thread = state["thread"]
            if thread is not None:
                thread.join(2)  # the worker closes its connection right after reporting
            run = current_run()
            if run is not None:
                reload_runs(run.id)
            if finished[0] == "error":
                messagebox.showerror(title, str(finished[1]), parent=window)
            elif finished[1] == RUN_RATE_LIMITED:
                messagebox.showwarning(title, t("acs.rate_limited"), parent=window)
            elif finished[1] == RUN_COMPLETED:
                messagebox.showinfo(title, t("acs.completed"), parent=window)

        def select_all() -> None:
            tree.selection_set([i for i in tree.get_children() if not state["results"][int(i)].moved])
            update_selected()

        def move_accounts(account_ids: list[int]) -> None:
            """Pick a destination, plan and run the move without freezing the window.

            Planning touches the library disk for every account, so it runs in a worker with a
            «preparing» status; the preview is parented to this window so it cannot hide behind it.
            """

            if not account_ids or not self._fsops_guard():
                return
            dest = pick_folder(window, self.connection, t("fsops.move_to"), account_ids=account_ids)
            if dest is None:
                return

            def plan_work(connection):
                fs = FsOperationService(connection)
                plan = fs.plan_move_accounts(account_ids, dest)
                changes = AccountLifecycleService(connection, fs=fs).preview_status_changes(plan)
                extra = [(t("plan.status_change"), "@" + name, t(STATUS_TEXT[kind])) for _i, name, kind in changes]
                return plan, extra

            def planned(ok: bool, payload) -> None:
                if not ok:
                    messagebox.showerror(t("plan.title"), str(payload), parent=window)
                    return
                plan, extra = payload
                if not confirm_plan(window, plan, extra_rows=extra or None):
                    return

                def exec_work(connection):
                    fs = FsOperationService(connection)
                    group = fs.execute(plan)
                    lifecycle = AccountLifecycleService(connection, fs=fs)
                    messages = lifecycle.sync_with_location(lifecycle.affected_accounts(group), group)
                    try:
                        lite = lite_path_from_settings(connection)
                        if lite is not None:
                            changed = mirror_to_lite(connection, lite, fs.root)
                            if changed:
                                messages.append(f"accounts_lite actualizada ({changed} filas).")
                    except Exception as exc:  # noqa: BLE001 - lite offline must not fail the move
                        messages.append(f"accounts_lite pendiente de actualizar ({exc}).")
                    return messages

                def executed(ok2: bool, result) -> None:
                    if not ok2:
                        messagebox.showerror(t("plan.title"), str(result), parent=window)
                    else:
                        for message in result:
                            self._write_console(message + "\n")
                        self._write_console(f"{plan.title}: OK\n")
                        self._set_status(plan.title)
                    self.destination_paths = self.catalog_service.list_destination_paths()
                    self._reload_catalog()
                    self._refresh_editor_catalog_fields()
                    run = current_run()
                    if run is not None:
                        load_run(service.run(run.id))

                run_job(t("acs.moving", n=len(account_ids)), exec_work, executed)

            run_job(t("acs.preparing", n=len(account_ids)), plan_work, planned)

        def move_selected() -> None:
            ids = [int(i) for i in tree.selection()]
            account_ids = movable_ids(state["results"][i] for i in ids)
            if not account_ids:
                messagebox.showinfo(t("acs.move"), t("acs.select_first"), parent=window)
                return
            move_accounts(account_ids)

        def move_disabled() -> None:
            results = list(state["results"].values())
            account_ids = movable_ids(results, only_status="UNAVAILABLE")
            if not account_ids:
                messagebox.showinfo(t("acs.move_disabled"), t("acs.none_disabled"), parent=window)
                return
            wanted = set(account_ids)
            rows = [str(r.id) for r in results if r.account_id in wanted and tree.exists(str(r.id))]
            tree.selection_set(rows)  # what the user would have selected by hand
            update_selected()
            move_accounts(account_ids)

        def clicked_result(event) -> CheckResult | None:
            row = tree.identify_row(event.y)
            if not row:
                return None
            result = state["results"].get(int(row))
            if result is not None and not result.moved and row not in tree.selection():
                tree.selection_set(row)
            return result

        def open_browser(result: CheckResult) -> None:
            webbrowser.open(profile_url(result.username))

        def open_explorer(result: CheckResult) -> None:
            try:
                where = result.destination if result.moved else result.rel_path
                _open_path_in_explorer(Path(self._fsops_service().abs(where)))
            except Exception as exc:  # offline library, folder gone, no LIBRARY root
                messagebox.showerror(t("acs.open_explorer"), str(exc), parent=window)

        def show_menu(event) -> None:
            result = clicked_result(event)
            if result is None:
                return
            menu = tk.Menu(window, tearoff=False)
            menu.add_command(label=t("acs.open_browser"), command=lambda: open_browser(result))
            menu.add_command(label=t("acs.open_explorer"), command=lambda: open_explorer(result))
            menu.tk_popup(event.x_root, event.y_root)

        def on_double_click(event) -> None:
            if tree.identify_region(event.x, event.y) != "cell":  # not on headings or separators
                return
            result = state["results"].get(int(tree.identify_row(event.y) or 0))
            if result is not None:
                open_browser(result)

        def on_close() -> None:
            if state["busy"]:
                messagebox.showinfo(t("acs.close"), t("acs.close_busy"), parent=window)
                return
            if is_running():
                if not messagebox.askyesno(t("acs.close"), t("acs.close_running"), parent=window):
                    return
                state["stop"].set()
            self._account_status_window = None
            window.destroy()

        run_box.bind("<<ComboboxSelected>>", on_pick_run)
        filter_box.bind("<<ComboboxSelected>>", lambda _e: fill_tree())
        tree.bind("<<TreeviewSelect>>", update_selected)
        tree.bind("<Button-3>", show_menu)
        tree.bind("<Double-1>", on_double_click)
        new_button.configure(command=new_run)
        force_check.configure(command=set_buttons)
        delete_button.configure(command=delete_run)
        start_button.configure(command=start)
        stop_button.configure(command=stop)
        select_button.configure(command=select_all)
        move_button.configure(command=move_selected)
        move_gone_button.configure(command=move_disabled)
        window.protocol("WM_DELETE_WINDOW", on_close)
        bind_escape_close(window, on_close=on_close)
        reload_runs()
        if current_run() is None and folder_id is not None:
            new_run()


__all__ = ["AccountStatusMixin", "movable_ids"]
