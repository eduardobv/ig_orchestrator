from __future__ import annotations

import dataclasses
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from sqlite3 import IntegrityError
import tkinter as tk
from tkinter import font as tkfont
from tkinter import colorchooser, filedialog, messagebox, ttk

from ig_orchestrator import __version__
from ig_orchestrator.db.downloaded_files_cleanup import purge_downloaded_files
from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogService,
    filter_catalog_entries,
    list_usernames_active_on_date,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    inspect_account_draft,
    normalize_url_lines,
    save_catalog_metadata_to_history,
    save_new_account_to_catalog,
    save_batch_draft,
)
from ig_orchestrator.gui.batch_queue_service import (
    BatchQueueError,
    QueueStatus,
    add_batches_to_open_queue,
    collect_queue_rename_parameters,
    collect_rename_parameters,
    finish_queue_after_rename,
    get_open_queue,
    get_queue,
    mark_current_item_completed,
    move_queue_item,
    pause_queue,
    remove_queue_item,
    start_or_resume_queue,
)
from ig_orchestrator.gui.batch_resume_service import (
    AccountRuntimeProgress,
    ProblemUrlKind,
    activate_draft_batch,
    complete_account_manually,
    delete_draft_batch,
    fail_account_manually,
    finish_batch,
    get_account_runtime_progress,
    is_batch_ready_for_rename,
    list_account_problem_urls,
    list_historical_batches,
    list_managed_batches,
    load_batch_draft,
    mark_batch_executed_elsewhere,
    mark_batch_interrupted,
    resolve_account_download_folder,
)
from ig_orchestrator.gui.batch_transfer_service import (
    BatchTransferError,
    export_batch_to_path,
    import_batch_from_path,
)
from ig_orchestrator.http_fallback.manual import (
    estimate_http_duration,
    format_http_duration,
    list_http_candidate_ids,
    run_manual_http_download,
)
from ig_orchestrator.orchestration.run_settings import load_run_settings
from ig_orchestrator.gui.catalog_colors import load_catalog_colors, save_color
from ig_orchestrator.gui.catalog_tree import build_catalog_tree
from ig_orchestrator.gui.i18n import current_language, t
from ig_orchestrator.gui.process_runner import (
    build_manual_rename_command,
    build_run_continue_command,
    format_manual_rename_command_preview,
)
from ig_orchestrator.gui.rename_folder_status import (
    decide_rename_completion,
    list_unmoved_account_folders,
)
from ig_orchestrator.gui.shared.helpers import (
    _ACCOUNT_PROGRESS_RE,
    _BATCH_COLUMNS,
    _CATALOG_COLORS,
    _ITEM_PROGRESS_RE,
    _account_display_status,
    _batch_column_samples,
    _batch_mode_details,
    _catalog_entry_colors,
    _draft_signature,
    _gui_setting,
    _instagram_profile_url,
    _new_account_rename_parameters,
    _open_chrome_tab,
    _open_path_in_explorer,
    _play_completion_sound,
    _send_test_telegram,
    _set_ttk_enabled,
    _sort_accounts_by_username,
    _suggest_batch_name,
    _timestamp_console_text,
    _username_heading_title,
    _window_mode_title,
    bind_escape_close,
    catalog_focus_username,
    center_modal_on_parent,
    filter_batch_accounts,
    stories_cell_text,
)
from ig_orchestrator.gui.text_edit import (
    bind_edit_context_menu,
    first_clipboard_line,
    read_clipboard,
)
from ig_orchestrator.gui.theme import Tooltip, compact_icon_button, icon_button
from ig_orchestrator.gui.treeview_sort import bind_treeview_sort
from ig_orchestrator.input.batch_creation_service import DuplicateBatchNameError
from ig_orchestrator.models import AccountHistoryStatus
from ig_orchestrator.orchestration.processing_policy import (
    read_stories_first_enabled,
    write_stories_first_enabled,
)


class ProblemUrlsMixin:
    """Mixin: completed/retry/failed URL dialog and folder open."""

    def _on_batch_double_click(self, event: tk.Event) -> None:
        """Double click on an account row opens its Instagram profile in Chrome."""
        if not self.tree.identify_row(event.y):
            return
        self._open_selected_account_in_chrome()


    def _open_selected_account_in_chrome(self) -> None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.accounts)):
            return
        username = self.accounts[self.selected_index].username
        if not _open_chrome_tab(_instagram_profile_url(username)):
            messagebox.showwarning(
                "Abrir en Chrome", f"No se pudo abrir @{username} en el navegador."
            )


    def _open_selected_problem_urls(self) -> None:
        self._load_selected_row()
        kind = self._problem_kind_for_runtime(self._selected_runtime_progress())
        if kind is None:
            return
        self._open_account_problem_urls(kind)


    def _complete_selected_by_http(self) -> None:
        """«Completar por http…»: ask how many URLs and the pause, then download.

        Runs in a worker thread; progress goes to the bottom status bar. The
        pause is for this run only and is never stored.
        """

        if self.process_runner.is_running():
            messagebox.showwarning(
                t("complete_http.title"), t("complete_http.stop_first")
            )
            return
        thread = getattr(self, "_complete_http_thread", None)
        if isinstance(thread, threading.Thread) and thread.is_alive():
            messagebox.showinfo(t("complete_http.title"), t("complete_http.running"))
            return
        runtime = self._selected_runtime_progress()
        if runtime is None or self.selected_index is None:
            return
        username = self.accounts[self.selected_index].username
        job_ids = list_http_candidate_ids(self.connection, runtime.account_id)
        if not job_ids:
            messagebox.showinfo(
                t("complete_http.title"), t("complete_http.none", user=username)
            )
            return
        default_interval = int(
            load_run_settings(self.connection, self.settings).http_interval_seconds
        )

        dialog = tk.Toplevel(self.root)
        dialog.title(f"{t('complete_http.title')} · @{username}")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=14)
        body.grid(row=0, column=0)
        ttk.Label(
            body, text=t("complete_http.available", n=len(job_ids), user=username)
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        all_var = tk.BooleanVar(value=True)
        count_var = tk.StringVar(value=str(len(job_ids)))
        interval_var = tk.StringVar(value=str(default_interval))
        count_entry = ttk.Spinbox(
            body, from_=1, to=len(job_ids), textvariable=count_var, width=8
        )

        def sync_count_state() -> None:
            count_entry.configure(state="disabled" if all_var.get() else "normal")

        ttk.Checkbutton(
            body,
            text=t("complete_http.all"),
            variable=all_var,
            command=sync_count_state,
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=t("complete_http.first_n")).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        count_entry.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(body, text=t("complete_http.interval")).grid(
            row=3, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Spinbox(
            body, from_=0, to=3600, textvariable=interval_var, width=8
        ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(
            body,
            text=t("complete_http.note"),
            foreground="#57606a",
            wraplength=360,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        sync_count_state()

        estimate_var = tk.StringVar(value="")
        ttk.Label(
            body,
            textvariable=estimate_var,
            font=("Segoe UI", 10, "bold"),
            wraplength=360,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def refresh_estimate(*_args) -> None:
            """Live total time and finish clock for the current count and pause."""
            try:
                interval = float(interval_var.get().replace(",", "."))
                count = len(job_ids) if all_var.get() else int(count_var.get())
            except ValueError:
                estimate_var.set(t("complete_http.estimate_invalid"))
                return
            count = min(count, len(job_ids))
            if interval < 0 or count < 1:
                estimate_var.set(t("complete_http.estimate_invalid"))
                return
            seconds = estimate_http_duration(count, interval)
            finish = datetime.now() + timedelta(seconds=seconds)
            days = (finish.date() - date.today()).days
            when = finish.strftime("%H:%M")
            if days == 1:
                when += " " + t("complete_http.tomorrow")
            elif days > 1:
                when += " " + finish.strftime("%d/%m")
            estimate_var.set(
                t(
                    "complete_http.estimate",
                    count=count,
                    interval=f"{interval:g}",
                    duration=format_http_duration(seconds),
                    finish=when,
                )
            )

        def tick() -> None:
            if not dialog.winfo_exists():
                return
            refresh_estimate()
            dialog.after(15000, tick)

        for variable in (all_var, count_var, interval_var):
            variable.trace_add("write", refresh_estimate)
        tick()

        def start() -> None:
            try:
                interval = float(interval_var.get().replace(",", "."))
                count = len(job_ids) if all_var.get() else int(count_var.get())
            except ValueError:
                messagebox.showerror(
                    t("complete_http.title"), t("complete_http.invalid"), parent=dialog
                )
                return
            if interval < 0 or count < 1:
                messagebox.showerror(
                    t("complete_http.title"), t("complete_http.invalid"), parent=dialog
                )
                return
            dialog.destroy()
            self._start_complete_http(username, job_ids[:count], interval)

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=t("complete_http.cancel"), command=dialog.destroy).pack(
            side=tk.RIGHT
        )
        ttk.Button(buttons, text=t("complete_http.start"), command=start).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        center_modal_on_parent(dialog, self.root, self.root.state() == "zoomed")
        bind_escape_close(dialog, on_close=dialog.destroy)

    def _start_complete_http(
        self, username: str, job_ids: list[int], interval: float
    ) -> None:
        progress_box: dict[str, object] = {"progress": None}

        def report(progress) -> None:
            progress_box["progress"] = dataclasses.replace(progress)

        cancel_event = threading.Event()
        self._complete_http_cancel = cancel_event
        thread = threading.Thread(
            target=run_manual_http_download,
            kwargs={
                "settings": self.settings,
                "job_ids": job_ids,
                "allow_completed": False,
                "allow_busy": True,
                "interval_seconds": interval,
                "cancel": cancel_event,
                "report": report,
            },
            daemon=True,
        )
        self._complete_http_thread = thread
        self._write_console(
            f"[HTTP] @{username}: {len(job_ids)} URL(s), una cada {interval:g} s.\n"
        )
        self._set_status(
            t("complete_http.status", user=username, done=0, total=len(job_ids), text="")
        )
        thread.start()

        def poll() -> None:
            progress = progress_box["progress"]
            if progress is not None:
                self._set_status(
                    t(
                        "complete_http.status",
                        user=username,
                        done=progress.done,
                        total=progress.total,
                        text=progress.text,
                    )
                )
            if thread.is_alive():
                self.root.after(1000, poll)
                return
            self._refresh_runtime_progress()
            if progress is not None and progress.finished:
                summary = t(
                    "complete_http.done",
                    user=username,
                    ok=progress.ok,
                    failed=progress.failed,
                    skipped=progress.skipped,
                )
                self._set_status(summary)
                self._write_console(f"[HTTP] {summary}\n")
                if progress.error:
                    messagebox.showerror(
                        t("complete_http.title"),
                        t("problem_urls.http_error", reason=progress.error),
                    )

        self.root.after(1000, poll)

    def _open_selected_account_folder(self) -> None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.accounts)):
            messagebox.showwarning(
                "Abrir carpeta",
                "Selecciona primero una cuenta del lote.",
            )
            return
        account = self.accounts[self.selected_index]
        runtime = self.runtime_progress.get(account.username.casefold())
        if runtime is None or runtime.status != "COMPLETED":
            messagebox.showinfo(
                "Abrir carpeta",
                f"@{account.username} aún no está Completada.\n"
                "La carpeta se puede abrir cuando la cuenta termina de descargar.",
            )
            return
        folder = resolve_account_download_folder(
            self.connection,
            account_id=runtime.account_id,
            username=account.username,
            working_folder_setting=self.settings.working_folder,
        )
        if folder is None:
            expected = self.settings.working_folder / account.username
            messagebox.showwarning(
                "Abrir carpeta",
                f"No se encontró la carpeta de @{account.username} en disco.\n"
                f"Ruta esperada: {expected}",
            )
            return
        try:
            _open_path_in_explorer(folder)
        except OSError as exc:
            messagebox.showerror(
                "Abrir carpeta",
                f"No se pudo abrir la carpeta:\n{folder}\n\n{exc}",
            )


    def _open_account_problem_urls(self, kind: ProblemUrlKind) -> None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.accounts)):
            messagebox.showwarning(
                "URLs de la cuenta",
                "Selecciona primero una cuenta del lote.",
            )
            return
        account = self.accounts[self.selected_index]
        runtime = self.runtime_progress.get(account.username.casefold())
        if runtime is None:
            messagebox.showinfo(
                "URLs de la cuenta",
                "No hay estado de ejecución para esta cuenta todavía.\n"
                "Abre o reanuda el lote para consultar URLs, fallos y reintentos.",
            )
            return
        if kind == "pending" and runtime.total_items - runtime.completed_items <= 0:
            messagebox.showinfo(
                "URLs pendientes",
                f"@{account.username} no tiene URLs pendientes: todas están completadas.",
            )
            return
        if kind == "completed" and not runtime.completed_items:
            messagebox.showinfo(
                "URLs completadas",
                f"@{account.username} no tiene URLs completadas todavía.",
            )
            return
        if kind == "retry" and not runtime.retry_items:
            messagebox.showinfo(
                "URLs en reintento",
                f"@{account.username} no tiene URLs en reintento ahora mismo.",
            )
            return
        if kind == "failed" and not runtime.failed_items:
            messagebox.showinfo(
                "URLs fallidas",
                f"@{account.username} no tiene URLs fallidas definitivas.",
            )
            return

        kind_labels = {
            "pending": "Pendientes",
            "completed": "Completadas",
            "retry": "Reintentos",
            "failed": "Fallidas",
        }
        kind_label = kind_labels.get(kind, kind)
        title_batch = (
            f" · batch #{self.active_batch_id}"
            if self.active_batch_id is not None
            else ""
        )
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{kind_label} · @{account.username}{title_batch}")
        dialog.geometry("880x380")
        dialog.minsize(640, 280)
        dialog.transient(self.root)
        # Non-modal: keep the main window usable while a batch is running.
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        summary_var = tk.StringVar()
        ttk.Label(
            dialog,
            textvariable=summary_var,
            padding=(12, 10, 12, 2),
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            dialog,
            text="Doble click en una fila para abrir la URL en Chrome.",
            foreground="#57606a",
            padding=(12, 0, 12, 6),
        ).grid(row=1, column=0, sticky="w")

        table_frame = ttk.Frame(dialog, padding=(10, 0, 10, 0))
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("url", "status", "error", "retries")
        tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        for column, title, width, stretch in (
            ("url", "URL", 420, True),
            ("status", "Estado", 140, False),
            ("error", "Error", 220, True),
            ("retries", "Reintentos", 80, False),
        ):
            tree.heading(column, text=title)
            tree.column(
                column,
                width=width,
                minwidth=60 if column != "url" else 160,
                anchor="w" if column != "retries" else "e",
                stretch=stretch,
            )
        bind_treeview_sort(tree, columns, title_for=lambda c: {
            "url": "URL",
            "status": "Estado",
            "error": "Error",
            "retries": "Reintentos",
        }[c])
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=tree.yview,
            style="Visible.Vertical.TScrollbar",
        )
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)

        url_by_iid: dict[str, str] = {}
        refresh_after_id: list[str | None] = [None]

        def truncate_error(text: str | None, *, limit: int = 120) -> str:
            if not text:
                return "—"
            compact = " ".join(text.split())
            if len(compact) <= limit:
                return compact
            return compact[: limit - 1] + "…"

        def reload_rows() -> None:
            selected = tree.selection()
            selected_id = selected[0] if selected else None
            for item in tree.get_children():
                tree.delete(item)
            url_by_iid.clear()
            try:
                rows = list_account_problem_urls(
                    self.connection,
                    account_id=runtime.account_id,
                    kind=kind,
                )
            except ValueError as exc:
                summary_var.set(str(exc))
                return
            for item in rows:
                iid = str(item.job_id)
                url_by_iid[iid] = item.url
                tree.insert(
                    "",
                    tk.END,
                    iid=iid,
                    values=(
                        item.url,
                        item.status,
                        truncate_error(item.last_error),
                        item.retries,
                    ),
                )
            live = (
                " · actualización automática (~1s)"
                if self.process_runner.is_running()
                else ""
            )
            summary_var.set(f"{len(rows)} URL(s) · {kind_label.lower()}{live}")
            if selected_id and tree.exists(selected_id):
                tree.selection_set(selected_id)
                tree.focus(selected_id)
                tree.see(selected_id)

        def open_selected_url(_event: tk.Event | None = None) -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(
                    "Abrir URL",
                    "Selecciona una fila primero.",
                    parent=dialog,
                )
                return
            url = url_by_iid.get(selection[0])
            if not url:
                return
            if not _open_chrome_tab(url):
                messagebox.showerror(
                    "Abrir URL",
                    "No se pudo abrir la URL en el navegador.",
                    parent=dialog,
                )

        def schedule_auto_refresh() -> None:
            if refresh_after_id[0] is not None:
                try:
                    dialog.after_cancel(refresh_after_id[0])
                except tk.TclError:
                    pass
                refresh_after_id[0] = None
            if not dialog.winfo_exists():
                return
            reload_rows()
            if self.process_runner.is_running():
                refresh_after_id[0] = dialog.after(1000, schedule_auto_refresh)

        def on_close() -> None:
            cancel_event = http_state.get("cancel")
            if isinstance(cancel_event, threading.Event):
                cancel_event.set()
            if refresh_after_id[0] is not None:
                try:
                    dialog.after_cancel(refresh_after_id[0])
                except tk.TclError:
                    pass
                refresh_after_id[0] = None
            dialog.destroy()

        def copy_to_clipboard(url: str) -> None:
            """Copia URL al portapapeles."""
            try:
                dialog.clipboard_clear()
                dialog.clipboard_append(url)
                dialog.update()
                _show_copied_notification()
            except tk.TclError as e:
                messagebox.showerror(
                    t("error"),
                    f"{t('problem_urls.copy_failed')}: {e}",
                    parent=dialog,
                )

        def _show_copied_notification() -> None:
            """Muestra notificación temporal 'Copied!'"""
            notification = tk.Toplevel(dialog)
            notification.wm_overrideredirect(True)
            notification.wm_attributes("-alpha", 0.9)
            notification.wm_attributes("-topmost", True)

            # Posicionar en el centro inferior del dialog
            dialog_x = dialog.winfo_x()
            dialog_y = dialog.winfo_y()
            dialog_w = dialog.winfo_width()
            dialog_h = dialog.winfo_height()

            label = tk.Label(
                notification,
                text=t("problem_urls.copied"),
                background="#10b981",
                foreground="white",
                relief="solid",
                borderwidth=1,
                padx=12,
                pady=6,
                font=("Segoe UI", 9, "bold"),
            )
            label.pack()

            notification.update_idletasks()
            notif_w = notification.winfo_width()
            notif_h = notification.winfo_height()
            notif_x = dialog_x + (dialog_w - notif_w) // 2
            notif_y = dialog_y + dialog_h - notif_h - 20
            notification.wm_geometry(f"+{notif_x}+{notif_y}")

            def hide_notification():
                try:
                    notification.destroy()
                except tk.TclError:
                    pass

            notification.after(1500, hide_notification)

        def copy_selected_url() -> None:
            """Copia la URL seleccionada al portapapeles."""
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(
                    t("error"),
                    "Selecciona una fila primero.",
                    parent=dialog,
                )
                return
            url = url_by_iid.get(selection[0])
            if url:
                copy_to_clipboard(url)

        def copy_all_urls() -> None:
            """Copia todas las URLs al portapapeles, una por línea."""
            if not url_by_iid:
                messagebox.showinfo(
                    "Copiar",
                    "No hay URLs para copiar.",
                    parent=dialog,
                )
                return
            all_urls = "\n".join(url_by_iid.values())
            try:
                dialog.clipboard_clear()
                dialog.clipboard_append(all_urls)
                dialog.update()
                _show_copied_notification()
            except tk.TclError as e:
                messagebox.showerror(
                    t("error"),
                    f"{t('problem_urls.copy_failed')}: {e}",
                    parent=dialog,
                )

        def show_context_menu(event: tk.Event) -> None:
            """Muestra context menu al hacer click derecho."""
            selection = tree.identify_row(event.y)
            if selection:
                tree.selection_set(selection)
                context_menu = tk.Menu(dialog, tearoff=False)
                url = url_by_iid.get(selection)

                if url:
                    context_menu.add_command(
                        label=t("problem_urls.copy"),
                        command=lambda u=url: copy_to_clipboard(u),
                    )
                    context_menu.add_command(
                        label=t("problem_urls.open_chrome"),
                        command=lambda u=url: _open_chrome_tab(u),
                    )
                    context_menu.add_separator()

                context_menu.add_command(
                    label=t("problem_urls.copy_all"),
                    command=copy_all_urls,
                )
                context_menu.post(event.x_root, event.y_root)

        def on_ctrl_c(event: tk.Event) -> None:
            """Atajo Ctrl+C para copiar URL seleccionada."""
            copy_selected_url()

        http_state: dict[str, object] = {"cancel": None, "progress": None, "thread": None}
        http_status_var = tk.StringVar(value="")
        post_or_reel = re.compile(r"instagram\.com/(?:[^/?#]+/)?(?:p|reel|reels)/", re.I)

        def http_running() -> bool:
            thread = http_state["thread"]
            return isinstance(thread, threading.Thread) and thread.is_alive()

        def poll_http() -> None:
            if not dialog.winfo_exists():
                return
            progress = http_state["progress"]
            if progress is not None:
                http_status_var.set(
                    t(
                        "problem_urls.http_progress",
                        done=progress.done,
                        total=progress.total,
                        text=progress.text,
                    )
                )
            reload_rows()
            if http_running():
                dialog.after(1000, poll_http)
                return
            http_button.configure(text=t("problem_urls.http_download"))
            if progress is not None and progress.finished:
                http_status_var.set(
                    t("problem_urls.http_done", ok=progress.ok, failed=progress.failed)
                )
                if progress.error:
                    messagebox.showerror(
                        t("problem_urls.http_download"),
                        t("problem_urls.http_error", reason=progress.error),
                        parent=dialog,
                    )

        def start_or_stop_http() -> None:
            if http_running():
                cancel_event = http_state["cancel"]
                if isinstance(cancel_event, threading.Event):
                    cancel_event.set()
                http_button.configure(text=t("problem_urls.http_download"))
                return
            selection = list(tree.selection())
            if not selection:
                messagebox.showinfo(
                    t("problem_urls.http_download"),
                    t("problem_urls.http_none"),
                    parent=dialog,
                )
                return
            usable = [iid for iid in selection if post_or_reel.search(url_by_iid.get(iid, ""))]
            ignored = len(selection) - len(usable)
            if not usable:
                messagebox.showinfo(
                    t("problem_urls.http_download"),
                    t("problem_urls.http_unsupported", n=ignored),
                    parent=dialog,
                )
                return
            interval = load_run_settings(self.connection, self.settings).http_interval_seconds
            question = t("problem_urls.http_confirm", n=len(usable), interval=interval)
            if kind == "completed":
                question = t("problem_urls.http_confirm_completed") + question
            if ignored:
                question = t("problem_urls.http_unsupported", n=ignored) + " " + question
            if not messagebox.askyesno(
                t("problem_urls.http_download"), question, parent=dialog
            ):
                return
            cancel_event = threading.Event()
            http_state["cancel"] = cancel_event
            http_state["progress"] = None

            def report(progress) -> None:
                http_state["progress"] = dataclasses.replace(progress)

            thread = threading.Thread(
                target=run_manual_http_download,
                kwargs={
                    "settings": self.settings,
                    "job_ids": [int(iid) for iid in usable],
                    "allow_completed": kind == "completed",
                    "allow_busy": not self.process_runner.is_running(),
                    "cancel": cancel_event,
                    "report": report,
                },
                daemon=True,
            )
            http_state["thread"] = thread
            http_button.configure(text=t("problem_urls.http_stop"))
            thread.start()
            dialog.after(1000, poll_http)

        actions = ttk.Frame(dialog, padding=10)
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Button(actions, text="Cerrar", command=on_close).pack(side=tk.LEFT)
        if kind in ("retry", "completed", "pending"):
            http_button = ttk.Button(
                actions,
                text=t("problem_urls.http_download"),
                command=start_or_stop_http,
            )
            http_button.pack(side=tk.LEFT, padx=(8, 0))
            ttk.Label(actions, textvariable=http_status_var).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="Actualizar", command=reload_rows).pack(
            side=tk.RIGHT
        )
        ttk.Button(
            actions,
            text=t("problem_urls.copy_all"),
            command=copy_all_urls,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(
            actions,
            text=t("problem_urls.copy"),
            command=copy_selected_url,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="Abrir seleccionada", command=open_selected_url).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        tree.bind("<Double-Button-1>", open_selected_url)
        tree.bind("<Button-3>", show_context_menu)
        dialog.bind("<Control-c>", on_ctrl_c)
        dialog.protocol("WM_DELETE_WINDOW", on_close)
        schedule_auto_refresh()
        center_modal_on_parent(dialog, self.root, self.root.state() == "zoomed")
        bind_escape_close(dialog, on_close=on_close)
        dialog.focus_set()

