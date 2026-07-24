from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
import re
from sqlite3 import Connection
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
import webbrowser

from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogEntry,
    AccountCatalogService,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    inspect_account_draft,
    normalize_url_lines,
    save_new_account_to_catalog,
    save_batch_draft,
)
from ig_orchestrator.gui.batch_resume_service import (
    AccountRuntimeProgress,
    activate_draft_batch,
    complete_account_manually,
    delete_draft_batch,
    fail_account_manually,
    finish_batch,
    get_account_runtime_progress,
    is_batch_ready_for_rename,
    list_managed_batches,
    load_batch_draft,
    mark_batch_interrupted,
)
from ig_orchestrator.gui.process_runner import (
    MANUAL_RENAME_SCRIPT,
    NewAccountRenameParameters,
    ProcessRunner,
    build_manual_rename_command,
    build_run_continue_command,
)
from ig_orchestrator.settings import Settings


def launch_gui(
    *,
    connection: Connection,
    settings: Settings,
    batch_json_path: Path = Path("config/batch.json"),
) -> None:
    root = tk.Tk()
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
        self.destination_paths = self.catalog_service.list_destination_paths()
        self.accounts: list[AccountDraft] = []
        self.selected_index: int | None = None
        self.saved_batch_id: int | None = None
        self.saved_draft_signature: tuple[object, ...] | None = None
        self.process_runner = ProcessRunner()
        self.batch_ready_for_rename = False
        self.rename_new_accounts: tuple[NewAccountRenameParameters, ...] = ()
        self.last_run_was_dry_run = False
        self.active_batch_id: int | None = None
        self.cancel_requested = False
        self.active_process_kind: str | None = None
        self.runtime_progress: dict[str, AccountRuntimeProgress] = {}
        self.progress_poll_id: str | None = None

        today = date.today().isoformat()
        self.batch_name_var = tk.StringVar(
            value=_latest_executed_batch_name(connection) or _suggest_batch_name()
        )
        self.default_date_var = tk.StringVar(value=today)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.catalog_filter_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.account_date_var = tk.StringVar(value=today)
        self.stories_var = tk.BooleanVar(value=False)
        self.new_account_var = tk.BooleanVar(value=False)
        self.owner_id_var = tk.StringVar()
        self.start_init_date_var = tk.StringVar()
        self.destination_path_var = tk.StringVar()
        self.batch_context_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.account_progress_var = tk.StringVar(value="Cuentas: -")
        self.item_progress_var = tk.StringVar(value="Items: -")
        self.indicators_var = tk.StringVar(value="URLs: 0")

        self.root.title("Instagram Orchestrator")
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

    def _build_widgets(self) -> None:
        ttk.Style(self.root).configure("Thin.Vertical.TScrollbar", width=8)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=8)
        self.top_region = top
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Batch name").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.batch_name_var).grid(
            row=0, column=1, sticky="ew", padx=(6, 12)
        )
        ttk.Label(top, text="Start date").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.default_date_var, width=12).grid(
            row=0, column=3, sticky="w", padx=(6, 12)
        )
        ttk.Checkbutton(top, text="Dry-run", variable=self.dry_run_var).grid(
            row=0, column=4, sticky="w", padx=(0, 12)
        )
        self.new_batch_button = ttk.Button(
            top, text="Nuevo lote", command=self._start_new_batch
        )
        self.new_batch_button.grid(row=0, column=5, padx=(0, 6))
        self.register_button = ttk.Button(top, command=self._save_batch)
        self.register_button.grid(row=0, column=6, padx=(0, 6))
        self.pending_button = ttk.Button(
            top,
            text="Recuperar ejecucion",
            command=self._open_pending_batches,
        )
        self.pending_button.grid(row=0, column=7, padx=(0, 6))
        self.execute_button = ttk.Button(top, text="Ejecutar", command=self._execute)
        self.execute_button.grid(row=0, column=8)
        ttk.Label(
            top,
            textvariable=self.batch_context_var,
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=1, column=0, columnspan=9, sticky="w", pady=(7, 0))

        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.body_region = body
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        catalog_width = _catalog_width_chars(
            entry.username for entry in self.catalog_entries
        )
        catalog = ttk.Frame(body, padding=6)
        batch = ttk.Frame(body, padding=6)
        editor = ttk.Frame(body, padding=6)
        body.add(catalog, weight=1)
        body.add(batch, weight=2)
        body.add(editor, weight=2)

        self._build_catalog(catalog, width_chars=catalog_width)
        self._build_batch_table(batch)
        self._build_editor(editor)

        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)
        self.console = tk.Text(bottom, height=8, state="disabled", wrap="word")
        self.console.grid(row=0, column=0, sticky="nsew")
        console_scroll = ttk.Scrollbar(
            bottom,
            orient=tk.VERTICAL,
            command=self.console.yview,
            style="Thin.Vertical.TScrollbar",
        )
        console_scroll.grid(row=0, column=1, sticky="ns")
        self.console.configure(yscrollcommand=console_scroll.set)
        progress = ttk.Frame(bottom)
        progress.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        progress.columnconfigure(2, weight=1)
        ttk.Label(progress, textvariable=self.account_progress_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(progress, textvariable=self.item_progress_var).grid(
            row=0, column=1, sticky="w", padx=(18, 0)
        )
        ttk.Label(progress, textvariable=self.status_var).grid(
            row=0, column=2, sticky="w", padx=(18, 0)
        )
        self.cancel_button = ttk.Button(
            progress,
            text="Cancelar proceso",
            command=self._cancel_process,
            state="disabled",
        )
        self.rename_button = ttk.Button(
            progress,
            text="Renombrar",
            command=self._rename_manual_files,
            state="disabled",
        )
        self.rename_button.grid(row=0, column=3, sticky="e", padx=(0, 6))
        self.clean_console_button = ttk.Button(
            progress,
            text="Clean",
            command=self._clear_console,
        )
        self.clean_console_button.grid(row=0, column=4, sticky="e", padx=(0, 6))
        self.cancel_button.grid(row=0, column=5, sticky="e")

    def _build_catalog(self, parent: ttk.Frame, *, width_chars: int) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Catalogo").grid(row=0, column=0, sticky="w")
        filter_entry = ttk.Entry(parent, textvariable=self.catalog_filter_var)
        filter_entry.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        self.catalog_filter_var.trace_add("write", lambda *_: self._refresh_catalog())
        self.catalog_list = tk.Listbox(
            parent,
            exportselection=False,
            width=width_chars,
        )
        self.catalog_list.grid(row=2, column=0, sticky="nsew")
        self.catalog_list.bind(
            "<Double-Button-1>", lambda _event: self._open_and_load_catalog_account()
        )
        self.catalog_list.bind("<Button-3>", self._show_catalog_menu)
        self.catalog_menu = tk.Menu(self.root, tearoff=False)
        self.catalog_menu.add_command(label="Abrir", command=self._open_catalog_account)
        self.catalog_menu.add_command(label="Delete", command=self._disable_catalog_account)

    def _build_batch_table(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Cuentas del lote actual").grid(
            row=0, column=0, sticky="w"
        )
        self.tree = ttk.Treeview(
            parent,
            columns=tuple(column for column, _title in _BATCH_COLUMNS),
            show="headings",
            selectmode="browse",
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
        self.tree.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 6))
        batch_scroll = ttk.Scrollbar(
            parent,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            style="Thin.Vertical.TScrollbar",
        )
        batch_scroll.grid(row=1, column=2, sticky="ns", pady=(6, 6))
        self.tree.configure(yscrollcommand=batch_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_row())
        self.tree.bind("<Button-3>", self._show_batch_menu)
        self.batch_menu = tk.Menu(self.root, tearoff=False)
        self.batch_menu.add_command(
            label="Completar", command=self._complete_selected_account
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
        self.delete_all_button = ttk.Button(
            parent,
            text="Eliminar todo",
            command=self._delete_all_accounts,
        )
        self.delete_all_button.grid(
            row=2, column=1, columnspan=2, sticky="ew"
        )

    def _build_editor(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(5, weight=1)
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="Editor").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(parent, text="Username").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.username_combo = ttk.Combobox(
            parent,
            textvariable=self.username_var,
            values=[entry.username for entry in self.catalog_entries],
        )
        self.username_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        self.username_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_catalog_date())
        ttk.Checkbutton(
            parent,
            text="Download stories",
            variable=self.stories_var,
            command=self._update_indicators,
        ).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            parent,
            text="New account",
            variable=self.new_account_var,
            command=self._toggle_new_account_fields,
        ).grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Label(parent, text="Start date").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(parent, textvariable=self.account_date_var, width=12).grid(
            row=3, column=1, sticky="w", pady=(8, 0)
        )

        self.new_account_frame = ttk.LabelFrame(
            parent,
            text="Datos de cuenta nueva",
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
        ttk.Label(self.new_account_frame, text="startInitDate *").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Entry(self.new_account_frame, textvariable=self.start_init_date_var).grid(
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
            row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        self.new_account_frame.grid_remove()

        ttk.Label(parent, text="URLs").grid(row=5, column=0, sticky="nw", pady=(8, 0))
        self.urls_text = tk.Text(parent, height=9, wrap="none")
        self.urls_text.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=(8, 0))
        self.urls_text.bind("<KeyRelease>", lambda _event: self._update_indicators())
        ttk.Label(parent, textvariable=self.indicators_var).grid(
            row=6, column=1, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Button(
            parent,
            text="Pegar/Agregar",
            command=self._paste_and_upsert,
        ).grid(
            row=7, column=0, sticky="ew", pady=(8, 0), padx=(0, 4)
        )
        ttk.Button(parent, text="Pegar", command=self._paste_urls).grid(
            row=8, column=0, sticky="ew", pady=(8, 0), padx=(0, 4)
        )
        ttk.Button(parent, text="Normalizar", command=self._normalize_urls).grid(
            row=8, column=1, sticky="ew", pady=(8, 0), padx=(0, 4)
        )
        ttk.Button(parent, text="Agregar / Actualizar", command=self._upsert_account).grid(
            row=8, column=2, sticky="ew", pady=(8, 0)
        )
        ttk.Button(parent, text="Limpiar editor", command=self._clear_editor).grid(
            row=9, column=1, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def _toggle_new_account_fields(self) -> None:
        if self.new_account_var.get():
            self.new_account_frame.grid()
        else:
            self.new_account_frame.grid_remove()

    def _refresh_catalog(self) -> None:
        query = self.catalog_filter_var.get().strip().lower()
        self.catalog_list.delete(0, tk.END)
        for entry in self.catalog_entries:
            if not query or query in entry.username.lower():
                self.catalog_list.insert(tk.END, entry.username)

    def _show_catalog_menu(self, event: tk.Event) -> None:
        index = self.catalog_list.nearest(event.y)
        if index < 0 or index >= self.catalog_list.size():
            return
        self.catalog_list.selection_clear(0, tk.END)
        self.catalog_list.selection_set(index)
        self.catalog_list.activate(index)
        self.catalog_menu.tk_popup(event.x_root, event.y_root)

    def _selected_catalog_username(self) -> str | None:
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
            f"¿Ocultar @{username} del catalogo?\n\n"
            "La cuenta se conservara en SQLite con estado DISABLED.",
        ):
            return
        try:
            self.catalog_service.disable(username)
        except ValueError as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        self.catalog_entries = self.catalog_service.list_entries()
        self.username_combo.configure(
            values=[entry.username for entry in self.catalog_entries]
        )
        self._refresh_catalog()

    def _refresh_table(self) -> None:
        selected = self.tree.selection()
        selected_iid = selected[0] if selected else None
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
        if selected_iid is not None and self.tree.exists(selected_iid):
            self.tree.selection_set(selected_iid)
        if not self.runtime_progress:
            self._set_status(f"{len(self.accounts)} account(s) in draft")

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
        selection = self.catalog_list.curselection()
        if not selection:
            return
        username = self.catalog_list.get(selection[0])
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
        self.selected_index = int(selection[0])
        account = self.accounts[self.selected_index]
        self.username_var.set(account.username)
        self.stories_var.set(account.download_stories)
        self.new_account_var.set(account.is_new_account)
        self.owner_id_var.set(account.owner_id)
        self.start_init_date_var.set(account.start_init_date)
        self.destination_path_var.set(account.destination_path)
        self._toggle_new_account_fields()
        self.account_date_var.set(account.start_now_date)
        self.urls_text.delete("1.0", tk.END)
        self.urls_text.insert("1.0", "\n".join(account.urls))
        self._update_indicators()

    def _show_batch_menu(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self.selected_index = int(item_id)
        self.batch_menu.tk_popup(event.x_root, event.y_root)

    def _editor_account(self) -> AccountDraft:
        urls = self.urls_text.get("1.0", tk.END).splitlines()
        return AccountDraft(
            username=self.username_var.get(),
            download_stories=self.stories_var.get(),
            urls=urls,
            start_now_date=self.account_date_var.get(),
            is_new_account=self.new_account_var.get(),
            owner_id=self.owner_id_var.get(),
            start_init_date=self.start_init_date_var.get(),
            destination_path=self.destination_path_var.get(),
        )

    def _upsert_account(self) -> None:
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
            owner_id=account.owner_id.strip(),
            start_init_date=account.start_init_date.strip(),
            destination_path=account.destination_path.strip(),
        )
        try:
            save_new_account_to_catalog(stored, self.connection)
        except (BatchDraftValidationError, ValueError) as exc:
            messagebox.showerror("Catalogo", str(exc))
            return
        if self.selected_index is None:
            self.accounts.append(stored)
        else:
            self.accounts[self.selected_index] = stored
        if stored.is_new_account:
            self.catalog_entries = self.catalog_service.list_entries()
            self.destination_paths = self.catalog_service.list_destination_paths()
            self.username_combo.configure(
                values=[entry.username for entry in self.catalog_entries]
            )
            self.destination_path_combo.configure(values=self.destination_paths)
            self._refresh_catalog()
        self._refresh_table()
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
                owner_id=account.owner_id,
                start_init_date=account.start_init_date,
                destination_path=account.destination_path,
            ),
        )
        self._refresh_table()

    def _delete_selected(self) -> None:
        if self.selected_index is None:
            return
        if self.process_runner.is_running() and self.active_process_kind == "batch":
            self._fail_selected_running_account()
            return
        del self.accounts[self.selected_index]
        self.selected_index = None
        self._refresh_table()
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
        self._clear_editor()
        if self.saved_batch_id is not None:
            self._set_status(
                f"Todas las cuentas eliminadas; actualiza el lote {self.saved_batch_id}"
            )

    def _start_new_batch(self) -> None:
        """Leave any loaded batch untouched in SQLite and open a clean draft."""

        if self.process_runner.is_running():
            return
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
        self._clear_editor()
        self._refresh_table()
        self.account_progress_var.set("Cuentas: -")
        self.item_progress_var.set("Items: -")
        self.rename_button.configure(state="disabled")
        self._update_batch_context()
        self._set_status("Nuevo lote sin registrar")
        self._write_console(
            "Nuevo lote iniciado. El lote anterior permanece sin cambios en SQLite.\n"
        )

    def _clear_editor(self) -> None:
        self.selected_index = None
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)
        self.username_var.set("")
        self.account_date_var.set(date.today().isoformat())
        self.stories_var.set(False)
        self.new_account_var.set(False)
        self.owner_id_var.set("")
        self.start_init_date_var.set("")
        self.destination_path_var.set("")
        self._toggle_new_account_fields()
        self.urls_text.delete("1.0", tk.END)
        self._update_indicators()

    def _paste_urls(self) -> bool:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return False
        self.urls_text.insert(tk.INSERT, text)
        self._update_indicators()
        return True

    def _paste_and_upsert(self) -> None:
        if self._paste_urls():
            self._upsert_account()

    def _normalize_urls(self) -> None:
        urls = normalize_url_lines(self.urls_text.get("1.0", tk.END).splitlines())
        self.urls_text.delete("1.0", tk.END)
        self.urls_text.insert("1.0", "\n".join(urls))
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
        managed = list_managed_batches(self.connection)
        dialog = tk.Toplevel(self.root)
        dialog.title("Lotes guardados y ejecuciones pendientes")
        dialog.geometry("940x360")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(
            dialog,
            text=(
                "Los lotes GUARDADOS se pueden recuperar, modificar, borrar o ejecutar. "
                "Los demás estados pertenecen a ejecuciones y sólo se pueden reanudar."
            ),
            padding=(10, 10, 10, 4),
        ).grid(row=0, column=0, sticky="w")
        columns = ("date", "name", "id", "status", "progress")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (
            ("date", "Fecha", 170),
            ("name", "Nombre", 260),
            ("id", "Batch ID", 75),
            ("status", "Estado", 100),
            ("progress", "Cuentas", 230),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, anchor="w")
        tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)

        def reload_rows() -> None:
            for item in tree.get_children():
                tree.delete(item)
            for summary in list_managed_batches(self.connection):
                tree.insert(
                    "",
                    tk.END,
                    iid=str(summary.batch_id),
                    values=(
                        summary.batch_date,
                        summary.batch_name,
                        summary.batch_id,
                        "GUARDADO" if summary.is_draft else summary.status,
                        (
                            f"{summary.total_accounts} cuentas editables"
                            if summary.is_draft
                            else f"{summary.completed_accounts}/{summary.total_accounts} completas; "
                            f"{summary.retry_accounts} reintento; "
                            f"{summary.remaining_accounts} por terminar"
                        ),
                    ),
                )

        def selected_batch_id() -> int | None:
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(
                    "Ejecuciones pendientes",
                    "Selecciona primero un lote.",
                    parent=dialog,
                )
                return None
            return int(selection[0])

        def selected_summary():
            batch_id = selected_batch_id()
            if batch_id is None:
                return None
            return next(
                (item for item in list_managed_batches(self.connection) if item.batch_id == batch_id),
                None,
            )

        def recover_selected() -> None:
            summary = selected_summary()
            if summary is None:
                return
            if not summary.is_draft:
                messagebox.showwarning(
                    "Recuperar lote",
                    "Una ejecución ya iniciada no se puede editar. Usa Reanudar / Ejecutar.",
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
                f"Lote guardado {summary.batch_id} abierto para modificación.\n"
            )

        def resume_selected() -> None:
            batch_id = selected_batch_id()
            if batch_id is None:
                return
            try:
                draft = load_batch_draft(self.connection, batch_id)
            except ValueError as exc:
                messagebox.showerror("Reanudar lote", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load_persisted_draft(batch_id, draft)
            self._start_batch(batch_id)

        def delete_selected() -> None:
            summary = selected_summary()
            if summary is None:
                return
            if not summary.is_draft:
                messagebox.showwarning(
                    "Borrar lote",
                    "Sólo se pueden borrar lotes GUARDADOS que nunca se hayan ejecutado.",
                    parent=dialog,
                )
                return
            if not messagebox.askyesno(
                "Borrar lote guardado",
                f"¿Borrar definitivamente el lote guardado {summary.batch_name} "
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
            reload_rows()
            self._update_pending_button_label()

        def finish_selected() -> None:
            summary = selected_summary()
            if summary is None:
                return
            batch_id = summary.batch_id
            if summary.is_draft:
                messagebox.showwarning(
                    "Dar por finalizado",
                    "Un lote GUARDADO todavía no es una ejecución.",
                    parent=dialog,
                )
                return
            if not messagebox.askyesno(
                "Dar por finalizado",
                f"¿Seguro que quieres dar por finalizado el batch {batch_id}?\n\n"
                "No volverá a aparecer entre las ejecuciones pendientes. "
                "Los datos y archivos no se eliminarán.",
                parent=dialog,
            ):
                return
            try:
                finish_batch(self.connection, batch_id)
            except ValueError as exc:
                messagebox.showerror("Dar por finalizado", str(exc), parent=dialog)
                return
            self._write_console(f"Batch {batch_id} marcado manualmente como COMPLETED.\n")
            reload_rows()
            self._update_pending_button_label()

        actions = ttk.Frame(dialog, padding=10)
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Button(actions, text="Reanudar / Ejecutar", command=resume_selected).pack(
            side=tk.RIGHT
        )
        ttk.Button(actions, text="Recuperar / Modificar", command=recover_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(actions, text="Borrar lote", command=delete_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(actions, text="Dar por finalizado", command=finish_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(actions, text="Cerrar", command=dialog.destroy).pack(side=tk.LEFT)
        tree.bind("<Double-Button-1>", lambda _event: resume_selected())
        reload_rows()
        if not managed:
            ttk.Label(dialog, text="No hay lotes guardados ni ejecuciones pendientes.").place(
                relx=0.5, rely=0.48, anchor="center"
            )

    def _update_pending_button_label(self) -> None:
        total = len(list_managed_batches(self.connection))
        self.pending_button.configure(text=f"Lotes / ejecuciones ({total})")

    def _update_batch_context(self) -> None:
        context, register_text, execute_text, actions_enabled = _batch_mode_details(
            saved_batch_id=self.saved_batch_id,
            active_batch_id=self.active_batch_id,
            batch_name=self.batch_name_var.get(),
        )
        self.batch_context_var.set(context)
        self.register_button.configure(
            text=register_text,
            state="normal" if actions_enabled else "disabled",
        )
        self.execute_button.configure(
            text=execute_text,
            state="normal" if actions_enabled else "disabled",
        )
        self.delete_all_button.configure(
            state="normal" if actions_enabled else "disabled"
        )

    def _load_persisted_draft(self, batch_id: int, draft: BatchDraft) -> None:
        self.batch_name_var.set(draft.batch_name)
        self.default_date_var.set(draft.default_start_now_date)
        self.accounts = list(draft.accounts)
        self.selected_index = None
        self.saved_batch_id = batch_id
        self.saved_draft_signature = _draft_signature(draft)
        self.active_batch_id = batch_id
        self.rename_new_accounts = _new_account_rename_parameters(self.accounts)
        self._clear_editor()
        self.tree.selection_remove(*self.tree.selection())
        self._refresh_runtime_progress()
        self._update_batch_context()
        self._write_console(
            f"Lote {batch_id} recuperado desde SQLite: {draft.batch_name}.\n"
        )

    def _save_batch(self, *, show_confirmation: bool = True) -> int | None:
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

    def _execute(self) -> None:
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

        self.batch_ready_for_rename = False
        self.rename_new_accounts = _new_account_rename_parameters(self.accounts)
        self.last_run_was_dry_run = self.dry_run_var.get()
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
        self.batch_ready_for_rename = (
            exit_code == 0
            and not self.last_run_was_dry_run
            and not self.cancel_requested
        )
        self._set_process_running(False)
        if self.cancel_requested:
            self._set_status(f"Lote {batch_id} interrumpido; queda pendiente")
            self._write_console(
                f"Lote {batch_id} cancelado. SQLite conserva el trabajo y el batch "
                "queda en estado PARTIAL para poder reanudarlo.\n"
            )
        elif exit_code == 0:
            self.account_progress_var.set("Cuentas: 100%")
            self.item_progress_var.set("Items: 100%")
            self._set_status(f"Lote {batch_id} finalizado correctamente")
            self._write_console(f"Lote {batch_id} finalizado correctamente.\n")
        else:
            self._set_status(f"Lote {batch_id} finalizado con codigo {exit_code}")
            self._write_console(
                f"Lote {batch_id} finalizado con codigo de salida {exit_code}.\n"
            )
        self.cancel_requested = False
        self.active_process_kind = None
        self._update_pending_button_label()
        _play_completion_sound(self.root)

    def _complete_selected_account(self) -> None:
        if self.process_runner.is_running():
            messagebox.showwarning(
                "Completar cuenta",
                "Cancela primero la ejecución antes de completar una cuenta manualmente.",
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

    def _rename_manual_files(self) -> None:
        if self.process_runner.is_running() or not self.batch_ready_for_rename:
            return

        if self.active_batch_id is None:
            messagebox.showerror("Renombrar", "No hay un batch activo para renombrar.")
            return
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
        self.active_process_kind = None
        self._set_process_running(False)
        if exit_code == 0:
            self._set_status("Renombrado finalizado correctamente")
            self._write_console("Renombrado finalizado correctamente.\n")
        else:
            self._set_status(f"Renombrado finalizado con codigo {exit_code}")
            self._write_console(
                f"Renombrado finalizado con codigo de salida {exit_code}.\n"
            )

    def _cancel_process(self) -> None:
        if self.process_runner.cancel():
            self.cancel_requested = self.active_process_kind == "batch"
            self._set_status("Cancelando proceso...")
            self._write_console("Cancelacion solicitada.\n")

    def _set_process_running(self, running: bool) -> None:
        self._set_descendants_enabled(self.top_region, not running)
        self._set_descendants_enabled(self.body_region, not running)
        button_state = "disabled" if running else "normal"
        self.register_button.configure(state=button_state)
        self.pending_button.configure(state=button_state)
        self.execute_button.configure(state=button_state)
        if running and self.active_process_kind == "batch":
            _set_ttk_enabled(self.tree, True)
            self.delete_button.configure(state="normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.rename_button.configure(
            state="normal" if not running and self.batch_ready_for_rename else "disabled"
        )
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
        self.console.configure(state="normal")
        self.console.insert(tk.END, _timestamp_console_text(text))
        self.console.see(tk.END)
        self.console.configure(state="disabled")

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)


def _suggest_batch_name() -> str:
    return f"descargas_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"


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
