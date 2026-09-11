from __future__ import annotations

from datetime import date
from pathlib import Path
from sqlite3 import Connection, IntegrityError
import tkinter as tk
from tkinter import font as tkfont
from tkinter import colorchooser, filedialog, messagebox, ttk

from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogEntry,
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
from ig_orchestrator.gui.process_runner import (
    MANUAL_RENAME_SCRIPT,
    NewAccountRenameParameters,
    ProcessRunner,
    build_manual_rename_command,
    build_run_continue_command,
    format_manual_rename_command_preview,
)
from ig_orchestrator.gui.rename_folder_status import (
    decide_rename_completion,
    list_unmoved_account_folders,
)
from ig_orchestrator.settings import Settings
from ig_orchestrator.orchestration.processing_policy import (
    read_stories_first_enabled,
    write_stories_first_enabled,
)
from ig_orchestrator.input.batch_creation_service import DuplicateBatchNameError
from ig_orchestrator.models import AccountHistoryStatus
from ig_orchestrator import __version__
from ig_orchestrator.db.downloaded_files_cleanup import purge_downloaded_files
from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.catalog_colors import (
    load_catalog_colors,
    save_color,
)
from ig_orchestrator.gui.catalog_tree import build_catalog_tree
from ig_orchestrator.gui.i18n import current_language, load_language, t
from ig_orchestrator.gui.icons import IconSet
from ig_orchestrator.gui.log_window import LogWindow
from ig_orchestrator.gui.text_edit import (
    bind_edit_context_menu,
    first_clipboard_line,
    read_clipboard,
)
from ig_orchestrator.gui.theme import (
    Tooltip,
    apply_light_theme,
    compact_icon_button,
    icon_button,
)
from ig_orchestrator.gui.treeview_sort import bind_treeview_sort
from ig_orchestrator.gui.shared.helpers import (
    _ACCOUNT_PROGRESS_RE,
    _BATCH_COLUMNS,
    _CATALOG_COLORS,
    _ITEM_PROGRESS_RE,
    _account_display_status,
    _batch_column_samples,
    _batch_mode_details,
    _catalog_entry_colors,
    _catalog_width_chars,
    _draft_signature,
    _gui_setting,
    _half_screen_geometry,
    _instagram_profile_url,
    _latest_executed_batch_name,
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
    batch_username_matches_filter,
    catalog_focus_username,
    filter_batch_accounts,
    stories_cell_text,
)


from ig_orchestrator.gui.batch_accounts.panel import BatchAccountsPanelMixin
from ig_orchestrator.gui.batch_accounts.problem_urls import ProblemUrlsMixin
from ig_orchestrator.gui.batch_accounts.progress import BatchProgressMixin
from ig_orchestrator.gui.batches.dialog import BatchesDialogMixin
from ig_orchestrator.gui.catalog.panel import CatalogPanelMixin
from ig_orchestrator.gui.chrome.menubar import MenubarMixin
from ig_orchestrator.gui.chrome.statusbar import StatusBarMixin
from ig_orchestrator.gui.chrome.toolbar import ToolbarMixin
from ig_orchestrator.gui.editor.panel import EditorPanelMixin
from ig_orchestrator.gui.run.controller import RunControllerMixin
from ig_orchestrator.gui.run.rename import RenameMixin
from ig_orchestrator.gui.settings.dialog import SettingsDialogMixin

def launch_gui(
    *,
    connection: Connection,
    settings: Settings,
    batch_json_path: Path = Path("config/batch.json"),
) -> None:
    language = "es"
    if is_gui_schema(connection):
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'ui.language'"
        ).fetchone()
        if row is not None and str(row["value"]).strip():
            language = str(row["value"]).strip()
    load_language(language)
    root = tk.Tk()
    apply_light_theme(root)
    InstagramOrchestratorApp(
        root,
        connection=connection,
        settings=settings,
        batch_json_path=batch_json_path,
    )
    root.mainloop()


class InstagramOrchestratorApp(
    CatalogPanelMixin,
    EditorPanelMixin,
    BatchAccountsPanelMixin,
    BatchProgressMixin,
    ProblemUrlsMixin,
    MenubarMixin,
    ToolbarMixin,
    StatusBarMixin,
    SettingsDialogMixin,
    BatchesDialogMixin,
    RunControllerMixin,
    RenameMixin,
):
    def __init__(
        self,
        root: tk.Tk,
        *,
        connection: Connection,
        settings: Settings,
        batch_json_path: Path,
    ) -> None:
        self.root = root
        self.connection = connection
        self.settings = settings
        self.catalog_service = AccountCatalogService(
            connection,
            batch_json_path=batch_json_path,
        )
        self.catalog_entries = self.catalog_service.list_entries()
        self.today_catalog_usernames = list_usernames_active_on_date(
            connection, date.today()
        )
        self.destination_paths = self.catalog_service.list_destination_paths()
        self.accounts: list[AccountDraft] = []
        self.selected_index: int | None = None
        self.saved_batch_id: int | None = None
        self.saved_draft_signature: tuple[object, ...] | None = None
        self.process_runner = ProcessRunner()
        self.batch_ready_for_rename = False
        self.rename_new_accounts: tuple[NewAccountRenameParameters, ...] = ()
        self.last_run_was_dry_run = False
        self.dry_run_var = tk.BooleanVar(value=False)
        self.active_batch_id: int | None = None
        self.active_queue_id: int | None = None
        self.cancel_requested = False
        self.active_process_kind: str | None = None
        self._batches_dialog: tk.Toplevel | None = None
        self._refresh_queue_panel = None
        self.runtime_progress: dict[str, AccountRuntimeProgress] = {}
        self.progress_poll_id: str | None = None
        self._username_sort_ascending: bool | None = None
        self._catalog_silent_token = 0
        self.history_readonly = False
        self.catalog_view_mode = "list"
        self.catalog_colors = dict(_CATALOG_COLORS)
        if is_gui_schema(connection):
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'ui.catalog_view'"
            ).fetchone()
            if row is not None and str(row["value"]) in {"list", "tree"}:
                self.catalog_view_mode = str(row["value"])
            self.catalog_colors = load_catalog_colors(connection)

        today = date.today().isoformat()
        self.batch_name_var = tk.StringVar(
            value=_latest_executed_batch_name(connection) or _suggest_batch_name()
        )
        self.default_date_var = tk.StringVar(value=today)
        self.catalog_filter_var = tk.StringVar()
        self.batch_filter_var = tk.StringVar()
        self.batch_count_var = tk.StringVar(value=t("label.batch_count", count=0))
        self.username_var = tk.StringVar()
        self.account_date_var = tk.StringVar(value=today)
        self.stories_var = tk.BooleanVar(value=False)
        self.new_account_var = tk.BooleanVar(value=False)
        self.catalog_update_var = tk.BooleanVar(value=False)
        self.owner_id_var = tk.StringVar()
        self.start_init_date_var = tk.StringVar()
        self.destination_path_var = tk.StringVar()
        self.batch_context_var = tk.StringVar()
        self.status_var = tk.StringVar(value=t("status.ready"))
        self.account_progress_var = tk.StringVar(value="Cuentas: -")
        self.item_progress_var = tk.StringVar(value="Items: -")
        self.status_bar_var = tk.StringVar(value=t("status.ready"))
        self.indicators_var = tk.StringVar(value="URLs: 0")
        self.icons = IconSet(self.root)
        self.log_window = LogWindow(self.root)

        self.root.title(t("app.name"))
        self.root.geometry(
            _half_screen_geometry(
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
            )
        )
        self.root.minsize(860, 680)
        self._build_widgets()
        self.batch_name_var.trace_add("write", lambda *_: self._update_batch_context())
        self._refresh_catalog()
        self._refresh_table()
        self._update_pending_button_label()
        self._update_batch_context()
        self._restore_open_queue()


    def _restore_open_queue(self) -> None:
        """Pick up a sequence persisted by this or another instance."""
        queue = get_open_queue(self.connection)
        if queue is None:
            self.active_queue_id = None
            return
        self.active_queue_id = queue.id
        if queue.status == QueueStatus.AWAITING_RENAME.value and queue.rename_batch_ids:
            self.batch_ready_for_rename = True
            self.rename_button.configure(state="normal")
            try:
                params = collect_queue_rename_parameters(self.connection, queue.id)
            except (BatchQueueError, ValueError):
                self.active_queue_id = None
                return
            self.default_date_var.set(params.start_now_date)
            self.rename_new_accounts = params.new_accounts


    def _build_widgets(self) -> None:
        self._build_menubar()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=(8, 6))
        self.top_region = top
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(9, weight=1)

        self.new_batch_button = icon_button(
            top,
            image=self.icons.get("new"),
            command=self._start_new_batch,
            tooltip=t("tooltip.new"),
        )
        self.new_batch_button.grid(row=0, column=0, padx=(0, 2))
        self.register_button = icon_button(
            top,
            image=self.icons.get("save"),
            command=self._save_batch,
            tooltip=t("tooltip.save"),
        )
        self.register_button.grid(row=0, column=1, padx=(0, 2))
        self.pending_button = icon_button(
            top,
            image=self.icons.get("folder-open"),
            command=self._open_pending_batches,
            tooltip=t("tooltip.open_batches"),
        )
        self.pending_button.grid(row=0, column=2, padx=(0, 8))
        self.execute_button = icon_button(
            top,
            image=self.icons.get("play"),
            command=self._execute,
            tooltip=t("tooltip.execute"),
        )
        self.execute_button.grid(row=0, column=3, padx=(0, 2))
        self.cancel_button = icon_button(
            top,
            image=self.icons.get("stop"),
            command=self._cancel_process,
            tooltip=t("tooltip.stop"),
        )
        self.cancel_button.grid(row=0, column=4, padx=(0, 8))
        self.cancel_button.state(["disabled"])
        self.rename_button = icon_button(
            top,
            image=self.icons.get("rename"),
            command=self._rename_manual_files,
            tooltip=t("tooltip.rename"),
        )
        self.rename_button.grid(row=0, column=5, padx=(0, 2))
        self.rename_button.state(["disabled"])
        self.rename_manual_button = icon_button(
            top,
            image=self.icons.get("terminal"),
            command=self._show_manual_rename_command,
            tooltip=t("tooltip.rename_manual"),
        )
        self.rename_manual_button.grid(row=0, column=6, padx=(0, 12))
        ttk.Label(top, text=t("label.batch_name")).grid(row=0, column=7, sticky="w")
        self.batch_name_entry = ttk.Entry(
            top, textvariable=self.batch_name_var, width=28
        )
        self.batch_name_entry.grid(row=0, column=8, sticky="ew", padx=(6, 12))
        bind_edit_context_menu(self.batch_name_entry)
        ttk.Label(top, text=t("label.date")).grid(row=0, column=9, sticky="e")
        ttk.Label(top, textvariable=self.default_date_var).grid(
            row=0, column=10, sticky="w", padx=(6, 0)
        )

        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.body_region = body
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        catalog_width = _catalog_width_chars(
            entry.username for entry in self.catalog_entries
        )
        catalog = ttk.Frame(body, padding=6)
        body.add(catalog, weight=1)
        self._build_catalog(catalog, width_chars=catalog_width)

        workspace = ttk.PanedWindow(body, orient=tk.VERTICAL)
        editor = ttk.Frame(workspace, padding=6)
        batch = ttk.Frame(workspace, padding=6)
        workspace.add(editor, weight=1)
        workspace.add(batch, weight=1)
        body.add(workspace, weight=4)

        self._build_editor(editor)
        self._build_batch_table(batch)

        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.status_button = ttk.Button(
            bottom,
            textvariable=self.status_bar_var,
            command=self.log_window.toggle,
        )
        self.status_button.grid(row=0, column=0, sticky="ew")
        self.console = tk.Text(bottom, height=1)
        self.clean_console_button = ttk.Button(bottom, command=self._clear_console)



__all__ = ["InstagramOrchestratorApp", "launch_gui"]
