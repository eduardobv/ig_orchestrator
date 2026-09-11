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


class BatchProgressMixin:
    """Mixin: runtime progress poll and batch contextual menu."""

    def _refresh_runtime_progress(self) -> None:
        if self.active_batch_id is None:
            return
        progress = get_account_runtime_progress(self.connection, self.active_batch_id)
        self.runtime_progress = {item.username.casefold(): item for item in progress}
        self._refresh_table()
        completed = sum(item.status == "COMPLETED" for item in progress)
        retry = sum(item.retry_items > 0 for item in progress)
        remaining = sum(item.status != "COMPLETED" for item in progress)
        self.account_progress_var.set(
            f"Cuentas: {completed}/{len(progress)} completas | "
            f"{retry} en reintento | {remaining} pendientes"
        )


    def _schedule_progress_poll(self) -> None:
        if not self.process_runner.is_running() or self.active_batch_id is None:
            self.progress_poll_id = None
            return
        self._refresh_runtime_progress()
        self.progress_poll_id = self.root.after(600, self._schedule_progress_poll)


    def _stop_progress_poll(self) -> None:
        if self.progress_poll_id is not None:
            self.root.after_cancel(self.progress_poll_id)
            self.progress_poll_id = None


    def _show_batch_menu(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        if item_id not in self.tree.selection():
            self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self.selected_index = int(item_id)
        runtime = self._selected_runtime_progress()
        completed_state = (
            "normal" if runtime is not None and runtime.completed_items else "disabled"
        )
        retry_state = "normal" if runtime is not None and runtime.retry_items else "disabled"
        failed_state = (
            "normal" if runtime is not None and runtime.failed_items else "disabled"
        )
        folder_state = (
            "normal"
            if runtime is not None and runtime.status == "COMPLETED"
            else "disabled"
        )
        complete_state = "disabled" if self.history_readonly else "normal"
        self.batch_menu.entryconfigure("Completar", state=complete_state)
        self.batch_menu.entryconfigure("Ver URLs completadas…", state=completed_state)
        self.batch_menu.entryconfigure("Ver URLs en reintento…", state=retry_state)
        self.batch_menu.entryconfigure("Ver URLs fallidas…", state=failed_state)
        self.batch_menu.entryconfigure("Abrir carpeta", state=folder_state)
        self.batch_menu.tk_popup(event.x_root, event.y_root)


    def _selected_runtime_progress(self) -> AccountRuntimeProgress | None:
        if self.selected_index is None or not (0 <= self.selected_index < len(self.accounts)):
            return None
        username = self.accounts[self.selected_index].username.casefold()
        return self.runtime_progress.get(username)


    def _problem_kind_for_runtime(
        self,
        runtime: AccountRuntimeProgress | None,
    ) -> ProblemUrlKind | None:
        if runtime is None:
            return None
        # Same priority as the visible Estado column.
        if runtime.retry_items:
            return "retry"
        if runtime.status == "FAILED" or (
            runtime.failed_items and not runtime.pending_items
        ):
            return "failed"
        if runtime.failed_items:
            return "failed"
        if runtime.status == "COMPLETED" and runtime.completed_items:
            return "completed"
        if runtime.completed_items and not runtime.pending_items and not runtime.retry_items:
            return "completed"
        return None


    def _complete_selected_account(self) -> None:
        if self.process_runner.is_running():
            messagebox.showwarning(
                "Completar cuenta",
                "Detén primero la ejecución antes de completar una cuenta manualmente.",
            )
            return
        if self.selected_index is None or self.active_batch_id is None:
            return
        account = self.accounts[self.selected_index]
        runtime = self.runtime_progress.get(account.username.casefold())
        if runtime is None:
            messagebox.showwarning(
                "Completar cuenta", "No se encontró el estado persistido de la cuenta."
            )
            return
        if not messagebox.askyesno(
            "Completar cuenta",
            f"¿Dar por completada @{account.username}?\n\n"
            "Las URLs todavía pendientes quedarán como FAILED_FINAL con motivo de "
            "finalización manual.",
        ):
            return
        try:
            affected = complete_account_manually(
                self.connection,
                batch_id=self.active_batch_id,
                account_id=runtime.account_id,
            )
        except ValueError as exc:
            messagebox.showerror("Completar cuenta", str(exc))
            return
        self._refresh_runtime_progress()
        self.batch_ready_for_rename = is_batch_ready_for_rename(
            self.connection, self.active_batch_id
        )
        self.rename_button.configure(
            state="normal" if self.batch_ready_for_rename else "disabled"
        )
        self._write_console(
            f"Cuenta @{account.username} completada manualmente; "
            f"{affected} URL(s) pendientes cerradas como FAILED_FINAL.\n"
        )
        self._update_pending_button_label()

