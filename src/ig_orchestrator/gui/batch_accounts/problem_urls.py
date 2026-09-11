from __future__ import annotations

from datetime import date
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
    catalog_focus_username,
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

    def _open_selected_problem_urls(self) -> None:
        self._load_selected_row()
        kind = self._problem_kind_for_runtime(self._selected_runtime_progress())
        if kind is None:
            return
        self._open_account_problem_urls(kind)


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
            selectmode="browse",
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
            if refresh_after_id[0] is not None:
                try:
                    dialog.after_cancel(refresh_after_id[0])
                except tk.TclError:
                    pass
                refresh_after_id[0] = None
            dialog.destroy()

        actions = ttk.Frame(dialog, padding=10)
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Button(actions, text="Cerrar", command=on_close).pack(side=tk.LEFT)
        ttk.Button(actions, text="Actualizar", command=reload_rows).pack(
            side=tk.RIGHT
        )
        ttk.Button(actions, text="Abrir seleccionada", command=open_selected_url).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        tree.bind("<Double-Button-1>", open_selected_url)
        dialog.protocol("WM_DELETE_WINDOW", on_close)
        schedule_auto_refresh()
        dialog.focus_set()

