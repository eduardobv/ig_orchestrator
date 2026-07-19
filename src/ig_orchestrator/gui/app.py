from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
from sqlite3 import Connection
import tkinter as tk
from tkinter import messagebox, ttk

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
    finish_batch,
    get_account_runtime_progress,
    list_pending_batches,
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
        self.status_var = tk.StringVar(value="Ready")
        self.account_progress_var = tk.StringVar(value="Cuentas: -")
        self.item_progress_var = tk.StringVar(value="Items: -")
        self.indicators_var = tk.StringVar(value="URLs: 0")

        self.root.title("Instagram Orchestrator")
        self.root.geometry("1280x760")
        self._build_widgets()
        self._refresh_catalog()
        self._refresh_table()
        self._update_pending_button_label()

    def _build_widgets(self) -> None:
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
        self.register_button = ttk.Button(
            top, text="Registrar lote", command=self._save_batch
        )
        self.register_button.grid(row=0, column=5, padx=(0, 6))
        self.pending_button = ttk.Button(
            top,
            text="Recuperar ejecucion",
            command=self._open_pending_batches,
        )
        self.pending_button.grid(row=0, column=6, padx=(0, 6))
        self.execute_button = ttk.Button(top, text="Ejecutar", command=self._execute)
        self.execute_button.grid(row=0, column=7)

        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.body_region = body
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        catalog = ttk.Frame(body, padding=6)
        batch = ttk.Frame(body, padding=6)
        editor = ttk.Frame(body, padding=6)
        body.add(catalog, weight=1)
        body.add(batch, weight=2)
        body.add(editor, weight=2)

        self._build_catalog(catalog)
        self._build_batch_table(batch)
        self._build_editor(editor)

        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.console = tk.Text(bottom, height=9, state="disabled", wrap="word")
        self.console.grid(row=0, column=0, sticky="ew")
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

    def _build_catalog(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Catalogo").grid(row=0, column=0, sticky="w")
        filter_entry = ttk.Entry(parent, textvariable=self.catalog_filter_var)
        filter_entry.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        self.catalog_filter_var.trace_add("write", lambda *_: self._refresh_catalog())
        self.catalog_list = tk.Listbox(parent, exportselection=False)
        self.catalog_list.grid(row=2, column=0, sticky="nsew")
        self.catalog_list.bind("<Double-Button-1>", lambda _event: self._load_catalog())

    def _build_batch_table(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Lote actual").grid(row=0, column=0, sticky="w")
        self.tree = ttk.Treeview(
            parent,
            columns=("username", "stories", "urls", "start_date", "status"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("username", "Username", 140),
            ("stories", "Stories", 70),
            ("urls", "URLs", 55),
            ("start_date", "Start date", 95),
            ("status", "Estado", 90),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=1, column=0, columnspan=5, sticky="nsew", pady=(6, 6))
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_row())
        self.tree.tag_configure("completed", foreground="#238636")
        self.tree.tag_configure("retry", foreground="#b76e00")
        self.tree.tag_configure("processing", foreground="#0969da")
        self.tree.tag_configure("pending", foreground="#57606a")
        self.tree.tag_configure("failed", foreground="#cf222e")
        ttk.Button(parent, text="Subir", command=lambda: self._move_selected(-1)).grid(
            row=2, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(parent, text="Bajar", command=lambda: self._move_selected(1)).grid(
            row=2, column=1, sticky="ew", padx=(0, 4)
        )
        ttk.Button(parent, text="Duplicar", command=self._duplicate_selected).grid(
            row=2, column=2, sticky="ew", padx=(0, 4)
        )
        ttk.Button(parent, text="Eliminar", command=self._delete_selected).grid(
            row=2, column=3, sticky="ew", padx=(0, 4)
        )
        ttk.Button(parent, text="Limpiar lote", command=self._clear_batch).grid(
            row=2, column=4, sticky="ew"
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
        ttk.Entry(self.new_account_frame, textvariable=self.destination_path_var).grid(
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
        ttk.Button(parent, text="Pegar", command=self._paste_urls).grid(
            row=7, column=0, sticky="ew", pady=(8, 0), padx=(0, 4)
        )
        ttk.Button(parent, text="Normalizar", command=self._normalize_urls).grid(
            row=7, column=1, sticky="ew", pady=(8, 0), padx=(0, 4)
        )
        ttk.Button(parent, text="Agregar / Actualizar", command=self._upsert_account).grid(
            row=7, column=2, sticky="ew", pady=(8, 0)
        )
        ttk.Button(parent, text="Limpiar editor", command=self._clear_editor).grid(
            row=8, column=1, columnspan=2, sticky="ew", pady=(8, 0)
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

    def _refresh_table(self) -> None:
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        for index, account in enumerate(self.accounts):
            runtime = self.runtime_progress.get(account.username.casefold())
            status, tag = _account_display_status(account, runtime)
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    account.username,
                    "si" if account.download_stories else "no",
                    len([url for url in account.urls if url.strip()]),
                    account.start_now_date or self.default_date_var.get(),
                    status,
                ),
                tags=(tag,),
            )
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
            self.username_combo.configure(
                values=[entry.username for entry in self.catalog_entries]
            )
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
        del self.accounts[self.selected_index]
        self.selected_index = None
        self._refresh_table()
        self._clear_editor()

    def _clear_batch(self) -> None:
        self.accounts.clear()
        self.selected_index = None
        self._refresh_table()
        self._clear_editor()

    def _clear_editor(self) -> None:
        self.selected_index = None
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

    def _paste_urls(self) -> None:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        self.urls_text.insert(tk.INSERT, text)
        self._update_indicators()

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
        pending = list_pending_batches(self.connection)
        dialog = tk.Toplevel(self.root)
        dialog.title("Ejecuciones pendientes")
        dialog.geometry("940x360")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(
            dialog,
            text=(
                "Selecciona un lote interrumpido para recuperar su contenido y "
                "reanudarlo desde SQLite."
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
            for summary in list_pending_batches(self.connection):
                tree.insert(
                    "",
                    tk.END,
                    iid=str(summary.batch_id),
                    values=(
                        summary.batch_date,
                        summary.batch_name,
                        summary.batch_id,
                        summary.status,
                        f"{summary.completed_accounts}/{summary.total_accounts} completas; "
                        f"{summary.retry_accounts} reintento; "
                        f"{summary.remaining_accounts} por terminar",
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

        def finish_selected() -> None:
            batch_id = selected_batch_id()
            if batch_id is None:
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
        ttk.Button(actions, text="Reanudar seleccionado", command=resume_selected).pack(
            side=tk.RIGHT
        )
        ttk.Button(actions, text="Dar por finalizado", command=finish_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ttk.Button(actions, text="Cerrar", command=dialog.destroy).pack(side=tk.LEFT)
        tree.bind("<Double-Button-1>", lambda _event: resume_selected())
        reload_rows()
        if not pending:
            ttk.Label(dialog, text="No hay ejecuciones pendientes.").place(
                relx=0.5, rely=0.48, anchor="center"
            )

    def _update_pending_button_label(self) -> None:
        total = len(list_pending_batches(self.connection))
        self.pending_button.configure(text=f"Recuperar ejecucion ({total})")

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
        self._refresh_runtime_progress()
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
            result = save_batch_draft(draft, self.connection, settings=self.settings)
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
        self._write_console(
            f"Batch saved: {result.batch.batch_name} (id={result.batch.id})\n"
            f"SQLite database: {self.settings.sqlite_db_path}\n"
        )
        self._set_status(f"Saved batch id {result.batch.id}")
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

        self.batch_ready_for_rename = False
        self.rename_new_accounts = _new_account_rename_parameters(self.accounts)
        self.last_run_was_dry_run = self.dry_run_var.get()
        self.active_batch_id = batch_id
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

    def _rename_manual_files(self) -> None:
        if self.process_runner.is_running() or not self.batch_ready_for_rename:
            return

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
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.rename_button.configure(
            state="normal" if not running and self.batch_ready_for_rename else "disabled"
        )
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
    return f"descargas_{datetime.now().strftime('%Y_%m_%d_%H%M')}"


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
