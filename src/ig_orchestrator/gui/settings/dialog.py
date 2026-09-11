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


class SettingsDialogMixin:
    """Mixin: configuration dialog."""

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
        ttk.Label(frame, text=t("settings.processing")).grid(
            row=5, column=0, sticky="w", pady=(8, 4)
        )
        stories_first = tk.BooleanVar(
            value=read_stories_first_enabled(self.connection)
        )

        def apply_stories_first() -> None:
            write_stories_first_enabled(self.connection, stories_first.get())

        ttk.Checkbutton(
            frame,
            text=t("settings.stories_first"),
            variable=stories_first,
            command=apply_stories_first,
        ).grid(row=6, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.stories_first_help"), wraplength=520).grid(
            row=7, column=0, sticky="w", pady=(2, 12)
        )
        ttk.Button(
            frame,
            text=t("settings.purge_files"),
            command=lambda: self._purge_downloaded_files(window),
        ).grid(row=8, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.colors")).grid(
            row=9, column=0, sticky="w", pady=(16, 4)
        )
        color_row = ttk.Frame(frame)
        color_row.grid(row=10, column=0, sticky="w")
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
            row=11, column=0, sticky="w", pady=(16, 4)
        )
        notify_enabled = tk.BooleanVar(
            value=_gui_setting(self.connection, "notify.enabled", "0") in {"1", "true"}
        )
        ttk.Checkbutton(
            frame, text=t("settings.notify_enable"), variable=notify_enabled
        ).grid(row=12, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.notify_target")).grid(
            row=13, column=0, sticky="w", pady=(6, 0)
        )
        target_var = tk.StringVar(
            value=_gui_setting(self.connection, "notify.target", "me")
        )
        ttk.Entry(frame, textvariable=target_var, width=32).grid(
            row=14, column=0, sticky="w"
        )
        ttk.Label(frame, text=t("settings.notify_template")).grid(
            row=15, column=0, sticky="w", pady=(6, 0)
        )
        template_var = tk.StringVar(
            value=_gui_setting(
                self.connection,
                "notify.template_batch_done",
                t("settings.notify_template_default"),
            )
        )
        ttk.Entry(frame, textvariable=template_var, width=64).grid(
            row=16, column=0, sticky="ew"
        )
        ttk.Label(frame, text=t("settings.notify_errors")).grid(
            row=17, column=0, sticky="w", pady=(8, 2)
        )
        error_vars: dict[str, tk.BooleanVar] = {}
        error_frame = ttk.Frame(frame)
        error_frame.grid(row=18, column=0, sticky="w")
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
            row=19, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Button(
            frame,
            text=t("settings.notify_test"),
            command=lambda: self._send_test_notification(
                window, target_var.get().strip() or "me"
            ),
        ).grid(row=20, column=0, sticky="w", pady=(4, 0))
        ttk.Button(frame, text=t("settings.close"), command=window.destroy).grid(
            row=21, column=0, sticky="e", pady=(16, 0)
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

