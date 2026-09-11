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


class BatchAccountsPanelMixin:
    """Mixin: current-batch account table."""

    def _build_batch_table(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, columnspan=4, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=t("label.batch_accounts")).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.batch_count_var).pack(side=tk.RIGHT)
        filter_row = ttk.Frame(parent)
        filter_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        filter_row.columnconfigure(0, weight=1)
        self.batch_filter_entry = ttk.Entry(
            filter_row, textvariable=self.batch_filter_var
        )
        self.batch_filter_entry.grid(row=0, column=0, sticky="ew")
        bind_edit_context_menu(self.batch_filter_entry)
        ttk.Button(
            filter_row,
            text="❌",
            width=3,
            command=self._clear_batch_filter,
        ).grid(row=0, column=1, sticky="e", padx=(4, 0))
        self.batch_filter_var.trace_add("write", lambda *_: self._refresh_table())
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
        self.tree.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(6, 6))
        batch_scroll = ttk.Scrollbar(
            parent,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            style="Visible.Vertical.TScrollbar",
        )
        batch_scroll.grid(row=2, column=3, sticky="ns", pady=(6, 6))
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
        self.delete_button.grid(row=3, column=0, sticky="ew", padx=(0, 4))
        self.save_selection_button = ttk.Button(
            parent,
            text="Guardar selección",
            command=self._save_selected_accounts_as_batch,
        )
        self.save_selection_button.grid(row=3, column=1, sticky="ew", padx=(0, 4))
        self.delete_all_button = ttk.Button(
            parent,
            text="Eliminar todo",
            command=self._delete_all_accounts,
        )
        self.delete_all_button.grid(row=3, column=2, columnspan=2, sticky="ew")


    def _clear_batch_filter(self) -> None:
        self.batch_filter_var.set("")


    def _refresh_table(self) -> None:
        if getattr(self, "tree", None) is None:
            return
        selected_usernames = self._selected_batch_usernames()
        query = self.batch_filter_var.get() if getattr(self, "batch_filter_var", None) else ""
        visible = filter_batch_accounts(self.accounts, query)
        visible_ids = {str(index) for index, _account in visible}
        for item_id in self.tree.get_children():
            if item_id not in visible_ids:
                self.tree.delete(item_id)
        for display_order, (index, account) in enumerate(visible):
            runtime = self.runtime_progress.get(account.username.casefold())
            status, tag = _account_display_status(account, runtime)
            iid = str(index)
            values = (
                account.username,
                len([url for url in account.urls if url.strip()]),
                status,
                stories_cell_text(account.download_stories),
                account.start_now_date or self.default_date_var.get(),
            )
            if self.tree.exists(iid):
                self.tree.item(iid, values=values, tags=(tag,))
                self.tree.move(iid, "", display_order)
            else:
                self.tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
        self.tree.selection_remove(*self.tree.selection())
        for index, account in visible:
            if account.username.casefold() in selected_usernames:
                self.tree.selection_add(str(index))
        self._update_batch_count()
        if not self.runtime_progress:
            self._set_status(f"{len(self.accounts)} account(s) in draft")


    def _update_batch_count(self) -> None:
        total = len(self.accounts)
        visible = len(self.tree.get_children()) if getattr(self, "tree", None) else total
        query = ""
        if getattr(self, "batch_filter_var", None) is not None:
            query = self.batch_filter_var.get().strip()
        if query and visible != total:
            self.batch_count_var.set(
                t("label.batch_count_filtered", visible=visible, count=total)
            )
            return
        self.batch_count_var.set(t("label.batch_count", count=total))


    def _reveal_batch_row(self, index: int) -> None:
        """Scroll to a batch row and focus it without selecting (editor stays empty)."""
        iid = str(index)
        if not getattr(self, "tree", None) or not self.tree.exists(iid):
            return
        self.tree.focus(iid)
        self.tree.see(iid)


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
            iid = str(index)
            if account.username.casefold() in selected and self.tree.exists(iid):
                self.tree.selection_add(iid)
        if self.tree.selection():
            focus_id = self.tree.selection()[-1]
            self.tree.focus(focus_id)
            self.selected_index = int(focus_id)


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
        except DuplicateBatchNameError as exc:
            messagebox.showerror("Guardar selección", str(exc))
            return
        except IntegrityError as exc:
            messagebox.showerror(
                "Guardar selección",
                "No se pudo guardar la selección por una restricción de SQLite. "
                "Revisa que el nombre no esté repetido y que no haya "
                f"cuentas duplicadas.\n\n{exc}",
            )
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

