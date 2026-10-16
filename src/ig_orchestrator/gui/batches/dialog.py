from __future__ import annotations

from datetime import date
from pathlib import Path
from sqlite3 import IntegrityError
import tkinter as tk
from tkinter import font as tkfont
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

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
from ig_orchestrator.gui.batches.manage import (
    BatchManageError,
    create_empty_draft_batch,
    delete_unstarted_batch,
    list_batch_accounts,
    list_draft_targets,
    rename_batch,
    restore_batch_to_draft,
)
from ig_orchestrator.gui.batches.pause import (
    PauseAccountsError,
    move_accounts_to_batch,
    suggest_split_name,
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
    bind_escape_close,
    catalog_focus_username,
    center_modal_on_parent,
    filter_batch_accounts,
    priority_cell_text,
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


class BatchesDialogMixin:
    """Mixin: saved/executed batches dialog (list, accounts detail, batch management)."""

    def _open_pending_batches(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Lotes guardados y ejecuciones")
        dialog.geometry("1100x720")
        dialog.transient(self.root)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=3)
        dialog.rowconfigure(2, weight=2)
        self._batches_dialog = dialog

        def _clear_dialog_ref(_event=None) -> None:
            if self._batches_dialog is dialog:
                self._batches_dialog = None

        dialog.bind("<Destroy>", _clear_dialog_ref)
        bind_escape_close(dialog, on_close=_clear_dialog_ref)

        ttk.Label(
            dialog,
            text=(
                "Activos: GUARDADO, ejecuciones y POR RENOMBRAR; selecciona un lote "
                "para ver sus cuentas, moverlas a otro lote, renombrarlo o borrarlo. "
                "Históricos: lotes COMPLETED (solo lectura; los no iniciados se "
                "pueden recuperar). Importar crea un lote nuevo en esta instancia."
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
                    "Editar lote",
                    "Una ejecucion ya iniciada no se puede editar. "
                    "Usa Ejecutar o Renombrar segun el estado.",
                    parent=dialog,
                )
                return
            try:
                draft = load_batch_draft(self.connection, summary.batch_id)
            except ValueError as exc:
                messagebox.showerror("Editar lote", str(exc), parent=dialog)
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
                    "Ejecutar lote",
                    "Este lote esta POR RENOMBRAR. Usa Renombrar o "
                    "Finalizar sin renombrar.",
                    parent=dialog,
                )
                return
            batch_id = summary.batch_id
            try:
                draft = load_batch_draft(self.connection, batch_id)
            except ValueError as exc:
                messagebox.showerror("Ejecutar lote", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load_persisted_draft(batch_id, draft)
            self._start_batch(batch_id)

        def selected_active_batch_id_quiet() -> int | None:
            selection = active_tree.selection()
            return int(selection[0]) if len(selection) == 1 else None

        def select_batch(batch_id: int | None) -> None:
            if batch_id is not None and active_tree.exists(str(batch_id)):
                active_tree.selection_set(str(batch_id))
                active_tree.see(str(batch_id))
            refresh_detail()

        def after_change(*, changed=(), deleted=()) -> None:
            """Refresh lists and keep the main window consistent with SQLite."""
            reload_active()
            if history_loaded["done"]:
                reload_history()
            self._sync_editor_with_batches(set(changed), set(deleted))
            self._update_pending_button_label()

        def new_batch() -> None:
            name = simpledialog.askstring(
                t("batches.new.title"),
                t("batches.new.prompt"),
                initialvalue=_suggest_batch_name(),
                parent=dialog,
            )
            if name is None:
                return
            try:
                batch_id = create_empty_draft_batch(self.connection, name)
            except BatchManageError as exc:
                messagebox.showerror(t("batches.new.title"), str(exc), parent=dialog)
                return
            self._write_console(f"Lote GUARDADO vacío creado: id={batch_id}.\n")
            after_change()
            select_batch(batch_id)

        def rename_batch_action() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            if self.process_runner.is_running() and self.active_batch_id == summary.batch_id:
                messagebox.showwarning(
                    t("batches.btn.rename"),
                    t("batches.rename.running"),
                    parent=dialog,
                )
                return
            name = simpledialog.askstring(
                t("batches.btn.rename"),
                t("batches.rename.prompt"),
                initialvalue=summary.batch_name,
                parent=dialog,
            )
            if name is None or name.strip() == summary.batch_name:
                return
            try:
                rename_batch(self.connection, summary.batch_id, name)
            except BatchManageError as exc:
                messagebox.showerror(t("batches.btn.rename"), str(exc), parent=dialog)
                return
            after_change(changed={summary.batch_id})
            select_batch(summary.batch_id)

        def delete_selected() -> None:
            summary = selected_active_summary()
            if summary is None:
                return
            if not messagebox.askyesno(
                t("batches.btn.delete"),
                t(
                    "batches.delete.confirm",
                    name=summary.batch_name,
                    id=summary.batch_id,
                    accounts=summary.total_accounts,
                ),
                parent=dialog,
            ):
                return
            try:
                delete_unstarted_batch(self.connection, summary.batch_id)
            except (BatchManageError, ValueError) as exc:
                messagebox.showerror(t("batches.btn.delete"), str(exc), parent=dialog)
                return
            self._write_console(f"Lote {summary.batch_id} borrado.\n")
            after_change(deleted={summary.batch_id})
            select_batch(None)

        def choose_move_target(source_id: int, count: int):
            """Small modal: pick a saved batch or a new name. Returns (kind, value) or None."""
            result: dict[str, object] = {}
            top = tk.Toplevel(dialog)
            top.title(t("batches.move.title"))
            top.transient(dialog)
            top.columnconfigure(0, weight=1)
            targets = list_draft_targets(self.connection, source_id)
            new_label = t("batches.move.new_option")
            labels = [new_label] + [f"{name} (id={bid})" for bid, name in targets]
            ttk.Label(top, text=t("batches.move.prompt", count=count), padding=10).grid(
                row=0, column=0, sticky="w"
            )
            combo = ttk.Combobox(top, values=labels, state="readonly", width=48)
            combo.current(1 if targets else 0)
            combo.grid(row=1, column=0, sticky="ew", padx=10)
            name_var = tk.StringVar(value=suggest_split_name(self.connection, source_id))
            name_entry = ttk.Entry(top, textvariable=name_var, width=50)
            name_entry.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 0))

            def sync_entry(_event=None) -> None:
                name_entry.configure(
                    state="normal" if combo.current() == 0 else "disabled"
                )

            combo.bind("<<ComboboxSelected>>", sync_entry)
            sync_entry()

            def accept() -> None:
                if combo.current() == 0:
                    result["value"] = ("new", name_var.get())
                else:
                    result["value"] = ("existing", targets[combo.current() - 1][0])
                top.destroy()

            buttons = ttk.Frame(top, padding=10)
            buttons.grid(row=3, column=0, sticky="e")
            ttk.Button(buttons, text=t("batches.move.ok"), command=accept).pack(side=tk.RIGHT)
            ttk.Button(buttons, text=t("batches.close"), command=top.destroy).pack(
                side=tk.RIGHT, padx=(0, 8)
            )
            top.bind("<Escape>", lambda _e: top.destroy())
            top.grab_set()
            center_modal_on_parent(top, dialog, False)
            top.wait_window()
            return result.get("value")

        def move_accounts_action() -> None:
            source_id = selected_active_batch_id_quiet()
            if source_id is None:
                messagebox.showwarning(
                    t("batches.move.title"), t("batches.select_one"), parent=dialog
                )
                return
            usernames = [
                str(detail_tree.item(item, "values")[0])
                for item in detail_tree.selection()
            ]
            if not usernames:
                messagebox.showwarning(
                    t("batches.move.title"), t("batches.move.select_accounts"), parent=dialog
                )
                return
            choice = choose_move_target(source_id, len(usernames))
            if choice is None:
                return
            kind, value = choice
            created_id = None
            try:
                if kind == "new":
                    created_id = create_empty_draft_batch(self.connection, str(value))
                    target_id = created_id
                else:
                    target_id = int(value)
                result = move_accounts_to_batch(
                    self.connection,
                    source_batch_id=source_id,
                    target_batch_id=target_id,
                    usernames=usernames,
                )
            except (BatchManageError, PauseAccountsError) as exc:
                if created_id is not None:
                    delete_unstarted_batch(self.connection, created_id)
                messagebox.showerror(t("batches.move.title"), str(exc), parent=dialog)
                return
            self._write_console(
                f"{len(result.usernames)} cuenta(s) movidas → «{result.target_batch_name}» "
                f"(id={result.target_batch_id}).\n"
            )
            after_change(changed={source_id, result.target_batch_id})
            select_batch(source_id)

        def restore_selected() -> None:
            summary = selected_history_summary()
            if summary is None:
                return
            try:
                restore_batch_to_draft(self.connection, summary.batch_id)
            except BatchManageError as exc:
                messagebox.showwarning(t("batches.btn.restore"), str(exc), parent=dialog)
                return
            self._write_console(
                f"Lote {summary.batch_id} recuperado del histórico como GUARDADO.\n"
            )
            after_change(changed={summary.batch_id})
            notebook.select(0)
            select_batch(summary.batch_id)

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
            refresh_detail()
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
                "(puedes renombrar o finalizar sin renombrar).\n\n"
                + t("batches.elsewhere_warning"),
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
            refresh_detail()
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

        # --- detail of the selected batch: its accounts ---------------------------------
        manage_row = ttk.Frame(active_tab)
        manage_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(manage_row, text=t("batches.btn.new"), command=new_batch).pack(side=tk.LEFT)
        ttk.Button(manage_row, text=t("batches.btn.rename"), command=rename_batch_action).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(manage_row, text=t("batches.btn.delete"), command=delete_selected).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        detail_frame = ttk.LabelFrame(dialog, text=t("batches.detail"), padding=8)
        detail_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 4))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        detail_tree = ttk.Treeview(
            detail_frame,
            columns=("username", "prio", "urls", "stories", "start"),
            show="headings",
            height=6,
            selectmode="extended",
        )
        for column, title_key, width, anchor in (
            ("username", "batches.col.username", 260, "w"),
            ("prio", "batches.col.prio", 60, "center"),
            ("urls", "batches.col.urls", 70, "e"),
            ("stories", "batches.col.stories", 80, "center"),
            ("start", "batches.col.start", 120, "w"),
        ):
            detail_tree.heading(column, text=t(title_key))
            detail_tree.column(column, width=width, anchor=anchor)
        detail_tree.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(
            detail_frame,
            orient=tk.VERTICAL,
            command=detail_tree.yview,
            style="Visible.Vertical.TScrollbar",
        )
        detail_scroll.grid(row=0, column=1, sticky="ns")
        detail_tree.configure(yscrollcommand=detail_scroll.set)
        detail_buttons = ttk.Frame(detail_frame)
        detail_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        detail_hint = ttk.Label(detail_buttons, text="")
        detail_hint.pack(side=tk.LEFT)
        ttk.Button(
            detail_buttons, text=t("batches.btn.move"), command=move_accounts_action
        ).pack(side=tk.RIGHT)

        def refresh_detail() -> None:
            for item in detail_tree.get_children():
                detail_tree.delete(item)
            batch_id = selected_active_batch_id_quiet()
            if batch_id is None:
                detail_hint.configure(text=t("batches.select_one"))
                return
            rows = list_batch_accounts(self.connection, batch_id)
            for index, row in enumerate(rows):
                detail_tree.insert(
                    "",
                    tk.END,
                    iid=str(index),
                    values=(
                        row.username,
                        priority_cell_text(row.priority),
                        row.url_count,
                        stories_cell_text(row.download_stories),
                        row.start_date,
                    ),
                )
            detail_hint.configure(text=t("batches.detail_count", count=len(rows)))

        active_tree.bind("<<TreeviewSelect>>", lambda _event: refresh_detail())

        active_actions = ttk.Frame(dialog, padding=10)
        history_actions = ttk.Frame(dialog, padding=10)
        active_actions.grid(row=3, column=0, sticky="ew")

        def show_active_actions() -> None:
            history_actions.grid_remove()
            active_actions.grid(row=3, column=0, sticky="ew")
            detail_frame.grid()

        def show_history_actions() -> None:
            active_actions.grid_remove()
            detail_frame.grid_remove()
            history_actions.grid(row=3, column=0, sticky="ew")
            if not history_loaded["done"]:
                reload_history()

        def on_tab_changed(_event=None) -> None:
            if current_is_history():
                show_history_actions()
            else:
                show_active_actions()

        ttk.Button(active_actions, text=t("batches.btn.run"), command=resume_selected).pack(
            side=tk.RIGHT
        )
        ttk.Button(active_actions, text=t("batches.btn.edit"), command=recover_selected).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
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
        ttk.Button(active_actions, text="Cerrar", command=dialog.destroy).pack(side=tk.LEFT)

        ttk.Button(
            history_actions,
            text="Abrir (solo lectura)",
            command=open_history_selected,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            history_actions,
            text=t("batches.btn.restore"),
            command=restore_selected,
        ).pack(side=tk.RIGHT, padx=(0, 8))
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
        refresh_detail()
        if not managed:
            active_empty.place(relx=0.48, rely=0.48, anchor="center")
        center_modal_on_parent(dialog, self.root, self.root.state() == "zoomed")


    def _sync_editor_with_batches(self, changed: set[int], deleted: set[int]) -> None:
        """Keep the main window consistent after the batches dialog changed SQLite."""
        if self.saved_batch_id in deleted:
            if not self.process_runner.is_running():
                self._start_new_batch()
            return
        for batch_id in (self.saved_batch_id, self.active_batch_id):
            if batch_id is None or batch_id not in changed:
                continue
            try:
                draft = load_batch_draft(self.connection, batch_id)
            except ValueError:
                return
            if self.saved_batch_id == batch_id:
                self._load_persisted_draft(batch_id, draft)
            else:
                self.accounts = list(draft.accounts)
                self.saved_draft_signature = _draft_signature(draft)
                self.selected_index = None
                self._refresh_table()
                self._refresh_runtime_progress()
            return
