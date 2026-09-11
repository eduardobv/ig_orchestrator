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


class BatchesDialogMixin:
    """Mixin: saved/executed batches dialog (includes queue panel)."""

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
            if self.active_queue_id is not None:
                open_queue = get_open_queue(self.connection)
                if open_queue is None:
                    self.active_queue_id = None
            reload_active()
            refresh_queue_panel()
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
            if self.active_queue_id is not None:
                open_queue = get_open_queue(self.connection)
                if open_queue is None:
                    self.active_queue_id = None
            self._write_console(
                f"Batch {batch_id} marcado como COMPLETED (sin renombrar).\n"
            )
            reload_active()
            refresh_queue_panel()
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
            if self.active_queue_id is not None:
                open_queue = get_open_queue(self.connection)
                if open_queue is None:
                    self.active_queue_id = None
            reload_active()
            refresh_queue_panel()
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
            self.active_queue_id = None
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
                queue = remove_queue_item(self.connection, item_id)
            except BatchQueueError as exc:
                messagebox.showerror("Cola", str(exc), parent=dialog)
                return
            refresh_queue_panel()
            if queue.status == QueueStatus.CANCELLED.value:
                self.active_queue_id = None
                self._write_console(
                    "Lote quitado de la cola; la secuencia quedó vacía y se cerró.\n"
                )
            elif self.process_runner.is_running() and self.active_queue_id is not None:
                self._write_console(
                    "Lote quitado de la cola; la secuencia "
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

