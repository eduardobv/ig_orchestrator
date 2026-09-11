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
    batch_username_matches_filter,
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


class EditorPanelMixin:
    """Mixin: username, URLs, paste/normalize, upsert."""

    def _build_editor(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(4, weight=1)
        parent.columnconfigure(2, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Label(header, text=t("label.editor")).pack(side=tk.LEFT)

        self.add_update_button = icon_button(
            parent,
            image=self.icons.get("plus"),
            command=self._upsert_account,
            tooltip=t("tooltip.add_update"),
        )
        self.add_update_button.grid(row=1, column=0, sticky="n", padx=(0, 8), pady=(8, 0))
        ttk.Label(parent, text=t("label.username")).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        username_row = ttk.Frame(parent)
        username_row.grid(row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))
        self.username_combo = ttk.Combobox(
            username_row,
            textvariable=self.username_var,
            width=28,
            values=[entry.username for entry in self.catalog_entries],
        )
        self.username_combo.grid(row=0, column=0, sticky="w")
        self.username_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._apply_catalog_date()
        )
        bind_edit_context_menu(self.username_combo)
        self.paste_username_button = compact_icon_button(
            username_row,
            image=self.icons.get_compact("clipboard-black"),
            command=self._paste_username,
            tooltip=t("tooltip.paste_username"),
        )
        self.paste_username_button.grid(row=0, column=1, sticky="e", padx=(4, 0))
        self.clear_username_button = ttk.Button(
            username_row,
            text="❌",
            width=3,
            command=self._clear_username,
        )
        self.clear_username_button.grid(row=0, column=2, sticky="e", padx=(4, 0))
        Tooltip(self.clear_username_button, t("tooltip.clear_username"))

        flags = ttk.Frame(parent)
        flags.grid(row=2, column=2, columnspan=2, sticky="w", pady=(8, 0))
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
            parent,
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
            row=3, column=1, columnspan=3, sticky="ew", pady=(8, 0)
        )
        self.new_account_frame.grid_remove()

        self.url_actions = ttk.Frame(parent)
        self.url_actions.grid(row=4, column=0, sticky="n", padx=(0, 8), pady=(8, 0))
        self.paste_add_button = icon_button(
            self.url_actions,
            image=self.icons.get("clipboard-plus"),
            command=self._paste_and_upsert,
            tooltip=t("tooltip.paste_add"),
        )
        self.paste_add_button.pack(side=tk.TOP, pady=1)
        icon_button(
            self.url_actions,
            image=self.icons.get("clipboard"),
            command=self._paste_urls,
            tooltip=t("tooltip.paste"),
        ).pack(side=tk.TOP, pady=1)
        icon_button(
            self.url_actions,
            image=self.icons.get("wand"),
            command=self._normalize_urls,
            tooltip=t("tooltip.normalize"),
        ).pack(side=tk.TOP, pady=1)
        icon_button(
            self.url_actions,
            image=self.icons.get("eraser"),
            command=self._clear_editor,
            tooltip=t("tooltip.clear_editor"),
        ).pack(side=tk.TOP, pady=1)

        ttk.Label(parent, text=t("label.urls")).grid(
            row=4, column=1, sticky="nw", pady=(8, 0)
        )
        self.urls_text = tk.Text(parent, height=9, wrap="none", undo=True)
        self.urls_text.grid(
            row=4, column=2, sticky="nsew", pady=(8, 0)
        )
        urls_scroll = ttk.Scrollbar(
            parent,
            orient=tk.VERTICAL,
            command=self.urls_text.yview,
            style="Visible.Vertical.TScrollbar",
        )
        urls_scroll.grid(row=4, column=3, sticky="ns", pady=(8, 0))
        self.urls_text.configure(yscrollcommand=urls_scroll.set)
        self.urls_text.bind("<KeyRelease>", lambda _event: self._update_indicators())
        bind_edit_context_menu(self.urls_text, after_change=self._update_indicators)
        ttk.Label(parent, textvariable=self.indicators_var).grid(
            row=5, column=2, columnspan=2, sticky="w", pady=(6, 0)
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
            reveal_index = len(self.accounts) - 1
        else:
            self.accounts[self.selected_index] = stored
            reveal_index = self.selected_index
        if stored.is_new_account or stored.is_catalog_update:
            self.catalog_entries = self.catalog_service.list_entries()
            self.destination_paths = self.catalog_service.list_destination_paths()
            self.username_combo.configure(
                values=[entry.username for entry in self.catalog_entries]
            )
            self.destination_path_combo.configure(values=self.destination_paths)
        query = self.batch_filter_var.get() if getattr(self, "batch_filter_var", None) else ""
        if not batch_username_matches_filter(stored.username, query):
            self.batch_filter_var.set("")
        self._refresh_table()
        self._refresh_catalog()
        self._clear_editor()
        self._reveal_batch_row(reveal_index)


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


    def _clear_username(self) -> None:
        self.username_var.set("")
        try:
            self.username_combo.focus_set()
        except (tk.TclError, AttributeError):
            pass


    def _paste_username(self) -> bool:
        text = read_clipboard(self.root)
        if text is None:
            return False
        self.username_var.set(first_clipboard_line(text))
        try:
            self.username_combo.icursor(tk.END)
            self.username_combo.focus_set()
        except (tk.TclError, AttributeError):
            pass
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

