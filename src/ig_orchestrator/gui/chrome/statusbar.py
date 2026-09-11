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


class StatusBarMixin:
    """Mixin: console, status bar, enable/disable while running."""

    def _write_console(self, text: str) -> None:
        stamped = _timestamp_console_text(text)
        log = getattr(self, "log_window", None)
        if log is not None:
            log.append(stamped)
        console = getattr(self, "console", None)
        if console is None:
            return
        try:
            console.configure(state="normal")
            console.insert(tk.END, stamped)
            console.see(tk.END)
            console.configure(state="disabled")
        except tk.TclError:
            pass


    def _clear_console(self) -> None:
        log = getattr(self, "log_window", None)
        if log is not None:
            log.clear()
        console = getattr(self, "console", None)
        if console is None:
            return
        try:
            console.configure(state="normal")
            console.delete("1.0", tk.END)
            console.configure(state="disabled")
        except tk.TclError:
            pass


    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        bar = getattr(self, "status_bar_var", None)
        if bar is not None:
            accounts = getattr(self, "account_progress_var", None)
            items = getattr(self, "item_progress_var", None)
            parts = []
            if accounts is not None:
                parts.append(accounts.get())
            if items is not None:
                parts.append(items.get())
            parts.append(text)
            bar.set("  ·  ".join(part for part in parts if part))


    def _set_process_running(self, running: bool) -> None:
        self._set_descendants_enabled(self.top_region, not running)
        self._set_descendants_enabled(self.body_region, not running)
        button_state = "disabled" if running else "normal"
        self.register_button.configure(state=button_state)
        # The lots dialog stays reachable during a batch/sequence so pending
        # queue items can be removed before they start.
        if running and self.active_process_kind == "rename":
            self.pending_button.configure(state="disabled")
        else:
            self.pending_button.configure(state="normal")
        self.execute_button.configure(state=button_state)
        self.save_selection_button.configure(state=button_state)
        if running and self.active_process_kind == "batch":
            _set_ttk_enabled(self.tree, True)
            self.delete_button.configure(state="normal")
            self.save_selection_button.configure(state="disabled")
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.rename_button.configure(
            state="normal" if not running and self.batch_ready_for_rename else "disabled"
        )
        # Always available: only previews the rename command, never runs it.
        self.rename_manual_button.configure(state="normal")
        if not running:
            self._update_batch_context()
        self._set_status("Ejecutando..." if running else self.status_var.get())


    def _set_descendants_enabled(self, parent: tk.Misc, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in parent.winfo_children():
            try:
                if "state" in child.configure():
                    child.configure(state=state)
            except tk.TclError:
                pass
            self._set_descendants_enabled(child, enabled)

