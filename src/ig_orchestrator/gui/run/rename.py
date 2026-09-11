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
    MANUAL_RENAME_SCRIPT,
    NewAccountRenameParameters,
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


class RenameMixin:
    """Mixin: manual rename command and leftover folders."""

    def _resolve_manual_rename_context(
        self,
    ) -> tuple[str, tuple[NewAccountRenameParameters, ...], list[str]]:
        """Return start date, new-account args and optional warning notes."""

        notes: list[str] = []
        if self.active_queue_id is not None:
            try:
                queue = get_queue(self.connection, self.active_queue_id)
            except BatchQueueError as exc:
                notes.append(f"No se pudo leer la cola {self.active_queue_id}: {exc}")
                self.active_queue_id = None
            else:
                if not queue.rename_batch_ids:
                    notes.append(
                        f"La cola {self.active_queue_id} no tiene lotes activos; "
                        "se usará el lote seleccionado."
                    )
                    self.active_queue_id = None
        if self.active_queue_id is not None:
            try:
                params = collect_queue_rename_parameters(
                    self.connection, self.active_queue_id
                )
            except (BatchQueueError, ValueError) as exc:
                notes.append(f"No se pudo leer la cola {self.active_queue_id}: {exc}")
                self.active_queue_id = None
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
                queue = get_queue(self.connection, self.active_queue_id)
            except BatchQueueError as exc:
                messagebox.showerror("Renombrar", str(exc))
                return
            if not queue.rename_batch_ids:
                self.active_queue_id = None
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
                    if self._refresh_queue_panel is not None:
                        self._refresh_queue_panel()
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

