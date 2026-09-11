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


class ToolbarMixin:
    """Mixin: batch mode labels and pending-button state."""

    def _update_pending_button_label(self) -> None:
        total = len(list_managed_batches(self.connection))
        # Icon button: count stays in the frozen Lotes dialog title, not here.
        _ = total


    def _update_batch_context(self) -> None:
        if self.history_readonly:
            name = self.batch_name_var.get().strip() or "(sin nombre)"
            batch_id = self.active_batch_id
            id_part = f" · id={batch_id}" if batch_id is not None else ""
            self.batch_context_var.set(
                f"HISTÓRICO · solo lectura · {name}{id_part} · COMPLETED"
            )
            self.register_button.configure(state="disabled")
            self.execute_button.configure(state="disabled")
            self.delete_all_button.configure(state="disabled")
            self.save_selection_button.configure(state="disabled")
            self.delete_button.configure(state="disabled")
            self.rename_button.configure(state="disabled")
            self.root.title(
                f"{t('app.name')} - "
                + t("mode.history", name=name, id=batch_id or "-")
            )
            return

        context, register_text, execute_text, actions_enabled = _batch_mode_details(
            saved_batch_id=self.saved_batch_id,
            active_batch_id=self.active_batch_id,
            batch_name=self.batch_name_var.get(),
        )
        self.batch_context_var.set(context)
        self.root.title(f"{t('app.name')} - {_window_mode_title(context, self.batch_name_var.get(), self.history_readonly, self.saved_batch_id, self.active_batch_id)}")
        self.register_button.configure(
            state="normal" if actions_enabled else "disabled",
        )
        self.execute_button.configure(
            state="normal" if actions_enabled else "disabled",
        )
        self.delete_all_button.configure(
            state="normal" if actions_enabled else "disabled"
        )
        self.save_selection_button.configure(
            state="normal" if actions_enabled else "disabled"
        )
        running_batch = (
            self.process_runner.is_running() and self.active_process_kind == "batch"
        )
        self.delete_button.configure(
            state="normal" if (actions_enabled or running_batch) else "disabled"
        )

