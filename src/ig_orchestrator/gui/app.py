from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
import os
from pathlib import Path
import re
from sqlite3 import Connection
import tkinter as tk
from tkinter import font as tkfont
from tkinter import colorchooser, filedialog, messagebox, ttk
import webbrowser

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
    mark_current_item_completed,
    move_queue_item,
    pause_queue,
    remove_pending_item,
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
from ig_orchestrator.models import AccountHistoryStatus
from ig_orchestrator import __version__
from ig_orchestrator.db.downloaded_files_cleanup import purge_downloaded_files
from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.catalog_colors import (
    colors_for_entry,
    load_catalog_colors,
    save_color,
)
from ig_orchestrator.gui.catalog_tree import build_catalog_tree
from ig_orchestrator.gui.i18n import current_language, load_language, t
from ig_orchestrator.gui.icons import IconSet
from ig_orchestrator.gui.log_window import LogWindow
from ig_orchestrator.gui.theme import apply_light_theme, icon_button
from ig_orchestrator.gui.treeview_sort import bind_treeview_sort


_CATALOG_COLORS = {
    "favorite": "#d9ead3",
    "inactive": "#fff2cc",
    "in_batch": "#f5c08c",
    "today": "#fff59d",
    "disabled": "#f4cccc",
}


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


class InstagramOrchestratorApp:
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
            return
        self.active_queue_id = queue.id
        if queue.status == QueueStatus.AWAITING_RENAME.value and queue.rename_batch_ids:
            self.batch_ready_for_rename = True
            self.rename_button.configure(state="normal")
            try:
                params = collect_queue_rename_parameters(self.connection, queue.id)
            except (BatchQueueError, ValueError):
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
        ttk.Entry(top, textvariable=self.batch_name_var, width=28).grid(
            row=0, column=8, sticky="ew", padx=(6, 12)
        )
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

    def _build_catalog(self, parent: ttk.Frame, *, width_chars: int) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=t("label.catalog")).pack(side=tk.LEFT)
        self.catalog_view_button = icon_button(
            header,
            image=self.icons.get("tree" if self.catalog_view_mode == "list" else "list"),
            command=self._toggle_catalog_view,
            tooltip=t("tooltip.catalog_view"),
        )
        self.catalog_view_button.pack(side=tk.RIGHT)
        filter_row = ttk.Frame(parent)
        filter_row.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        filter_row.columnconfigure(0, weight=1)
        filter_entry = ttk.Entry(filter_row, textvariable=self.catalog_filter_var)
        filter_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            filter_row,
            text="❌",
            width=3,
            command=self._clear_catalog_filter,
        ).grid(row=0, column=1, sticky="e", padx=(4, 0))
        self.catalog_filter_var.trace_add("write", lambda *_: self._refresh_catalog())
        self.catalog_list = tk.Listbox(
            parent,
            exportselection=False,
            width=width_chars,
        )
        self.catalog_list.grid(row=2, column=0, sticky="nsew")
        self.catalog_list.bind(
            "<ButtonRelease-1>", lambda _event: self._load_catalog()
        )
        self.catalog_list.bind(
            "<Double-Button-1>", lambda _event: self._open_and_load_catalog_account()
        )
        self.catalog_list.bind("<Button-3>", self._show_catalog_menu)
        self.catalog_tree = ttk.Treeview(
            parent, show="tree", selectmode="browse"
        )
        self.catalog_tree.grid(row=2, column=0, sticky="nsew")
        self.catalog_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._load_catalog()
        )
        self.catalog_tree.bind(
            "<Double-Button-1>", lambda _event: self._open_and_load_catalog_account()
        )
        self.catalog_tree.bind("<Button-3>", self._show_catalog_menu)
        self._apply_catalog_view_visibility()
        self.catalog_menu = tk.Menu(self.root, tearoff=False)
        self.catalog_menu.add_command(label="Abrir", command=self._open_catalog_account)
        self.catalog_menu.add_separator()
        self.catalog_menu.add_command(
            label="Inactivo", command=self._set_catalog_account_inactive
        )
        self.catalog_menu.add_command(
            label="Favorito", command=lambda: self._set_catalog_account_favorite(True)
        )
        self.catalog_menu.add_command(
            label="Quitar favorito",
            command=lambda: self._set_catalog_account_favorite(False),
        )
        self.catalog_menu.add_separator()
        self.catalog_menu.add_command(label="Delete", command=self._disable_catalog_account)
        self.catalog_menu.add_command(
            label="Activar", command=self._enable_catalog_account
        )

    def _build_batch_table(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        ttk.Label(parent, text=t("label.batch_accounts")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        self.tree = ttk.Treeview(
            parent,
            columns=tuple(column for column, _title in _BATCH_COLUMNS),
            show="headings",
            selectmode="extended",
        )
        style = ttk.Style(self.root)
        tree_font = tkfont.Font(
            root=self.root,
            font=style.lookup("Treeview", "font") or "TkDefaultFont",
        )
        column_samples = _batch_column_samples(
            entry.username for entry in self.catalog_entries
        )
        for column, title in _BATCH_COLUMNS:
            width = tree_font.measure(column_samples[column]) + 16
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=width, anchor="w")
        bind_treeview_sort(
            self.tree,
            tuple(column for column, _title in _BATCH_COLUMNS),
            title_for=lambda column: dict(_BATCH_COLUMNS)[column],
        )
        self.tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6, 6))
        batch_scroll = ttk.Scrollbar(
            parent,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            style="Visible.Vertical.TScrollbar",
        )
        batch_scroll.grid(row=1, column=3, sticky="ns", pady=(6, 6))
        self.tree.configure(yscrollcommand=batch_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_row())
        self.tree.bind("<Button-3>", self._show_batch_menu)
        self.tree.bind(
            "<Double-Button-1>",
            lambda _event: self._open_selected_problem_urls(),
        )
        self.batch_menu = tk.Menu(self.root, tearoff=False)
        self.batch_menu.add_command(
            label="Completar", command=self._complete_selected_account
        )
        self.batch_menu.add_separator()
        self.batch_menu.add_command(
            label="Ver URLs completadas…",
            command=lambda: self._open_account_problem_urls("completed"),
        )
        self.batch_menu.add_command(
            label="Ver URLs en reintento…",
            command=lambda: self._open_account_problem_urls("retry"),
        )
        self.batch_menu.add_command(
            label="Ver URLs fallidas…",
            command=lambda: self._open_account_problem_urls("failed"),
        )
        self.batch_menu.add_separator()
        self.batch_menu.add_command(
            label="Abrir carpeta",
            command=self._open_selected_account_folder,
        )
        self.tree.tag_configure("completed", foreground="#238636")
        self.tree.tag_configure("retry", foreground="#b76e00")
        self.tree.tag_configure("processing", foreground="#0969da")
        self.tree.tag_configure("pending", foreground="#57606a")
        self.tree.tag_configure("failed", foreground="#cf222e")
        # v1.26.5: Subir, Bajar y Duplicar se conservan en los metodos, pero sus
        # botones se ocultan porque el orden visible pasa a ser el de procesamiento.
        self.delete_button = ttk.Button(
            parent, text="Eliminar", command=self._delete_selected
        )
        self.delete_button.grid(row=2, column=0, sticky="ew", padx=(0, 4))
        self.save_selection_button = ttk.Button(
            parent,
            text="Guardar selección",
            command=self._save_selected_accounts_as_batch,
        )
        self.save_selection_button.grid(row=2, column=1, sticky="ew", padx=(0, 4))
        self.delete_all_button = ttk.Button(
            parent,
            text="Eliminar todo",
            command=self._delete_all_accounts,
        )
        self.delete_all_button.grid(row=2, column=2, columnspan=2, sticky="ew")

    def _build_editor(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=t("label.editor")).pack(side=tk.LEFT)
        actions = ttk.Frame(header)
        actions.pack(side=tk.RIGHT)
        icon_button(
            actions,
            image=self.icons.get("clipboard-plus"),
            command=self._paste_and_upsert,
            tooltip=t("tooltip.paste_add"),
        ).pack(side=tk.LEFT, padx=1)
        icon_button(
            actions,
            image=self.icons.get("plus"),
            command=self._upsert_account,
            tooltip=t("tooltip.add_update"),
        ).pack(side=tk.LEFT, padx=1)
        icon_button(
            actions,
            image=self.icons.get("clipboard"),
            command=self._paste_urls,
            tooltip=t("tooltip.paste"),
        ).pack(side=tk.LEFT, padx=1)
        icon_button(
            actions,
            image=self.icons.get("wand"),
            command=self._normalize_urls,
            tooltip=t("tooltip.normalize"),
        ).pack(side=tk.LEFT, padx=1)
        icon_button(
            actions,
            image=self.icons.get("eraser"),
            command=self._clear_editor,
            tooltip=t("tooltip.clear_editor"),
        ).pack(side=tk.LEFT, padx=1)

        fields = ttk.Frame(parent)
        fields.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        parent.rowconfigure(1, weight=1)
        fields.rowconfigure(4, weight=1)
        fields.columnconfigure(1, weight=1)
        ttk.Label(fields, text=t("label.username")).grid(row=0, column=0, sticky="w")
        self.username_combo = ttk.Combobox(
            fields,
            textvariable=self.username_var,
            width=28,
            values=[entry.username for entry in self.catalog_entries],
        )
        self.username_combo.grid(row=0, column=1, sticky="w")
        self.username_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_catalog_date())
        flags = ttk.Frame(fields)
        flags.grid(row=1, column=1, sticky="w", pady=(8, 0))
        # tk.Checkbutton (not ttk): the label text toggles reliably on Windows.
        tk.Checkbutton(
            flags,
            text=t("label.stories"),
            variable=self.stories_var,
            command=self._update_indicators,
        ).pack(side=tk.LEFT)
        tk.Checkbutton(
            flags,
            text=t("label.new_account"),
            variable=self.new_account_var,
            command=self._on_new_account_toggle,
        ).pack(side=tk.LEFT, padx=(12, 0))
        tk.Checkbutton(
            flags,
            text=t("label.update"),
            variable=self.catalog_update_var,
            command=self._on_catalog_update_toggle,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.new_account_frame = ttk.LabelFrame(
            fields,
            text=t("label.new_account_frame"),
            padding=6,
        )
        self.new_account_frame.columnconfigure(1, weight=1)
        ttk.Label(self.new_account_frame, text="ownerId *").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Entry(self.new_account_frame, textvariable=self.owner_id_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )
        self.start_init_date_label = ttk.Label(
            self.new_account_frame, text="startInitDate *"
        )
        self.start_init_date_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.start_init_date_entry = ttk.Entry(
            self.new_account_frame, textvariable=self.start_init_date_var
        )
        self.start_init_date_entry.grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0)
        )
        ttk.Label(self.new_account_frame, text="path *").grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self.destination_path_combo = ttk.Combobox(
            self.new_account_frame,
            textvariable=self.destination_path_var,
            values=self.destination_paths,
        )
        self.destination_path_combo.grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=(6, 0)
        )
        self.new_account_frame.grid(
            row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0)
        )
        self.new_account_frame.grid_remove()

        ttk.Label(fields, text=t("label.urls")).grid(
            row=4, column=0, sticky="nw", pady=(8, 0)
        )
        self.urls_text = tk.Text(fields, height=9, wrap="none")
        self.urls_text.grid(
            row=4, column=1, columnspan=2, sticky="nsew", pady=(8, 0)
        )
        urls_scroll = ttk.Scrollbar(
            fields,
            orient=tk.VERTICAL,
            command=self.urls_text.yview,
            style="Visible.Vertical.TScrollbar",
        )
        urls_scroll.grid(row=4, column=3, sticky="ns", pady=(8, 0))
        self.urls_text.configure(yscrollcommand=urls_scroll.set)
        self.urls_text.bind("<KeyRelease>", lambda _event: self._update_indicators())
        ttk.Label(fields, textvariable=self.indicators_var).grid(
            row=5, column=1, columnspan=2, sticky="w", pady=(6, 0)
        )

    def _on_new_account_toggle(self) -> None:
        if self.new_account_var.get():
            self.catalog_update_var.set(False)
        self._toggle_catalog_metadata_fields()

    def _on_catalog_update_toggle(self) -> None:
        if self.catalog_update_var.get():
            self.new_account_var.set(False)
        self._toggle_catalog_metadata_fields()

    def _toggle_new_account_fields(self) -> None:
        self._toggle_catalog_metadata_fields()

    def _toggle_catalog_metadata_fields(self) -> None:
        if self.new_account_var.get():
            self.new_account_frame.configure(text="Datos de cuenta nueva")
            self.start_init_date_label.grid()
            self.start_init_date_entry.grid()
            self.new_account_frame.grid()
            return
        if self.catalog_update_var.get():
            self.new_account_frame.configure(text="Datos de catálogo (Update)")
            self.start_init_date_label.grid_remove()
            self.start_init_date_entry.grid_remove()
            self.new_account_frame.grid()
            return
        self.new_account_frame.grid_remove()

    def _clear_catalog_filter(self) -> None:
        self.catalog_filter_var.set("")

    def _toggle_catalog_view(self) -> None:
        self._set_catalog_view("tree" if self.catalog_view_mode == "list" else "list")

    def _set_catalog_view(self, mode: str) -> None:
        next_mode = "list" if mode == "list" else "tree"
        if next_mode == self.catalog_view_mode:
            return
        self.catalog_view_mode = next_mode
        self._persist_catalog_view()

    def _persist_catalog_view(self) -> None:
        if is_gui_schema(self.connection):
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('ui.catalog_view', ?, 'TEXT', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (self.catalog_view_mode,),
            )
            self.connection.commit()
        self.catalog_view_button.configure(
            image=self.icons.get("tree" if self.catalog_view_mode == "list" else "list")
        )
        self._apply_catalog_view_visibility()
        self._refresh_catalog()

    def _apply_catalog_view_visibility(self) -> None:
        if self.catalog_view_mode == "tree":
            self.catalog_list.grid_remove()
            self.catalog_tree.grid()
        else:
            self.catalog_tree.grid_remove()
            self.catalog_list.grid()

    def _batch_usernames(self) -> set[str]:
        return {account.username.casefold() for account in self.accounts}

    def _refresh_catalog(self) -> None:
        selected_username = self._selected_catalog_username()
        try:
            yview = self.catalog_list.yview()
        except tk.TclError:
            yview = (0.0, 1.0)

        query = self.catalog_filter_var.get()
        in_batch = self._batch_usernames()
        today = self.today_catalog_usernames
        visible: list[str] = []
        filtered = filter_catalog_entries(self.catalog_entries, query)
        self.catalog_list.delete(0, tk.END)
        palette = getattr(self, "catalog_colors", _CATALOG_COLORS)
        for entry in filtered:
            self.catalog_list.insert(tk.END, entry.username)
            colors = _catalog_entry_colors(
                entry,
                in_batch=entry.username.casefold() in in_batch,
                today=entry.username.casefold() in today,
                palette=palette,
            )
            if colors:
                self.catalog_list.itemconfig(tk.END, **colors)
            visible.append(entry.username)
        self._refresh_catalog_tree(filtered, query=query, in_batch=in_batch, today=today)

        if selected_username is not None:
            try:
                index = visible.index(selected_username)
            except ValueError:
                index = None
            if index is not None:
                self.catalog_list.selection_set(index)
                self.catalog_list.activate(index)
        if yview:
            self.catalog_list.yview_moveto(yview[0])

    def _refresh_catalog_tree(
        self,
        entries,
        *,
        query: str,
        in_batch: set[str],
        today: set[str],
    ) -> None:
        tree = getattr(self, "catalog_tree", None)
        if tree is None:
            return
        selected = self._selected_catalog_username()
        tree.delete(*tree.get_children())
        for key, color in self.catalog_colors.items():
            if color:
                tree.tag_configure(key, background=color)
        roots = build_catalog_tree(list(entries), unrouted_label=t("label.unrouted"))
        match = query.strip().casefold()

        def insert_nodes(parent: str, nodes) -> None:
            for node in nodes:
                if node.is_leaf and node.username:
                    tags: list[str] = []
                    entry = node.entry
                    if entry is not None:
                        colors = _catalog_entry_colors(
                            entry,
                            in_batch=entry.username.casefold() in in_batch,
                            today=entry.username.casefold() in today,
                            palette=self.catalog_colors,
                        )
                        if colors.get("background") == self.catalog_colors.get("disabled"):
                            tags.append("disabled")
                        elif colors.get("background") == self.catalog_colors.get("in_batch"):
                            tags.append("in_batch")
                        elif colors.get("background") == self.catalog_colors.get("today"):
                            tags.append("today")
                        elif colors.get("background") == self.catalog_colors.get("inactive"):
                            tags.append("inactive")
                        elif colors.get("background") == self.catalog_colors.get("favorite"):
                            tags.append("favorite")
                    tree.insert(
                        parent,
                        tk.END,
                        iid=f"user:{node.username}",
                        text=node.username,
                        tags=tuple(tags),
                    )
                    continue
                folder_id = f"folder:{node.path or node.name}"
                tree.insert(parent, tk.END, iid=folder_id, text=node.name)
                insert_nodes(folder_id, node.children)
                if match:
                    tree.item(folder_id, open=True)

        insert_nodes("", roots)
        if selected:
            leaf = f"user:{selected}"
            if tree.exists(leaf):
                tree.selection_set(leaf)
                tree.see(leaf)

    def _show_catalog_menu(self, event: tk.Event) -> None:
        if self.catalog_view_mode == "tree":
            row = self.catalog_tree.identify_row(event.y)
            if not row.startswith("user:"):
                return
            self.catalog_tree.selection_set(row)
            self.catalog_menu.tk_popup(event.x_root, event.y_root)
            return
        index = self.catalog_list.nearest(event.y)
        if index < 0 or index >= self.catalog_list.size():
            return
        self.catalog_list.selection_clear(0, tk.END)
        self.catalog_list.selection_set(index)
        self.catalog_list.activate(index)
        self.catalog_menu.tk_popup(event.x_root, event.y_root)

    def _selected_catalog_username(self) -> str | None:
        if getattr(self, "catalog_view_mode", "list") == "tree":
            tree = getattr(self, "catalog_tree", None)
            if tree is None:
                return None
            selection = tree.selection()
            if not selection:
                return None
            iid = str(selection[0])
            if iid.startswith("user:"):
                return iid[5:]
            return None
        selection = self.catalog_list.curselection()
        if not selection:
            return None
        return str(self.catalog_list.get(selection[0]))

    def _open_catalog_account(self) -> None:
        username = self._selected_catalog_username()
        if username is not None:
            _open_chrome_tab(_instagram_profile_url(username))

    def _open_and_load_catalog_account(self) -> None:
        """Load the selected username into the editor and open its profile."""
        self._load_catalog()
        self._open_catalog_account()

    def _disable_catalog_account(self) -> None:
        username = self._selected_catalog_username()
        if username is None:
            return
        if not messagebox.askyesno(
            "Delete del catalogo",
            f"¿Desactivar @{username} en el catalogo?\n\n"
            "La cuenta se conservara en SQLite con estado DISABLED y "
            "aparecera en rojo al final.",
        ):
            return
        try:
            self.catalog_service.disable(username)
        except ValueError as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        self._reload_catalog()

    def _enable_catalog_account(self) -> None:
        username = self._selected_catalog_username()
        if username is None:
            return
        try:
            self.catalog_service.enable(username)
        except ValueError as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        self._reload_catalog()

    def _set_catalog_account_inactive(self) -> None:
        username = self._selected_catalog_username()
        if username is None:
            return
        try:
            self.catalog_service.set_inactive(username)
        except ValueError as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        self._reload_catalog()

    def _set_catalog_account_favorite(self, favorite: bool) -> None:
        username = self._selected_catalog_username()
        if username is None:
            return
        try:
            self.catalog_service.set_favorite(username, favorite=favorite)
        except ValueError as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        self._reload_catalog()

    def _refresh_today_catalog(self) -> None:
        self.today_catalog_usernames = list_usernames_active_on_date(
            self.connection, date.today()
        )

    def _reload_catalog(self) -> None:
        self.catalog_entries = self.catalog_service.list_entries()
        self._refresh_today_catalog()
        self.username_combo.configure(
            values=[entry.username for entry in self.catalog_entries]
        )
        self._refresh_catalog()

    def _refresh_table(self) -> None:
        selected_usernames = self._selected_batch_usernames()
        expected_ids = {str(index) for index in range(len(self.accounts))}
        for item_id in self.tree.get_children():
            if item_id not in expected_ids:
                self.tree.delete(item_id)
        for index, account in enumerate(self.accounts):
            runtime = self.runtime_progress.get(account.username.casefold())
            status, tag = _account_display_status(account, runtime)
            iid = str(index)
            values = (
                account.username,
                len([url for url in account.urls if url.strip()]),
                status,
                "si" if account.download_stories else "no",
                account.start_now_date or self.default_date_var.get(),
            )
            if self.tree.exists(iid):
                self.tree.item(iid, values=values, tags=(tag,))
                self.tree.move(iid, "", index)
            else:
                self.tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
        self.tree.selection_remove(*self.tree.selection())
        for index, account in enumerate(self.accounts):
            if account.username.casefold() in selected_usernames:
                self.tree.selection_add(str(index))
        if not self.runtime_progress:
            self._set_status(f"{len(self.accounts)} account(s) in draft")

    def _selected_batch_indices(self) -> list[int]:
        return sorted(int(item_id) for item_id in self.tree.selection())

    def _selected_batch_usernames(self) -> set[str]:
        usernames: set[str] = set()
        for index in self._selected_batch_indices():
            if 0 <= index < len(self.accounts):
                usernames.add(self.accounts[index].username.casefold())
        return usernames

    def _toggle_username_sort(self) -> None:
        self._username_sort_ascending = self._username_sort_ascending is not True
        selected = self._selected_batch_usernames()
        # Clear selection before reordering so index-based mapping cannot drift.
        self.tree.selection_remove(*self.tree.selection())
        self.accounts = _sort_accounts_by_username(
            self.accounts,
            ascending=self._username_sort_ascending,
        )
        self.tree.heading(
            "username",
            text=_username_heading_title(self._username_sort_ascending),
            command=self._toggle_username_sort,
        )
        self.selected_index = None
        self._refresh_table()
        for index, account in enumerate(self.accounts):
            if account.username.casefold() in selected:
                self.tree.selection_add(str(index))
        if self.tree.selection():
            focus_id = self.tree.selection()[-1]
            self.tree.focus(focus_id)
            self.selected_index = int(focus_id)

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

    def _load_catalog(self) -> None:
        username = self._selected_catalog_username()
        if not username:
            return
        self.username_var.set(username)
        self._apply_catalog_date()

    def _apply_catalog_date(self) -> None:
        if not self.account_date_var.get().strip():
            self.account_date_var.set(date.today().isoformat())
        username = self.username_var.get().strip().casefold()
        entry = next(
            (
                item
                for item in self.catalog_entries
                if item.username.casefold() == username
            ),
            None,
        )
        if entry is None:
            return
        if entry.owner_id:
            self.owner_id_var.set(entry.owner_id)
        if entry.start_init_date:
            self.start_init_date_var.set(entry.start_init_date)
        if entry.destination_path:
            self.destination_path_var.set(entry.destination_path)

    def _load_selected_row(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        focus = self.tree.focus()
        item_id = focus if focus in selection else selection[-1]
        index = int(item_id)
        if index < 0 or index >= len(self.accounts):
            return
        self.selected_index = index
        account = self.accounts[self.selected_index]
        was_disabled = False
        try:
            was_disabled = str(self.urls_text.cget("state")) == "disabled"
        except (tk.TclError, AttributeError):
            was_disabled = False
        if was_disabled:
            self.urls_text.configure(state="normal")
        self.username_var.set(account.username)
        self.stories_var.set(account.download_stories)
        self.new_account_var.set(account.is_new_account)
        self.catalog_update_var.set(
            account.is_catalog_update and not account.is_new_account
        )
        self.owner_id_var.set(account.owner_id)
        self.start_init_date_var.set(account.start_init_date)
        self.destination_path_var.set(account.destination_path)
        self._toggle_catalog_metadata_fields()
        self.account_date_var.set(account.start_now_date)
        self.urls_text.delete("1.0", tk.END)
        self.urls_text.insert("1.0", "\n".join(account.urls))
        self._update_indicators()
        if was_disabled or getattr(self, "history_readonly", False):
            self.urls_text.configure(state="disabled")

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

    def _editor_account(self) -> AccountDraft:
        urls = self.urls_text.get("1.0", tk.END).splitlines()
        is_new = self.new_account_var.get()
        is_update = self.catalog_update_var.get() and not is_new
        return AccountDraft(
            username=self.username_var.get(),
            download_stories=self.stories_var.get(),
            urls=urls,
            start_now_date=self.account_date_var.get(),
            is_new_account=is_new,
            is_catalog_update=is_update,
            owner_id=self.owner_id_var.get(),
            start_init_date=self.start_init_date_var.get(),
            destination_path=self.destination_path_var.get(),
        )

    def _upsert_account(self) -> None:
        if self._history_guard("agregar o actualizar cuentas"):
            return
        account = self._editor_account()
        try:
            draft = BatchDraft(
                batch_name=self.batch_name_var.get() or "validation",
                default_start_now_date=self.default_date_var.get(),
                accounts=[account],
            )
            from ig_orchestrator.gui.batch_draft_service import validate_batch_draft

            validated = validate_batch_draft(draft).accounts[0]
        except BatchDraftValidationError as exc:
            messagebox.showerror("Validation", str(exc))
            return

        stored = AccountDraft(
            username=validated.username,
            download_stories=validated.download_stories,
            urls=list(validated.urls),
            start_now_date=account.start_now_date.strip(),
            is_new_account=account.is_new_account,
            is_catalog_update=account.is_catalog_update,
            owner_id=account.owner_id.strip(),
            start_init_date=account.start_init_date.strip(),
            destination_path=account.destination_path.strip(),
        )
        try:
            save_catalog_metadata_to_history(stored, self.connection)
        except (BatchDraftValidationError, ValueError) as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        if self.selected_index is None:
            self.accounts.append(stored)
        else:
            self.accounts[self.selected_index] = stored
        if stored.is_new_account or stored.is_catalog_update:
            self.catalog_entries = self.catalog_service.list_entries()
            self.destination_paths = self.catalog_service.list_destination_paths()
            self.username_combo.configure(
                values=[entry.username for entry in self.catalog_entries]
            )
            self.destination_path_combo.configure(values=self.destination_paths)
        self._refresh_table()
        self._refresh_catalog()
        self._clear_editor()

    def _move_selected(self, direction: int) -> None:
        if self.selected_index is None:
            return
        target = self.selected_index + direction
        if target < 0 or target >= len(self.accounts):
            return
        self.accounts[self.selected_index], self.accounts[target] = (
            self.accounts[target],
            self.accounts[self.selected_index],
        )
        self.selected_index = target
        self._refresh_table()
        self.tree.selection_set(str(target))

    def _duplicate_selected(self) -> None:
        if self.selected_index is None:
            return
        account = self.accounts[self.selected_index]
        self.accounts.insert(
            self.selected_index + 1,
            AccountDraft(
                username=account.username,
                download_stories=account.download_stories,
                urls=list(account.urls),
                start_now_date=account.start_now_date,
                is_new_account=account.is_new_account,
                is_catalog_update=account.is_catalog_update,
                owner_id=account.owner_id,
                start_init_date=account.start_init_date,
                destination_path=account.destination_path,
            ),
        )
        self._refresh_table()

    def _delete_selected(self) -> None:
        if self._history_guard("eliminar cuentas"):
            return
        indices = self._selected_batch_indices()
        if not indices and self.selected_index is not None:
            indices = [self.selected_index]
        if not indices:
            return
        if self.process_runner.is_running() and self.active_process_kind == "batch":
            self.selected_index = indices[-1]
            self._fail_selected_running_account()
            return
        for index in reversed(indices):
            if 0 <= index < len(self.accounts):
                del self.accounts[index]
        self.selected_index = None
        self._refresh_table()
        self._refresh_catalog()
        self._clear_editor()

    def _fail_selected_running_account(self) -> None:
        if self.selected_index is None or self.active_batch_id is None:
            return
        account = self.accounts[self.selected_index]
        runtime = self.runtime_progress.get(account.username.casefold())
        if runtime is None:
            messagebox.showwarning(
                "Eliminar cuenta",
                "No se encontro el estado persistido de la cuenta seleccionada.",
            )
            return
        if not messagebox.askyesno(
            "Eliminar cuenta del lote",
            f"¿Marcar @{account.username} como fallida y detener sus URLs pendientes?",
        ):
            return
        try:
            affected = fail_account_manually(
                self.connection,
                batch_id=self.active_batch_id,
                account_id=runtime.account_id,
            )
        except ValueError as exc:
            messagebox.showerror("Eliminar cuenta", str(exc))
            return
        self._write_console(
            f"Cuenta @{account.username} eliminada del procesamiento: "
            f"{affected} URL(s) marcadas FAILED_FINAL.\n"
        )
        self._refresh_runtime_progress()

    def _delete_all_accounts(self) -> None:
        if self._history_guard("eliminar todas las cuentas"):
            return
        if self.saved_batch_id is not None:
            batch_name = self.batch_name_var.get().strip()
            if not messagebox.askyesno(
                "Eliminar todas las cuentas",
                "Se eliminarán todas las cuentas del lote ya registrado con:\n\n"
                f"Nombre: {batch_name}\n"
                f"ID: {self.saved_batch_id}\n\n"
                "El cambio quedará pendiente hasta pulsar «Actualizar lote».",
            ):
                return
        self.accounts.clear()
        self.selected_index = None
        self._refresh_table()
        self._refresh_catalog()
        self._clear_editor()
        if self.saved_batch_id is not None:
            self._set_status(
                f"Todas las cuentas eliminadas; actualiza el lote {self.saved_batch_id}"
            )

    def _start_new_batch(self) -> None:
        """Leave any loaded batch untouched in SQLite and open a clean draft."""

        if self.process_runner.is_running():
            return
        self.history_readonly = False
        self.saved_batch_id = None
        self.saved_draft_signature = None
        self.active_batch_id = None
        self.runtime_progress = {}
        self.batch_ready_for_rename = False
        self.rename_new_accounts = ()
        self.last_run_was_dry_run = False
        self.cancel_requested = False
        self.active_process_kind = None
        self.batch_name_var.set(_suggest_batch_name())
        today = date.today().isoformat()
        self.default_date_var.set(today)
        self.accounts.clear()
        self.selected_index = None
        self.tree.selection_remove(*self.tree.selection())
        self._set_editor_editable(True)
        self._clear_editor()
        self._refresh_table()
        self._refresh_catalog()
        self.account_progress_var.set("Cuentas: -")
        self.item_progress_var.set("Items: -")
        self.rename_button.configure(state="disabled")
        self._update_batch_context()
        self._set_status("Nuevo lote sin registrar")
        self._write_console(
            "Nuevo lote iniciado. El lote anterior permanece sin cambios en SQLite.\n"
        )

    def _history_guard(self, action: str) -> bool:
        """Return True and warn when the UI is in historical read-only mode."""
        if not getattr(self, "history_readonly", False):
            return False
        messagebox.showinfo(
            "Lote histórico",
            f"Este lote está en solo lectura.\n"
            f"No se puede {action}.\n\n"
            "Usa «Nuevo lote» para salir del histórico.",
        )
        return True

    def _clear_editor(self) -> None:
        self.selected_index = None
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)
        self.username_var.set("")
        self.account_date_var.set(date.today().isoformat())
        self.stories_var.set(False)
        self.new_account_var.set(False)
        self.catalog_update_var.set(False)
        self.owner_id_var.set("")
        self.start_init_date_var.set("")
        self.destination_path_var.set("")
        self._toggle_catalog_metadata_fields()
        was_disabled = False
        try:
            was_disabled = str(self.urls_text.cget("state")) == "disabled"
        except (tk.TclError, AttributeError):
            was_disabled = False
        if was_disabled:
            self.urls_text.configure(state="normal")
        self.urls_text.delete("1.0", tk.END)
        if was_disabled or getattr(self, "history_readonly", False):
            self.urls_text.configure(state="disabled")
        self._update_indicators()

    def _focus_urls_end(self) -> None:
        """Keep the caret and viewport at the end of the URLs text."""
        self.urls_text.mark_set(tk.INSERT, tk.END)
        self.urls_text.see(tk.END)
        self.urls_text.focus_set()

    def _paste_urls(self) -> bool:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return False
        self.urls_text.insert(tk.INSERT, text)
        self._focus_urls_end()
        self._update_indicators()
        return True

    def _paste_and_upsert(self) -> None:
        if self._paste_urls():
            self._upsert_account()

    def _normalize_urls(self) -> None:
        urls = normalize_url_lines(self.urls_text.get("1.0", tk.END).splitlines())
        self.urls_text.delete("1.0", tk.END)
        self.urls_text.insert("1.0", "\n".join(urls))
        self._focus_urls_end()
        self._update_indicators()

    def _update_indicators(self) -> None:
        account = self._editor_account()
        try:
            summary = inspect_account_draft(
                account,
                default_start_now_date=self.default_date_var.get(),
            )
        except BatchDraftValidationError as exc:
            self.indicators_var.set(str(exc))
            return
        types = ", ".join(summary.publication_types) or "-"
        self.indicators_var.set(
            f"URLs: {summary.url_count} | duplicadas: {summary.duplicate_count} | "
            f"invalidas: {len(summary.invalid_urls)} | tipos: {types}"
        )

    def _open_pending_batches(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Lotes guardados y ejecuciones")
        dialog.geometry("1100x620")
        dialog.transient(self.root)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        self._batches_dialog = dialog

        def _clear_dialog_ref(_event=None) -> None:
            if self._batches_dialog is dialog:
                self._batches_dialog = None
                self._refresh_queue_panel = None

        dialog.bind("<Destroy>", _clear_dialog_ref)

        ttk.Label(
            dialog,
            text=(
                "Activos: GUARDADO, ejecuciones y POR RENOMBRAR. "
                "Históricos: lotes COMPLETED (solo lectura). "
                "Selecciona 2 o más lotes para armar una cola y ejecutarlos "
                "en secuencia. Importar crea un lote nuevo en esta instancia."
            ),
            padding=(10, 10, 10, 4),
        ).grid(row=0, column=0, sticky="w")

        notebook = ttk.Notebook(dialog)
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)

        active_tab = ttk.Frame(notebook)
        history_tab = ttk.Frame(notebook)
        notebook.add(active_tab, text="Activos")
        notebook.add(history_tab, text="Históricos")
        for tab in (active_tab, history_tab):
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)

        columns = ("date", "name", "id", "status", "urls", "progress")
        column_defs = (
            ("date", "Fecha", 170, "w"),
            ("name", "Nombre", 240, "w"),
            ("id", "Batch ID", 75, "w"),
            ("status", "Estado", 120, "w"),
            ("urls", "URLs", 70, "e"),
            ("progress", "Cuentas", 250, "w"),
        )

        def make_tree(parent: ttk.Frame, *, selectmode: str = "browse") -> ttk.Treeview:
            tree = ttk.Treeview(
                parent,
                columns=columns,
                show="headings",
                selectmode=selectmode,
            )
            for column, title, width, anchor in column_defs:
                tree.heading(column, text=title)
                tree.column(column, width=width, anchor=anchor)
            tree.grid(row=0, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(
                parent,
                orient=tk.VERTICAL,
                command=tree.yview,
                style="Visible.Vertical.TScrollbar",
            )
            scroll.grid(row=0, column=1, sticky="ns")
            tree.configure(yscrollcommand=scroll.set)
            return tree

        active_tree = make_tree(active_tab, selectmode="extended")
        history_tree = make_tree(history_tab)
        active_empty = ttk.Label(
            active_tab,
            text="No hay lotes guardados ni ejecuciones pendientes.",
        )
        history_empty = ttk.Label(
            history_tab,
            text=(
                "No hay lotes históricos todavía. "
                "Los lotes aparecen aquí al completarse o finalizarse."
            ),
        )
        history_loaded = {"done": False}

        def progress_text(summary) -> str:
            if summary.is_draft:
                return f"{summary.total_accounts} cuentas editables"
            if summary.is_awaiting_rename:
                return (
                    f"{summary.completed_accounts}/{summary.total_accounts} "
                    "listas; pendiente renombrar o finalizar"
                )
            if summary.is_completed:
                return (
                    f"{summary.completed_accounts}/{summary.total_accounts} "
                    "cuentas en el lote cerrado"
                )
            return (
                f"{summary.completed_accounts}/{summary.total_accounts} completas; "
                f"{summary.retry_accounts} reintento; "
                f"{summary.remaining_accounts} por terminar"
            )

        def fill_tree(tree: ttk.Treeview, rows, empty_label: ttk.Label) -> None:
            for item in tree.get_children():
                tree.delete(item)
            for summary in rows:
                tree.insert(
                    "",
                    tk.END,
                    iid=str(summary.batch_id),
                    values=(
                        summary.batch_date,
                        summary.batch_name,
                        summary.batch_id,
                        summary.display_status,
                        summary.url_count,
                        progress_text(summary),
                    ),
                )
            if rows:
                empty_label.place_forget()
            else:
                empty_label.place(relx=0.48, rely=0.48, anchor="center")

        def reload_active() -> list:
            rows = list_managed_batches(self.connection)
            fill_tree(active_tree, rows, active_empty)
            notebook.tab(0, text=f"Activos ({len(rows)})")
            return rows

        def reload_history() -> list:
            rows = list_historical_batches(self.connection)
            fill_tree(history_tree, rows, history_empty)
            notebook.tab(1, text=f"Históricos ({len(rows)})")
            history_loaded["done"] = True
            return rows

        def current_is_history() -> bool:
            return notebook.index(notebook.select()) == 1

        def selected_batch_id_from(tree: ttk.Treeview) -> int | None:
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(
                    "Lotes",
                    "Selecciona primero un lote.",
                    parent=dialog,
                )
                return None
            return int(selection[0])

        def selected_active_batch_ids() -> list[int]:
            selection = active_tree.selection()
            if not selection:
                messagebox.showwarning(
                    "Cola",
                    "Selecciona uno o más lotes activos.",
                    parent=dialog,
                )
                return []
            return [int(item_id) for item_id in selection]

        def selected_active_summary():
            batch_id = selected_batch_id_from(active_tree)
            if batch_id is None:
                return None
            return next(
                (
                    item
                    for item in list_managed_batches(self.connection)
                    if item.batch_id == batch_id
                ),
                None,
            )

        def selected_history_summary():
            batch_id = selected_batch_id_from(history_tree)
            if batch_id is None:
                return None
            return next(
                (
                    item
                    for item in list_historical_batches(self.connection)
                    if item.batch_id == batch_id
                ),
                None,
            )

        def recover_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            if not summary.is_draft:
                messagebox.showwarning(
                    "Recuperar lote",
                    "Una ejecucion ya iniciada no se puede editar. "
                    "Usa Reanudar / Ejecutar o Renombrar segun el estado.",
                    parent=dialog,
                )
                return
            try:
                draft = load_batch_draft(self.connection, summary.batch_id)
            except ValueError as exc:
                messagebox.showerror("Recuperar lote", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load_persisted_draft(summary.batch_id, draft)
            self._write_console(
                f"Lote guardado {summary.batch_id} abierto para modificacion.\n"
            )

        def resume_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            if summary.is_awaiting_rename:
                messagebox.showwarning(
                    "Reanudar lote",
                    "Este lote esta POR RENOMBRAR. Usa Renombrar o "
                    "Finalizar sin renombrar.",
                    parent=dialog,
                )
                return
            batch_id = summary.batch_id
            try:
                draft = load_batch_draft(self.connection, batch_id)
            except ValueError as exc:
                messagebox.showerror("Reanudar lote", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load_persisted_draft(batch_id, draft)
            self._start_batch(batch_id)

        def delete_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            if not summary.is_draft:
                messagebox.showwarning(
                    "Borrar lote",
                    "Solo se pueden borrar lotes GUARDADOS que nunca se hayan ejecutado.",
                    parent=dialog,
                )
                return
            if not messagebox.askyesno(
                "Borrar lote guardado",
                f"Borrar definitivamente el lote guardado {summary.batch_name} "
                f"(id={summary.batch_id})?",
                parent=dialog,
            ):
                return
            try:
                delete_draft_batch(self.connection, summary.batch_id)
            except ValueError as exc:
                messagebox.showerror("Borrar lote", str(exc), parent=dialog)
                return
            if self.saved_batch_id == summary.batch_id:
                self._start_new_batch()
            reload_active()
            self._update_pending_button_label()

        def finish_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            batch_id = summary.batch_id
            if summary.is_draft:
                messagebox.showwarning(
                    "Finalizar sin renombrar",
                    "Un lote GUARDADO todavia no es una ejecucion. "
                    "Si se ejecuto en otra instancia, usa "
                    "Ejecutado en otra instancia.",
                    parent=dialog,
                )
                return
            if not messagebox.askyesno(
                "Finalizar sin renombrar",
                f"Dar por finalizado el batch {batch_id} sin renombrar?\n\n"
                "Pasara a COMPLETED y no volvera a aparecer en pendientes. "
                "Los datos y archivos no se eliminaran.",
                parent=dialog,
            ):
                return
            try:
                finish_batch(self.connection, batch_id)
            except ValueError as exc:
                messagebox.showerror("Finalizar sin renombrar", str(exc), parent=dialog)
                return
            if self.active_batch_id == batch_id:
                self.batch_ready_for_rename = False
                self.rename_button.configure(state="disabled")
            self._write_console(
                f"Batch {batch_id} marcado como COMPLETED (sin renombrar).\n"
            )
            reload_active()
            if history_loaded["done"]:
                reload_history()
            self._update_pending_button_label()

        def mark_elsewhere_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            if summary.is_awaiting_rename:
                messagebox.showinfo(
                    "Ejecutado en otra instancia",
                    "Este lote ya esta POR RENOMBRAR.",
                    parent=dialog,
                )
                return
            if not messagebox.askyesno(
                "Ejecutado en otra instancia",
                f"Marcar el lote {summary.batch_name} (id={summary.batch_id}) "
                "como ejecutado en otra instancia?\n\n"
                "Dejara de ser pendiente de descarga y pasara a POR RENOMBRAR "
                "(puedes renombrar o finalizar sin renombrar).",
                parent=dialog,
            ):
                return
            try:
                mark_batch_executed_elsewhere(self.connection, summary.batch_id)
            except ValueError as exc:
                messagebox.showerror(
                    "Ejecutado en otra instancia",
                    str(exc),
                    parent=dialog,
                )
                return
            self._write_console(
                f"Batch {summary.batch_id} marcado como AWAITING_RENAME "
                "(ejecutado en otra instancia).\n"
            )
            reload_active()
            self._update_pending_button_label()

        def rename_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            batch_id = summary.batch_id
            if not is_batch_ready_for_rename(self.connection, batch_id):
                messagebox.showwarning(
                    "Renombrar",
                    "Este lote aun no esta listo para renombrar. "
                    "Debe estar POR RENOMBRAR o con todas las cuentas completadas.",
                    parent=dialog,
                )
                return
            try:
                draft = load_batch_draft(self.connection, batch_id)
            except ValueError as exc:
                messagebox.showerror("Renombrar", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load_persisted_draft(batch_id, draft)
            # Recovered awaiting-rename lots are not editable drafts.
            self.saved_batch_id = None
            self.saved_draft_signature = None
            self.active_batch_id = batch_id
            self.batch_ready_for_rename = True
            self._update_batch_context()
            self.rename_button.configure(state="normal")
            self._write_console(
                f"Lote {batch_id} cargado para renombrar. "
                "Pulsa Renombrar en la ventana principal.\n"
            )
            self._rename_manual_files()

        def export_selected_active() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            _export_summary(summary)

        def export_selected_history() -> None:
            summary = selected_history_summary()
            if summary is None:
                return
            _export_summary(summary)

        def _export_summary(summary) -> None:
            path = filedialog.asksaveasfilename(
                parent=dialog,
                title="Exportar lote",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
                initialfile=f"{summary.batch_name}.json",
            )
            if not path:
                return
            try:
                export_batch_to_path(self.connection, summary.batch_id, Path(path))
            except (OSError, ValueError, BatchTransferError) as exc:
                messagebox.showerror("Exportar lote", str(exc), parent=dialog)
                return
            self._write_console(f"Lote {summary.batch_id} exportado a {path}\n")
            messagebox.showinfo(
                "Exportar lote",
                f"Lote exportado:\n{path}",
                parent=dialog,
            )

        def import_batch() -> None:
            path = filedialog.askopenfilename(
                parent=dialog,
                title="Importar lote",
                filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
            )
            if not path:
                return
            try:
                result = import_batch_from_path(
                    self.connection,
                    Path(path),
                    settings=self.settings,
                )
            except (OSError, ValueError, BatchTransferError) as exc:
                messagebox.showerror("Importar lote", str(exc), parent=dialog)
                return
            self._write_console(
                f"Lote importado como DRAFT id={result.batch.id} "
                f"nombre={result.batch.batch_name} desde {path}\n"
            )
            reload_active()
            self._update_pending_button_label()
            messagebox.showinfo(
                "Importar lote",
                f"Importado como lote guardado id={result.batch.id}\n"
                f"Nombre: {result.batch.batch_name}",
                parent=dialog,
            )

        def open_history_selected() -> None:
            summary = selected_history_summary()
            if summary is None:
                return
            try:
                draft = load_batch_draft(self.connection, summary.batch_id)
            except ValueError as exc:
                messagebox.showerror("Abrir histórico", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load_historical_batch(summary.batch_id, draft)

        queue_frame = ttk.LabelFrame(dialog, text="Cola de ejecución", padding=8)
        queue_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 4))
        queue_frame.columnconfigure(0, weight=1)
        queue_tree = ttk.Treeview(
            queue_frame,
            columns=("order", "name", "id", "item_status", "batch_status"),
            show="headings",
            height=4,
            selectmode="browse",
        )
        for column, title, width, anchor in (
            ("order", "#", 40, "e"),
            ("name", "Lote", 280, "w"),
            ("id", "ID", 60, "e"),
            ("item_status", "En cola", 110, "w"),
            ("batch_status", "Lote", 130, "w"),
        ):
            queue_tree.heading(column, text=title)
            queue_tree.column(column, width=width, anchor=anchor)
        queue_tree.grid(row=0, column=0, sticky="nsew")
        queue_scroll = ttk.Scrollbar(
            queue_frame,
            orient=tk.VERTICAL,
            command=queue_tree.yview,
            style="Visible.Vertical.TScrollbar",
        )
        queue_scroll.grid(row=0, column=1, sticky="ns")
        queue_tree.configure(yscrollcommand=queue_scroll.set)
        queue_buttons = ttk.Frame(queue_frame)
        queue_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        def selected_queue_item_id() -> int | None:
            selection = queue_tree.selection()
            if not selection:
                messagebox.showwarning(
                    "Cola",
                    "Selecciona un lote de la cola.",
                    parent=dialog,
                )
                return None
            return int(selection[0])

        def refresh_queue_panel() -> None:
            for item in queue_tree.get_children():
                queue_tree.delete(item)
            queue = get_open_queue(self.connection)
            if queue is None:
                self.active_queue_id = None
                return
            self.active_queue_id = queue.id
            visible_index = 0
            for item in queue.items:
                if item.is_removed:
                    continue
                visible_index += 1
                queue_tree.insert(
                    "",
                    tk.END,
                    iid=str(item.id),
                    values=(
                        visible_index,
                        item.batch_name,
                        item.batch_id,
                        item.status,
                        item.batch_status,
                    ),
                )

        self._refresh_queue_panel = refresh_queue_panel

        def add_selected_to_queue() -> None:
            batch_ids = selected_active_batch_ids()
            if not batch_ids:
                return
            try:
                queue = add_batches_to_open_queue(self.connection, batch_ids)
            except BatchQueueError as exc:
                messagebox.showerror("Cola", str(exc), parent=dialog)
                return
            self.active_queue_id = queue.id
            refresh_queue_panel()
            self._write_console(
                f"Cola {queue.id}: {len(queue.items)} lote(s) en secuencia.\n"
            )

        def remove_selected_from_queue() -> None:
            item_id = selected_queue_item_id()
            if item_id is None:
                return
            try:
                remove_pending_item(self.connection, item_id)
            except BatchQueueError as exc:
                messagebox.showerror("Cola", str(exc), parent=dialog)
                return
            refresh_queue_panel()
            if self.process_runner.is_running() and self.active_queue_id is not None:
                self._write_console(
                    "Lote pendiente quitado de la cola; la secuencia "
                    "continuará con los que queden.\n"
                )

        def move_selected_queue_item(direction: int) -> None:
            item_id = selected_queue_item_id()
            if item_id is None:
                return
            try:
                move_queue_item(self.connection, item_id, direction=direction)
            except BatchQueueError as exc:
                messagebox.showerror("Cola", str(exc), parent=dialog)
                return
            refresh_queue_panel()
            queue_tree.selection_set(str(item_id))

        def run_queue_selected() -> None:
            queue = get_open_queue(self.connection)
            if queue is None or not queue.pending_items and queue.running_item is None:
                messagebox.showwarning(
                    "Ejecutar secuencia",
                    "Añade al menos un lote ejecutable a la cola.",
                    parent=dialog,
                )
                return
            try:
                self._start_queue_sequence(queue.id)
            except BatchQueueError as exc:
                messagebox.showerror("Ejecutar secuencia", str(exc), parent=dialog)

        def rename_queue_selected() -> None:
            queue = get_open_queue(self.connection)
            batch_ids: list[int] = []
            if queue is not None and queue.rename_batch_ids:
                batch_ids = list(queue.rename_batch_ids)
                self.active_queue_id = queue.id
            else:
                selected = selected_active_batch_ids()
                if len(selected) < 2:
                    messagebox.showwarning(
                        "Renombrar cola",
                        "Selecciona una cola o al menos dos lotes POR RENOMBRAR.",
                        parent=dialog,
                    )
                    return
                try:
                    queue = add_batches_to_open_queue(self.connection, selected)
                except BatchQueueError as exc:
                    messagebox.showerror("Renombrar cola", str(exc), parent=dialog)
                    return
                batch_ids = list(queue.rename_batch_ids)
                self.active_queue_id = queue.id
            if not batch_ids:
                messagebox.showwarning(
                    "Renombrar cola",
                    "No hay lotes en la cola listos para renombrar.",
                    parent=dialog,
                )
                return
            for batch_id in batch_ids:
                if not is_batch_ready_for_rename(self.connection, batch_id):
                    messagebox.showwarning(
                        "Renombrar cola",
                        f"El lote {batch_id} aún no está listo para renombrar.",
                        parent=dialog,
                    )
                    return
            try:
                draft = load_batch_draft(self.connection, batch_ids[0])
            except ValueError as exc:
                messagebox.showerror("Renombrar cola", str(exc), parent=dialog)
                return
            self._load_persisted_draft(batch_ids[0], draft)
            self.saved_batch_id = None
            self.saved_draft_signature = None
            self.active_batch_id = batch_ids[0]
            self.batch_ready_for_rename = True
            self._update_batch_context()
            self.rename_button.configure(state="normal")
            refresh_queue_panel()
            self._write_console(
                f"Cola {self.active_queue_id}: renombrado combinado de "
                f"{len(batch_ids)} lote(s). Pulsa Renombrar o espera el arranque.\n"
            )
            self._rename_manual_files()

        ttk.Button(
            queue_buttons, text="Añadir a cola", command=add_selected_to_queue
        ).pack(side=tk.LEFT)
        ttk.Button(
            queue_buttons, text="Quitar de cola", command=remove_selected_from_queue
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            queue_buttons, text="Subir", command=lambda: move_selected_queue_item(-1)
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            queue_buttons, text="Bajar", command=lambda: move_selected_queue_item(1)
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            queue_buttons, text="Ejecutar secuencia", command=run_queue_selected
        ).pack(side=tk.RIGHT)
        ttk.Button(
            queue_buttons,
            text="Renombrar cola / selección",
            command=rename_queue_selected,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        active_actions = ttk.Frame(dialog, padding=10)
        history_actions = ttk.Frame(dialog, padding=10)
        active_actions.grid(row=3, column=0, sticky="ew")

        def show_active_actions() -> None:
            history_actions.grid_remove()
            active_actions.grid(row=3, column=0, sticky="ew")
            queue_frame.grid()

        def show_history_actions() -> None:
            active_actions.grid_remove()
            queue_frame.grid_remove()
            history_actions.grid(row=3, column=0, sticky="ew")
            if not history_loaded["done"]:
                reload_history()

        def on_tab_changed(_event=None) -> None:
            if current_is_history():
                show_history_actions()
            else:
                show_active_actions()

        ttk.Button(active_actions, text="Reanudar / Ejecutar", command=resume_selected).pack(
            side=tk.RIGHT
        )
        ttk.Button(
            active_actions, text="Recuperar / Modificar", command=recover_selected
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(active_actions, text="Renombrar", command=rename_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(
            active_actions,
            text="Finalizar sin renombrar",
            command=finish_selected,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(
            active_actions,
            text="Ejecutado en otra instancia",
            command=mark_elsewhere_selected,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(active_actions, text="Exportar", command=export_selected_active).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(active_actions, text="Importar", command=import_batch).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(active_actions, text="Borrar lote", command=delete_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(active_actions, text="Cerrar", command=dialog.destroy).pack(side=tk.LEFT)

        ttk.Button(
            history_actions,
            text="Abrir (solo lectura)",
            command=open_history_selected,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            history_actions,
            text="Exportar",
            command=export_selected_history,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(history_actions, text="Cerrar", command=dialog.destroy).pack(
            side=tk.LEFT
        )

        active_tree.bind("<Double-Button-1>", lambda _event: resume_selected())
        history_tree.bind("<Double-Button-1>", lambda _event: open_history_selected())
        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

        managed = reload_active()
        notebook.tab(1, text="Históricos")
        show_active_actions()
        refresh_queue_panel()
        if not managed:
            active_empty.place(relx=0.48, rely=0.48, anchor="center")

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

    def _set_editor_editable(self, editable: bool) -> None:
        state = "normal" if editable else "disabled"
        username_combo = getattr(self, "username_combo", None)
        if username_combo is not None:
            try:
                username_combo.configure(state="normal" if editable else "disabled")
            except tk.TclError:
                pass
        urls_text = getattr(self, "urls_text", None)
        if urls_text is not None:
            try:
                urls_text.configure(state=state)
            except tk.TclError:
                pass

    def _load_persisted_draft(self, batch_id: int, draft: BatchDraft) -> None:
        self.history_readonly = False
        self.batch_name_var.set(draft.batch_name)
        self.default_date_var.set(draft.default_start_now_date)
        self.accounts = list(draft.accounts)
        self.selected_index = None
        self.saved_batch_id = batch_id
        self.saved_draft_signature = _draft_signature(draft)
        self.active_batch_id = batch_id
        self.rename_new_accounts = _new_account_rename_parameters(self.accounts)
        self._set_editor_editable(True)
        self._clear_editor()
        self.tree.selection_remove(*self.tree.selection())
        self._refresh_runtime_progress()
        self._refresh_catalog()
        self._update_batch_context()
        self._write_console(
            f"Lote {batch_id} recuperado desde SQLite: {draft.batch_name}.\n"
        )

    def _load_historical_batch(self, batch_id: int, draft: BatchDraft) -> None:
        """Open a COMPLETED batch for inspection only."""
        self.history_readonly = True
        self.batch_name_var.set(draft.batch_name)
        self.default_date_var.set(draft.default_start_now_date)
        self.accounts = list(draft.accounts)
        self.selected_index = None
        self.saved_batch_id = None
        self.saved_draft_signature = None
        self.active_batch_id = batch_id
        self.batch_ready_for_rename = False
        self.rename_new_accounts = _new_account_rename_parameters(self.accounts)
        self._set_editor_editable(True)
        self._clear_editor()
        self._set_editor_editable(False)
        self.tree.selection_remove(*self.tree.selection())
        self._refresh_runtime_progress()
        self._refresh_catalog()
        self._update_batch_context()
        self._set_status(f"Histórico solo lectura id {batch_id}")
        self._write_console(
            f"Histórico abierto (solo lectura): {draft.batch_name} "
            f"(id={batch_id}, COMPLETED).\n"
            "Puedes inspeccionar cuentas, URLs y carpetas. "
            "Usa «Nuevo lote» para salir.\n"
        )

    def _save_batch(self, *, show_confirmation: bool = True) -> int | None:
        if self._history_guard("registrar o actualizar el lote"):
            return None
        draft = BatchDraft(
            batch_name=self.batch_name_var.get(),
            default_start_now_date=self.default_date_var.get(),
            accounts=list(self.accounts),
        )
        try:
            result = save_batch_draft(
                draft,
                self.connection,
                settings=self.settings,
                batch_id=self.saved_batch_id,
            )
        except BatchDraftValidationError as exc:
            messagebox.showerror("Validation", str(exc))
            return None
        except ValueError as exc:
            messagebox.showerror("SQLite", str(exc))
            return None

        self.saved_batch_id = result.batch.id
        self.active_batch_id = result.batch.id
        self.saved_draft_signature = _draft_signature(draft)
        self._refresh_runtime_progress()
        self._refresh_today_catalog()
        self._refresh_catalog()
        self._update_batch_context()
        self._write_console(
            f"Lote guardado: {result.batch.batch_name} (id={result.batch.id}, estado=DRAFT)\n"
            f"SQLite database: {self.settings.sqlite_db_path}\n"
        )
        self._set_status(f"Lote guardado id {result.batch.id}")
        self._update_pending_button_label()
        if show_confirmation:
            messagebox.showinfo("Lote registrado", f"Lote registrado con id {result.batch.id}")
        return result.batch.id

    def _save_selected_accounts_as_batch(self) -> None:
        """Persist only the tree selection as a DRAFT and leave the rest in memory."""
        if self._history_guard("guardar selección"):
            return


        if self.process_runner.is_running():
            return
        indices = self._selected_batch_indices()
        if not indices:
            messagebox.showwarning(
                "Guardar selección",
                "Selecciona al menos una cuenta del lote actual "
                "(Ctrl o Shift + click para varias).",
            )
            return
        selected_accounts = [self.accounts[index] for index in indices]
        batch_name = self.batch_name_var.get().strip() or _suggest_batch_name()
        if not messagebox.askyesno(
            "Guardar selección",
            f"¿Guardar un lote con {len(selected_accounts)} cuenta(s) seleccionada(s)?\n\n"
            f"Nombre: {batch_name}\n\n"
            "Las cuentas guardadas saldrán de la tabla. "
            "Las no seleccionadas permanecen para otro lote.",
        ):
            return

        draft = BatchDraft(
            batch_name=batch_name,
            default_start_now_date=self.default_date_var.get(),
            accounts=list(selected_accounts),
        )
        # If editing a registered DRAFT, that id receives the selection.
        # Remaining rows become a new unregistered working set.
        try:
            result = save_batch_draft(
                draft,
                self.connection,
                settings=self.settings,
                batch_id=self.saved_batch_id,
            )
        except BatchDraftValidationError as exc:
            messagebox.showerror("Validation", str(exc))
            return
        except ValueError as exc:
            messagebox.showerror("SQLite", str(exc))
            return

        for index in reversed(indices):
            del self.accounts[index]

        remaining = len(self.accounts)
        self.saved_batch_id = None
        self.saved_draft_signature = None
        self.active_batch_id = None
        self.runtime_progress = {}
        self.selected_index = None
        self._username_sort_ascending = None
        self.tree.heading("username", text="Username")
        self.batch_name_var.set(_suggest_batch_name())
        self._clear_editor()
        self._refresh_table()
        self._refresh_today_catalog()
        self._refresh_catalog()
        self._update_batch_context()
        self._update_pending_button_label()
        self._write_console(
            f"Selección guardada como lote {result.batch.batch_name} "
            f"(id={result.batch.id}, estado=DRAFT); "
            f"{remaining} cuenta(s) quedan en la mesa de trabajo.\n"
        )
        self._set_status(
            f"Selección guardada id {result.batch.id}; quedan {remaining} en mesa"
        )
        messagebox.showinfo(
            "Selección guardada",
            f"Lote id {result.batch.id} con {len(selected_accounts)} cuenta(s).\n"
            f"Quedan {remaining} cuenta(s) en la mesa de trabajo.",
        )

    def _execute(self) -> None:
        if self._history_guard("ejecutar el lote"):
            return
        if self.process_runner.is_running():
            return

        draft = BatchDraft(
            batch_name=self.batch_name_var.get(),
            default_start_now_date=self.default_date_var.get(),
            accounts=list(self.accounts),
        )
        if not draft.accounts:
            messagebox.showerror(
                "Ejecución",
                "No se puede ejecutar un lote vacío. Agrega al menos una cuenta.",
            )
            return
        batch_id = (
            self.saved_batch_id
            if self.saved_batch_id is not None
            and self.saved_draft_signature == _draft_signature(draft)
            else self._save_batch(show_confirmation=False)
        )
        if batch_id is None:
            return

        self._start_batch(batch_id)

    def _start_queue_sequence(self, queue_id: int) -> None:
        if self.process_runner.is_running():
            raise BatchQueueError("Ya hay un proceso en ejecución")
        item = start_or_resume_queue(self.connection, queue_id)
        self.active_queue_id = queue_id
        self._write_console(
            f"Secuencia de cola {queue_id}: ejecutando lote "
            f"{item.batch_id} ({item.batch_name}).\n"
        )
        if self._refresh_queue_panel is not None:
            self._refresh_queue_panel()
        self._start_batch(item.batch_id)

    def _continue_queue_after_batch(self, *, cancelled: bool, exit_code: int) -> bool:
        """Advance the persisted queue. Return True if another batch was started."""
        if self.active_queue_id is None:
            return False
        queue_id = self.active_queue_id
        if cancelled or exit_code != 0:
            pause_queue(self.connection, queue_id)
            if self._refresh_queue_panel is not None:
                self._refresh_queue_panel()
            self._write_console(
                f"Cola {queue_id} en pausa. Los lotes pendientes se pueden "
                "quitar o la secuencia se puede reanudar.\n"
            )
            return False
        if self.last_run_was_dry_run:
            pause_queue(self.connection, queue_id)
            if self._refresh_queue_panel is not None:
                self._refresh_queue_panel()
            return False
        next_item = mark_current_item_completed(self.connection, queue_id)
        if self._refresh_queue_panel is not None:
            self._refresh_queue_panel()
        if next_item is None:
            self.batch_ready_for_rename = True
            self.rename_button.configure(state="normal")
            try:
                params = collect_queue_rename_parameters(self.connection, queue_id)
            except BatchQueueError as exc:
                self._write_console(f"Cola {queue_id} lista para renombrar: {exc}\n")
                return False
            self.rename_new_accounts = params.new_accounts
            self.default_date_var.set(params.start_now_date)
            self._write_console(
                f"Cola {queue_id} terminada. Renombrar usará "
                f"{len(params.batch_ids)} lote(s), startNowDate "
                f"{params.start_now_date} y {len(params.new_accounts)} "
                "cuenta(s) nueva(s).\n"
            )
            if params.has_mixed_dates:
                self._write_console(
                    "Aviso: los lotes tenían startNowDate distintos; "
                    "se usó la fecha más reciente.\n"
                )
            return False
        self._write_console(
            f"Cola {queue_id}: siguiente lote {next_item.batch_id} "
            f"({next_item.batch_name}).\n"
        )
        try:
            self._start_queue_sequence(queue_id)
        except BatchQueueError as exc:
            self._write_console(f"No se pudo continuar la cola: {exc}\n")
            return False
        return True

    def _start_batch(self, batch_id: int) -> None:
        if self.process_runner.is_running():
            return

        try:
            activate_draft_batch(self.connection, batch_id)
        except ValueError as exc:
            messagebox.showerror("Ejecucion", str(exc))
            return
        if self.saved_batch_id == batch_id:
            self.saved_batch_id = None

        # SQLite already contains the stable processing order and the complete
        # rename metadata. Rehydrate before every start/resume so the GUI never
        # relies on a stale in-memory draft.
        try:
            persisted_draft = load_batch_draft(self.connection, batch_id)
        except ValueError as exc:
            messagebox.showerror("Ejecucion", str(exc))
            return
        self.batch_name_var.set(persisted_draft.batch_name)
        self.default_date_var.set(persisted_draft.default_start_now_date)
        self.accounts = list(persisted_draft.accounts)
        self.saved_draft_signature = _draft_signature(persisted_draft)
        self.selected_index = None
        self.runtime_progress = {}
        self._clear_editor()
        self.tree.selection_remove(*self.tree.selection())
        self._refresh_table()
        self._refresh_catalog()

        self.batch_ready_for_rename = False
        self.rename_new_accounts = _new_account_rename_parameters(self.accounts)
        self.last_run_was_dry_run = False
        self.active_batch_id = batch_id
        self._update_batch_context()
        self.cancel_requested = False
        self.active_process_kind = "batch"
        self.rename_button.configure(state="disabled")
        command = build_run_continue_command(batch_id, dry_run=self.last_run_was_dry_run)
        self._write_console(
            f"Ejecutando lote {batch_id}: {' '.join(command)}\n"
        )
        self.account_progress_var.set("Cuentas: iniciando...")
        self.item_progress_var.set("Items: iniciando...")
        self._set_process_running(True)
        try:
            self.process_runner.start(
                command,
                on_output=lambda line: self.root.after(
                    0, self._handle_process_output, line
                ),
                on_complete=lambda exit_code: self.root.after(
                    0, self._handle_process_complete, batch_id, exit_code
                ),
                extra_env={
                    "SQLITE_DB_PATH": str(self.settings.sqlite_gui_db_path),
                },
            )
            self._schedule_progress_poll()
        except (OSError, RuntimeError) as exc:
            self._set_process_running(False)
            messagebox.showerror("Ejecucion", str(exc))

    def _handle_process_output(self, line: str) -> None:
        account_match = _ACCOUNT_PROGRESS_RE.search(line)
        if account_match:
            self.account_progress_var.set(
                f"Cuentas: {account_match.group('percentage')}% "
                f"({account_match.group('current')}/{account_match.group('total')})"
            )

        item_match = _ITEM_PROGRESS_RE.search(line)
        if item_match:
            item_status = (
                f"Items {item_match.group('username')}: "
                f"{item_match.group('percentage')}% "
                f"({item_match.group('current')}/{item_match.group('total')})"
            )
            self.item_progress_var.set(item_status)
            self._set_status(item_status)
            line = item_status + (" reintento" if item_match.group("retry") else "") + "\n"
        self._write_console(line)

    def _handle_process_complete(self, batch_id: int, exit_code: int) -> None:
        self._stop_progress_poll()
        if self.cancel_requested:
            mark_batch_interrupted(self.connection, batch_id)
        self._refresh_runtime_progress()
        self._reload_catalog()
        self.batch_ready_for_rename = (
            not self.last_run_was_dry_run
            and not self.cancel_requested
            and is_batch_ready_for_rename(self.connection, batch_id)
        )
        queued = self.active_queue_id is not None
        cancelled = self.cancel_requested
        self.cancel_requested = False
        self.active_process_kind = None
        if queued:
            continued = self._continue_queue_after_batch(
                cancelled=cancelled,
                exit_code=exit_code,
            )
            if continued:
                self._update_pending_button_label()
                return
        self._set_process_running(False)
        if cancelled:
            self._set_status(f"Lote {batch_id} interrumpido; queda pendiente")
            self._write_console(
                f"Lote {batch_id} detenido. SQLite conserva el trabajo y el batch "
                "queda en estado PARTIAL para poder reanudarlo.\n"
            )
        elif exit_code == 0:
            self.account_progress_var.set("Cuentas: 100%")
            self.item_progress_var.set("Items: 100%")
            if self.batch_ready_for_rename:
                self._set_status(
                    f"Lote {batch_id} listo para renombrar o finalizar"
                )
                self._write_console(
                    f"Lote {batch_id} finalizado correctamente. "
                    "Estado POR RENOMBRAR: usa Renombrar o Finalizar sin renombrar.\n"
                )
            else:
                self._set_status(f"Lote {batch_id} finalizado correctamente")
                self._write_console(f"Lote {batch_id} finalizado correctamente.\n")
        else:
            self._set_status(f"Lote {batch_id} finalizado con codigo {exit_code}")
            self._write_console(
                f"Lote {batch_id} finalizado con codigo de salida {exit_code}.\n"
            )
        self._update_pending_button_label()
        _play_completion_sound(self.root)

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

    def _resolve_manual_rename_context(
        self,
    ) -> tuple[str, tuple[NewAccountRenameParameters, ...], list[str]]:
        """Return start date, new-account args and optional warning notes."""

        notes: list[str] = []
        if self.active_queue_id is not None:
            try:
                params = collect_queue_rename_parameters(
                    self.connection, self.active_queue_id
                )
            except (BatchQueueError, ValueError) as exc:
                notes.append(f"No se pudo leer la cola {self.active_queue_id}: {exc}")
            else:
                notes.append(
                    f"Parámetros unidos de la cola id={self.active_queue_id} "
                    f"({len(params.batch_ids)} lote(s))."
                )
                if params.has_mixed_dates:
                    notes.append(
                        "Los lotes tenían startNowDate distintos; "
                        f"se usa {params.start_now_date}."
                    )
                if not MANUAL_RENAME_SCRIPT.is_file():
                    notes.append(
                        f"Aviso: no se encontró el script en {MANUAL_RENAME_SCRIPT}."
                    )
                return params.start_now_date, params.new_accounts, notes

        start_now_date = self.default_date_var.get().strip()
        accounts = self.accounts
        batch_id = self.active_batch_id or self.saved_batch_id
        if batch_id is not None:
            try:
                persisted_draft = load_batch_draft(self.connection, batch_id)
            except ValueError as exc:
                notes.append(f"No se pudo releer el lote {batch_id} desde SQLite: {exc}")
            else:
                if persisted_draft.default_start_now_date.strip():
                    start_now_date = persisted_draft.default_start_now_date.strip()
                accounts = persisted_draft.accounts
                notes.append(f"Parámetros tomados del lote id={batch_id} en SQLite.")
        else:
            notes.append(
                "Sin lote persistido: se usan la fecha global y las cuentas "
                "del borrador en pantalla."
            )

        try:
            parsed_date = date.fromisoformat(start_now_date)
        except ValueError:
            parsed_date = None
        if parsed_date is None or parsed_date.isoformat() != start_now_date:
            notes.append(
                f"Aviso: Start date «{start_now_date or '(vacío)'}» no es YYYY-MM-DD."
            )
        if not MANUAL_RENAME_SCRIPT.is_file():
            notes.append(
                f"Aviso: no se encontró el script en {MANUAL_RENAME_SCRIPT}."
            )

        new_accounts = _new_account_rename_parameters(accounts)
        return start_now_date, new_accounts, notes

    def _show_manual_rename_command(self) -> None:
        """Show the exact rename script invocation without executing it."""

        start_now_date, new_accounts, notes = self._resolve_manual_rename_context()
        preview = format_manual_rename_command_preview(
            start_now_date,
            new_accounts=new_accounts,
        )
        if notes:
            preview = "Notas:\n" + "\n".join(f"- {note}" for note in notes) + "\n\n" + preview

        dialog = tk.Toplevel(self.root)
        dialog.title("Comando de renombrado manual")
        dialog.geometry("820x480")
        dialog.minsize(560, 320)
        dialog.transient(self.root)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(
            dialog,
            text=(
                "Este diálogo no ejecuta el renombrador: solo muestra el comando "
                "con todos sus parámetros para copiarlo y lanzarlo a mano."
            ),
            wraplength=780,
            padding=(12, 10, 12, 4),
        ).grid(row=0, column=0, sticky="ew")

        text = tk.Text(dialog, wrap="word", height=18)
        text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        scroll = ttk.Scrollbar(
            dialog,
            orient=tk.VERTICAL,
            command=text.yview,
            style="Visible.Vertical.TScrollbar",
        )
        scroll.grid(row=1, column=1, sticky="ns", pady=(0, 6))
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", preview)
        text.configure(state="disabled")

        def copy_command() -> None:
            # Prefer the shell-ready first command line when present.
            body = preview
            marker = "Comando listo para pegar (PowerShell / cmd):\n"
            if marker in body:
                after = body.split(marker, 1)[1]
                shell_line = after.splitlines()[0] if after else body
            else:
                shell_line = body
            dialog.clipboard_clear()
            dialog.clipboard_append(shell_line)
            dialog.update_idletasks()
            self._set_status("Comando de renombrado copiado al portapapeles")

        actions = ttk.Frame(dialog, padding=10)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="Cerrar", command=dialog.destroy).pack(side=tk.LEFT)
        ttk.Button(actions, text="Copiar comando", command=copy_command).pack(
            side=tk.RIGHT
        )
        dialog.focus_set()

    def _rename_manual_files(self) -> None:
        if self._history_guard("renombrar"):
            return
        if self.process_runner.is_running() or not self.batch_ready_for_rename:
            return

        if self.active_queue_id is None and self.active_batch_id is None:
            messagebox.showerror("Renombrar", "No hay un batch activo para renombrar.")
            return
        if self.active_queue_id is not None:
            try:
                params = collect_queue_rename_parameters(
                    self.connection, self.active_queue_id
                )
            except (BatchQueueError, ValueError) as exc:
                messagebox.showerror("Renombrar", str(exc))
                return
            self.default_date_var.set(params.start_now_date)
            self.rename_new_accounts = params.new_accounts
            if params.has_mixed_dates:
                self._write_console(
                    "Aviso: startNowDate combinado = "
                    f"{params.start_now_date} (la más reciente de la cola).\n"
                )
        else:
            try:
                persisted_draft = load_batch_draft(
                    self.connection,
                    self.active_batch_id,
                )
            except ValueError as exc:
                messagebox.showerror("Renombrar", str(exc))
                return
            self.default_date_var.set(persisted_draft.default_start_now_date)
            self.rename_new_accounts = _new_account_rename_parameters(
                persisted_draft.accounts
            )

        start_now_date = self.default_date_var.get().strip()
        try:
            parsed_date = date.fromisoformat(start_now_date)
        except ValueError:
            parsed_date = None
        if parsed_date is None or parsed_date.isoformat() != start_now_date:
            messagebox.showerror(
                "Renombrar",
                "Start date debe tener formato YYYY-MM-DD antes de renombrar.",
            )
            return
        if not MANUAL_RENAME_SCRIPT.is_file():
            error = f"No se encontro el script de renombrado: {MANUAL_RENAME_SCRIPT}"
            self._write_console(error + "\n")
            messagebox.showerror("Renombrar", error)
            return

        command = build_manual_rename_command(
            start_now_date,
            new_accounts=self.rename_new_accounts,
        )
        self._write_console(
            f"Iniciando renombrado con Start date {start_now_date}: "
            f"{' '.join(command)}\n"
        )
        self._set_process_running(True)
        self._set_status("Renombrando archivos...")
        self.active_process_kind = "rename"
        try:
            self.process_runner.start(
                command,
                on_output=lambda line: self.root.after(0, self._write_console, line),
                on_complete=lambda exit_code: self.root.after(
                    0, self._handle_rename_complete, exit_code
                ),
            )
        except (OSError, RuntimeError) as exc:
            self._set_process_running(False)
            self._set_status("No se pudo iniciar el renombrado")
            self._write_console(f"No se pudo iniciar el renombrado: {exc}\n")
            messagebox.showerror("Renombrar", str(exc))

    def _handle_rename_complete(self, exit_code: int) -> None:
        leftovers = list_unmoved_account_folders(self.settings.working_folder)
        decision = decide_rename_completion(
            exit_code=exit_code,
            leftover_folders=leftovers,
        )
        self.active_process_kind = None
        if decision.mark_completed:
            if self.active_queue_id is not None:
                try:
                    finish_queue_after_rename(self.connection, self.active_queue_id)
                    self._write_console(
                        f"Cola {self.active_queue_id} y sus lotes marcados "
                        "COMPLETED tras renombrar.\n"
                    )
                    self.active_queue_id = None
                except (BatchQueueError, ValueError) as exc:
                    self._write_console(
                        f"No se pudo marcar COMPLETED la cola: {exc}\n"
                    )
            elif self.active_batch_id is not None:
                try:
                    finish_batch(self.connection, self.active_batch_id)
                    self._write_console(
                        f"Batch {self.active_batch_id} marcado COMPLETED "
                        "tras renombrar.\n"
                    )
                except ValueError as exc:
                    self._write_console(
                        f"No se pudo marcar COMPLETED tras renombrar: {exc}\n"
                    )
        self.batch_ready_for_rename = decision.keep_rename_enabled
        self._set_process_running(False)
        if leftovers:
            names = ", ".join(path.name for path in leftovers)
            self._write_console(
                "Quedan carpetas sin mover en "
                f"{self.settings.working_folder}: {names}. "
                "Renombrar permanece activo (la llamada usa --move-renamed).\n"
            )
        if exit_code == 0 and not leftovers:
            self._update_pending_button_label()
            self._set_status("Renombrado finalizado correctamente")
            self._write_console("Renombrado finalizado correctamente.\n")
        elif leftovers:
            self._update_pending_button_label()
            self._set_status(
                f"Renombrado incompleto: {len(leftovers)} carpeta(s) pendiente(s)"
            )
        else:
            self._set_status(f"Renombrado finalizado con codigo {exit_code}")
            self._write_console(
                f"Renombrado finalizado con codigo de salida {exit_code}.\n"
            )

    def _cancel_process(self) -> None:
        if self.process_runner.cancel():
            self.cancel_requested = self.active_process_kind == "batch"
            self._set_status("Deteniendo proceso...")
            self._write_console("Detencion solicitada.\n")

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

    def _open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title(t("settings.title"))
        window.transient(self.root)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=t("settings.language")).grid(row=0, column=0, sticky="w")
        language = tk.StringVar(value=current_language())
        ttk.Radiobutton(
            frame,
            text=t("settings.language.es"),
            value="es",
            variable=language,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Radiobutton(
            frame,
            text=t("settings.language.en"),
            value="en",
            variable=language,
        ).grid(row=2, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.language_restart")).grid(
            row=3, column=0, sticky="w", pady=(6, 10)
        )

        def apply_language() -> None:
            chosen = language.get()
            if chosen == current_language():
                return
            if is_gui_schema(self.connection):
                self.connection.execute(
                    """
                    INSERT INTO app_settings (key, value, value_type, updated_at)
                    VALUES ('ui.language', ?, 'TEXT', datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (chosen,),
                )
                self.connection.commit()
            self.root.destroy()
            import subprocess
            import sys

            subprocess.Popen([sys.executable, "-m", "ig_orchestrator", "gui"])

        ttk.Button(frame, text=t("settings.language.es") + " / EN", command=apply_language).grid(
            row=4, column=0, sticky="w", pady=(0, 12)
        )
        ttk.Button(
            frame,
            text=t("settings.purge_files"),
            command=lambda: self._purge_downloaded_files(window),
        ).grid(row=5, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.colors")).grid(
            row=7, column=0, sticky="w", pady=(16, 4)
        )
        color_row = ttk.Frame(frame)
        color_row.grid(row=8, column=0, sticky="w")
        for index, (key, label_key) in enumerate(
            (
                ("favorite", "settings.color_favorite"),
                ("in_batch", "settings.color_in_batch"),
                ("today", "settings.color_today"),
                ("inactive", "settings.color_inactive"),
                ("disabled", "settings.color_disabled"),
            )
        ):
            ttk.Button(
                color_row,
                text=t(label_key),
                command=lambda k=key: self._pick_catalog_color(window, k),
            ).grid(row=0, column=index, padx=(0, 4))

        ttk.Label(frame, text=t("settings.notify")).grid(
            row=9, column=0, sticky="w", pady=(16, 4)
        )
        notify_enabled = tk.BooleanVar(
            value=_gui_setting(self.connection, "notify.enabled", "0") in {"1", "true"}
        )
        ttk.Checkbutton(
            frame, text=t("settings.notify_enable"), variable=notify_enabled
        ).grid(row=10, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.notify_target")).grid(
            row=11, column=0, sticky="w", pady=(6, 0)
        )
        target_var = tk.StringVar(
            value=_gui_setting(self.connection, "notify.target", "me")
        )
        ttk.Entry(frame, textvariable=target_var, width=32).grid(
            row=12, column=0, sticky="w"
        )
        ttk.Label(frame, text=t("settings.notify_template")).grid(
            row=13, column=0, sticky="w", pady=(6, 0)
        )
        template_var = tk.StringVar(
            value=_gui_setting(
                self.connection,
                "notify.template_batch_done",
                t("settings.notify_template_default"),
            )
        )
        ttk.Entry(frame, textvariable=template_var, width=64).grid(
            row=14, column=0, sticky="ew"
        )
        ttk.Label(frame, text=t("settings.notify_errors")).grid(
            row=15, column=0, sticky="w", pady=(8, 2)
        )
        error_vars: dict[str, tk.BooleanVar] = {}
        error_frame = ttk.Frame(frame)
        error_frame.grid(row=16, column=0, sticky="w")
        if is_gui_schema(self.connection):
            error_rows = self.connection.execute(
                """
                SELECT code, description, notify_on_match
                FROM bot_errors
                WHERE is_active = 1
                ORDER BY sort_order, id
                """
            ).fetchall()
            for index, row in enumerate(error_rows):
                var = tk.BooleanVar(value=bool(row["notify_on_match"]))
                error_vars[str(row["code"])] = var
                ttk.Checkbutton(
                    error_frame,
                    text=f"{row['code']}",
                    variable=var,
                ).grid(row=index, column=0, sticky="w")

        def save_notify() -> None:
            if not is_gui_schema(self.connection):
                return
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('notify.enabled', ?, 'BOOLEAN', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                ("1" if notify_enabled.get() else "0",),
            )
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('notify.target', ?, 'TEXT', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                (target_var.get().strip() or "me",),
            )
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('notify.template_batch_done', ?, 'TEXT', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                (template_var.get() or " ",),
            )
            for code, var in error_vars.items():
                self.connection.execute(
                    """
                    UPDATE bot_errors
                    SET notify_on_match = ?
                    WHERE code = ?
                    """,
                    (int(var.get()), code),
                )
            self.connection.commit()

        ttk.Button(frame, text=t("settings.notify_save"), command=save_notify).grid(
            row=17, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Button(
            frame,
            text=t("settings.notify_test"),
            command=lambda: self._send_test_notification(
                window, target_var.get().strip() or "me"
            ),
        ).grid(row=18, column=0, sticky="w", pady=(4, 0))
        ttk.Button(frame, text=t("settings.close"), command=window.destroy).grid(
            row=19, column=0, sticky="e", pady=(16, 0)
        )

    def _pick_catalog_color(self, parent: tk.Toplevel, key: str) -> None:
        current = self.catalog_colors.get(key) or "#ffffff"
        _rgb, hex_color = colorchooser.askcolor(color=current, parent=parent)
        if not hex_color:
            return
        save_color(self.connection, key, hex_color)
        self.catalog_colors = load_catalog_colors(self.connection)
        self._refresh_catalog()

    def _send_test_notification(self, parent: tk.Toplevel, target: str) -> None:
        import asyncio

        try:
            asyncio.run(
                _send_test_telegram(self.settings, target)
            )
        except Exception as exc:
            messagebox.showerror(t("settings.notify_test"), str(exc), parent=parent)
            return
        messagebox.showinfo(
            t("settings.notify_test"), t("settings.notify_test_ok"), parent=parent
        )

    def _purge_downloaded_files(self, parent: tk.Toplevel) -> None:
        if not messagebox.askyesno(
            t("settings.purge_files"), t("settings.purge_confirm"), parent=parent
        ):
            return
        count = purge_downloaded_files(self.connection)
        messagebox.showinfo(
            t("settings.purge_files"),
            t("settings.purged", count=count),
            parent=parent,
        )


def _gui_setting(connection: Connection, key: str, default: str) -> str:
    if not is_gui_schema(connection):
        return default
    try:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
    except Exception:
        return default
    if row is None or not str(row["value"]).strip():
        return default
    return str(row["value"])


async def _send_test_telegram(settings: Settings, target: str) -> None:
    from ig_orchestrator.telegram.notify_service import send_ephemeral_notification

    await send_ephemeral_notification(
        settings, "Instagram Orchestrator: prueba de notificación", target=target
    )


def _suggest_batch_name() -> str:
    return f"descargas_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"


def _catalog_entry_colors(
    entry: AccountCatalogEntry,
    *,
    in_batch: bool = False,
    today: bool = False,
    palette: dict[str, str] | None = None,
) -> dict[str, str]:
    return colors_for_entry(
        entry,
        palette or _CATALOG_COLORS,
        in_batch=in_batch,
        today=today,
    )


def _batch_mode_details(
    *,
    saved_batch_id: int | None,
    active_batch_id: int | None,
    batch_name: str,
) -> tuple[str, str, str, bool]:
    """Return explicit GUI labels for new, editable and already-started batches."""

    normalized_name = batch_name.strip() or "(sin nombre)"
    if saved_batch_id is not None:
        return (
            "Modo: EDITANDO LOTE REGISTRADO — "
            f"{normalized_name} (ID: {saved_batch_id})",
            "Actualizar lote",
            f"Ejecutar lote ID {saved_batch_id}",
            True,
        )
    if active_batch_id is not None:
        return (
            "Modo: LOTE YA INICIADO — "
            f"{normalized_name} (ID: {active_batch_id}). "
            "Pulsa «Nuevo lote» para registrar otro.",
            "Lote no editable",
            "Ejecución iniciada",
            False,
        )
    return (
        "Modo: NUEVO LOTE (sin registrar y sin ID)",
        "Registrar lote nuevo",
        "Ejecutar lote nuevo",
        True,
    )


def _window_mode_title(
    context: str,
    batch_name: str,
    history_readonly: bool,
    saved_batch_id: int | None,
    active_batch_id: int | None,
) -> str:
    name = batch_name.strip() or "-"
    if history_readonly:
        return t("mode.history", name=name, id=active_batch_id or "-")
    if saved_batch_id is not None:
        return t("mode.editing", name=name, id=saved_batch_id)
    if active_batch_id is not None:
        return t("mode.running", name=name, id=active_batch_id)
    return t("mode.new")


def _half_screen_geometry(screen_width: int, screen_height: int) -> str:
    width = max(860, screen_width // 2)
    height = max(680, screen_height - 80)
    return f"{width}x{height}+0+0"


_BATCH_COLUMNS = (
    ("username", "Username"),
    ("urls", "URLs"),
    ("status", "Estado"),
    ("stories", "Stories"),
    ("start_date", "Start date"),
)


def _username_heading_title(ascending: bool | None) -> str:
    if ascending is True:
        return "Username ▲"
    if ascending is False:
        return "Username ▼"
    return "Username"


def _sort_accounts_by_username(
    accounts: list[AccountDraft],
    *,
    ascending: bool,
) -> list[AccountDraft]:
    return sorted(
        accounts,
        key=lambda account: account.username.casefold(),
        reverse=not ascending,
    )


def _catalog_width_chars(usernames: Iterable[str]) -> int:
    """Return the initial catalog width in Tk character units."""
    return max(
        (len(str(username)) for username in usernames),
        default=len("Catalogo"),
    )


def _batch_column_samples(usernames: Iterable[str]) -> dict[str, str]:
    """Return the longest expected visible value for every batch column."""
    username_values = ["Username", *(str(username) for username in usernames)]
    longest_username = max(username_values, key=lambda value: (len(value), value))
    return {
        "username": longest_username,
        "urls": "9999",
        "status": "Completada 9999/9999",
        "stories": "Stories",
        "start_date": "0000-00-00",
    }


def _play_completion_sound(root: tk.Misc) -> None:
    """Play the native Windows completion sound, with Tk's bell as fallback."""
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
        return
    except (ImportError, OSError, RuntimeError):
        pass
    try:
        root.bell()
    except tk.TclError:
        pass


def _instagram_profile_url(username: str) -> str:
    normalized = username.strip().lstrip("@").strip()
    return f"https://www.instagram.com/{normalized}/"


def _open_chrome_tab(url: str) -> bool:
    try:
        chrome = webbrowser.get("chrome")
    except webbrowser.Error:
        return webbrowser.open_new_tab(url)
    return chrome.open_new_tab(url)


def _open_path_in_explorer(path: Path) -> None:
    """Open a local directory in the OS file manager (Explorer on Windows)."""
    target = Path(path)
    if not target.is_dir():
        raise FileNotFoundError(f"Directory not found: {target}")
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    import subprocess

    subprocess.run(["xdg-open", str(target)], check=False)


def _set_ttk_enabled(widget: ttk.Widget, enabled: bool) -> None:
    """Change a ttk state without using unsupported configure options."""
    widget.state(("!disabled",) if enabled else ("disabled",))


def _timestamp_console_text(text: str, *, now: datetime | None = None) -> str:
    """Prefix every GUI console line with a local timestamp including milliseconds."""
    if not text:
        return ""
    current = now or datetime.now()
    timestamp = current.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return "".join(f"{timestamp} {line}" for line in text.splitlines(keepends=True))


def _latest_executed_batch_name(connection: Connection) -> str | None:
    row = connection.execute(
        """
        SELECT input_batches.batch_name
        FROM runs
        JOIN input_batches ON input_batches.id = runs.batch_id
        WHERE runs.batch_id IS NOT NULL
        ORDER BY runs.started_at DESC, runs.id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is not None:
        return str(row[0])

    row = connection.execute(
        """
        SELECT batch_name
        FROM input_batches
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def _draft_signature(draft: BatchDraft) -> tuple[object, ...]:
    return (
        draft.batch_name,
        draft.default_start_now_date,
        tuple(
            (
                account.username,
                account.download_stories,
                tuple(account.urls),
                account.start_now_date,
                account.is_new_account,
                account.is_catalog_update,
                account.owner_id,
                account.start_init_date,
                account.destination_path,
            )
            for account in draft.accounts
        ),
    )


def _new_account_rename_parameters(
    accounts: list[AccountDraft],
) -> tuple[NewAccountRenameParameters, ...]:
    return tuple(
        NewAccountRenameParameters(
            username=account.username,
            owner_id=account.owner_id,
            start_init_date=account.start_init_date,
            destination_path=account.destination_path,
        )
        for account in accounts
        if account.is_new_account
    )


def _account_display_status(
    account: AccountDraft,
    runtime: AccountRuntimeProgress | None,
) -> tuple[str, str]:
    if runtime is None:
        if account.is_new_account:
            return "Nueva", "pending"
        if account.is_catalog_update:
            return "Catálogo", "pending"
        if account.download_stories or account.urls:
            return "Preparada", "pending"
        return "Vacia", "failed"
    if runtime.status == "COMPLETED":
        return f"Completada {runtime.completed_items}/{runtime.total_items}", "completed"
    if runtime.retry_items:
        return f"Reintento ({runtime.retry_items})", "retry"
    if runtime.status == "PROCESSING":
        return f"En curso {runtime.completed_items}/{runtime.total_items}", "processing"
    if runtime.status == "FAILED" or (
        runtime.failed_items and not runtime.pending_items
    ):
        return f"Fallida ({runtime.failed_items})", "failed"
    return f"Pendiente ({runtime.pending_items})", "pending"


_ACCOUNT_PROGRESS_RE = re.compile(
    r"\[(?P<current>\d+)/(?P<total>\d+)\s*\|\s*(?P<percentage>\d+)%\]"
)
_ITEM_PROGRESS_RE = re.compile(
    r"\[GUI_ITEM_PROGRESS\]\s+(?P<username>[^:]+):\s+"
    r"(?P<percentage>\d+)%\s+\((?P<current>\d+)/(?P<total>\d+)\)"
    r"(?P<retry>\s+retry)?"
)


__all__ = ["InstagramOrchestratorApp", "launch_gui"]
