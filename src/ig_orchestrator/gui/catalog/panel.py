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


class CatalogPanelMixin:
    """Mixin: catalog list/tree, filter, contextual menu."""

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
        self.catalog_filter_entry = ttk.Entry(
            filter_row, textvariable=self.catalog_filter_var
        )
        self.catalog_filter_entry.grid(row=0, column=0, sticky="ew")
        bind_edit_context_menu(self.catalog_filter_entry)
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
        focus_username = catalog_focus_username(query, filtered, selected_username)
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
        self._refresh_catalog_tree(
            filtered,
            query=query,
            in_batch=in_batch,
            today=today,
            focus_username=focus_username,
        )

        scrolled_to_match = False
        if focus_username is not None:
            try:
                index = visible.index(focus_username)
            except ValueError:
                index = None
            if index is not None:
                self.catalog_list.selection_clear(0, tk.END)
                self.catalog_list.selection_set(index)
                self.catalog_list.activate(index)
                if query.strip():
                    self.catalog_list.see(index)
                    scrolled_to_match = True
        if yview and not scrolled_to_match:
            self.catalog_list.yview_moveto(yview[0])


    def _refresh_catalog_tree(
        self,
        entries,
        *,
        query: str,
        in_batch: set[str],
        today: set[str],
        focus_username: str | None = None,
    ) -> None:
        tree = getattr(self, "catalog_tree", None)
        if tree is None:
            return
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
        self._select_catalog_tree_leaf(focus_username)


    def _select_catalog_tree_leaf(self, username: str | None) -> None:
        """Select a catalog leaf without loading it into the editor."""
        tree = getattr(self, "catalog_tree", None)
        if tree is None or not username:
            return
        leaf = f"user:{username}"
        if not tree.exists(leaf):
            return
        self._catalog_silent_token = getattr(self, "_catalog_silent_token", 0) + 1
        token = self._catalog_silent_token
        try:
            tree.selection_set(leaf)
            tree.focus(leaf)
            tree.see(leaf)
        finally:
            def _release() -> None:
                if self._catalog_silent_token == token:
                    self._catalog_silent_token = 0

            try:
                self.root.after_idle(_release)
            except tk.TclError:
                _release()


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


    def _load_catalog(self) -> None:
        if getattr(self, "_catalog_silent_token", 0):
            return
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

