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
from ig_orchestrator.gui.theme import (
    STATUS_TONE_IDLE,
    Tooltip,
    compact_icon_button,
    icon_button,
)
from ig_orchestrator.gui.treeview_sort import bind_treeview_sort
from ig_orchestrator.input.batch_creation_service import DuplicateBatchNameError
from ig_orchestrator.models import AccountHistoryStatus
from ig_orchestrator.orchestration.processing_policy import (
    read_stories_first_enabled,
    write_stories_first_enabled,
)


class RunControllerMixin:
    """Mixin: save/execute/cancel batch and queue sequence."""

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
        self._set_status_tone(STATUS_TONE_IDLE)
        self._write_console(
            "Nuevo lote iniciado. El lote anterior permanece sin cambios en SQLite.\n"
        )


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
        except DuplicateBatchNameError as exc:
            messagebox.showerror("Guardar lote", str(exc))
            return None
        except IntegrityError as exc:
            messagebox.showerror(
                "Guardar lote",
                "No se pudo guardar el lote por una restricción de SQLite. "
                "Revisa que el nombre no esté repetido y que no haya "
                f"cuentas duplicadas.\n\n{exc}",
            )
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

        self._set_status_tone(STATUS_TONE_IDLE)
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
            try:
                queue = get_queue(self.connection, queue_id)
            except BatchQueueError:
                self.active_queue_id = None
                return False
            if queue.status == QueueStatus.CANCELLED.value or not queue.rename_batch_ids:
                self.active_queue_id = None
                return False
            self.batch_ready_for_rename = True
            self.rename_button.configure(state="normal")
            try:
                params = collect_queue_rename_parameters(self.connection, queue_id)
            except BatchQueueError as exc:
                self.active_queue_id = None
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
        queued = False
        if self.active_queue_id is not None:
            try:
                queue = get_queue(self.connection, self.active_queue_id)
            except BatchQueueError:
                self.active_queue_id = None
            else:
                queued = queue.is_running_batch(batch_id)
                if not queued and not queue.is_open:
                    self.active_queue_id = None
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


    def _cancel_process(self) -> None:
        if self.process_runner.cancel():
            self.cancel_requested = self.active_process_kind == "batch"
            self._set_status("Deteniendo proceso...")
            self._write_console("Detencion solicitada.\n")

