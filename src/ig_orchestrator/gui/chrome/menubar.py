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


class MenubarMixin:
    """Mixin: application menubar."""

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label=t("menu.file.new"), command=self._start_new_batch)
        file_menu.add_command(label=t("menu.file.save"), command=self._save_batch)
        file_menu.add_command(
            label=t("menu.file.open_batches"), command=self._open_pending_batches
        )
        file_menu.add_separator()
        file_menu.add_command(label=t("menu.file.exit"), command=self.root.destroy)
        menubar.add_cascade(label=t("menu.file"), menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label=t("menu.edit.paste_add"), command=self._paste_and_upsert)
        edit_menu.add_command(label=t("menu.edit.add_update"), command=self._upsert_account)
        edit_menu.add_command(label=t("menu.edit.paste"), command=self._paste_urls)
        edit_menu.add_command(label=t("menu.edit.normalize"), command=self._normalize_urls)
        edit_menu.add_command(label=t("menu.edit.clear_editor"), command=self._clear_editor)
        edit_menu.add_separator()
        edit_menu.add_command(label=t("menu.edit.delete"), command=self._delete_selected)
        edit_menu.add_command(label=t("menu.edit.delete_all"), command=self._delete_all_accounts)
        menubar.add_cascade(label=t("menu.edit"), menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label=t("menu.view.log"), command=self.log_window.toggle)
        view_menu.add_separator()
        view_menu.add_command(
            label=t("menu.view.catalog_list"),
            command=lambda: self._set_catalog_view("list"),
        )
        view_menu.add_command(
            label=t("menu.view.catalog_tree"),
            command=lambda: self._set_catalog_view("tree"),
        )
        menubar.add_cascade(label=t("menu.view"), menu=view_menu)

        batch_menu = tk.Menu(menubar, tearoff=False)
        batch_menu.add_command(label=t("menu.batch.execute"), command=self._execute)
        batch_menu.add_command(label=t("menu.batch.stop"), command=self._cancel_process)
        batch_menu.add_separator()
        batch_menu.add_command(label=t("menu.batch.rename"), command=self._rename_manual_files)
        batch_menu.add_command(
            label=t("menu.batch.rename_manual"), command=self._show_manual_rename_command
        )
        menubar.add_cascade(label=t("menu.batch"), menu=batch_menu)

        catalog_menu = tk.Menu(menubar, tearoff=False)
        catalog_menu.add_command(label=t("menu.catalog.open"), command=self._open_catalog_account)
        catalog_menu.add_command(
            label=t("menu.catalog.favorite"),
            command=lambda: self._set_catalog_account_favorite(True),
        )
        catalog_menu.add_command(
            label=t("menu.catalog.unfavorite"),
            command=lambda: self._set_catalog_account_favorite(False),
        )
        catalog_menu.add_command(
            label=t("menu.catalog.inactive"), command=self._set_catalog_account_inactive
        )
        catalog_menu.add_command(
            label=t("menu.catalog.delete"), command=self._disable_catalog_account
        )
        catalog_menu.add_command(
            label=t("menu.catalog.enable"), command=self._enable_catalog_account
        )
        menubar.add_cascade(label=t("menu.catalog"), menu=catalog_menu)

        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(
            label=t("menu.settings.open"), command=self._open_settings
        )
        menubar.add_cascade(label=t("menu.settings"), menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(
            label=t("menu.help.about"),
            command=lambda: messagebox.showinfo(
                t("menu.help.about"), t("app.about", version=__version__)
            ),
        )
        menubar.add_cascade(label=t("menu.help"), menu=help_menu)
        self.root.config(menu=menubar)

