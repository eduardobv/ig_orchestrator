from __future__ import annotations

from copy import deepcopy
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
    center_modal_on_parent,
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


class SettingsDialogWithTabs:
    """Settings dialog with tabbed interface for organized configuration."""

    def __init__(self, parent: tk.Tk, connection, root_for_center):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(t("settings.title"))
        self.dialog.transient(parent)
        self.connection = connection
        self.parent = parent
        self.root_for_center = root_for_center
        self.saved = False

        # Main notebook
        main_frame = ttk.Frame(self.dialog, padding=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # Build tabs
        self._build_general_tab()
        self._build_ui_tab()
        self._build_processing_tab()
        self._build_catalog_tab()
        self._build_notify_tab()

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 0))
        ttk.Button(button_frame, text=t("settings.save"), command=self._on_save).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(button_frame, text=t("settings.cancel"), command=self._on_cancel).pack(
            side=tk.RIGHT, padx=4
        )

        center_modal_on_parent(
            self.dialog, root_for_center, root_for_center.state() == "zoomed"
        )

    def _build_general_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=t("settings.tabs.general"))

        ttk.Label(frame, text=t("settings.language")).grid(row=0, column=0, sticky="w")
        self.language = tk.StringVar(value=current_language())
        ttk.Radiobutton(
            frame,
            text=t("settings.language.es"),
            value="es",
            variable=self.language,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Radiobutton(
            frame,
            text=t("settings.language.en"),
            value="en",
            variable=self.language,
        ).grid(row=2, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.language_restart")).grid(
            row=3, column=0, sticky="w", pady=(6, 10)
        )

    def _build_ui_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=t("settings.tabs.ui"))

        ttk.Label(frame, text=t("settings.window_position")).grid(
            row=0, column=0, sticky="w"
        )
        self.window_position = tk.StringVar(
            value=_gui_setting(self.connection, "ui.window_position", "left")
        )
        positions_row = ttk.Frame(frame)
        positions_row.grid(row=1, column=0, sticky="w", pady=(0, 12))
        for index, position in enumerate(("left", "center", "right")):
            ttk.Radiobutton(
                positions_row,
                text=t(f"settings.window_position_{position}"),
                value=position,
                variable=self.window_position,
            ).grid(row=0, column=index, sticky="w", padx=(0, 16))

    def _build_processing_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=t("settings.tabs.processing"))

        self.stories_first = tk.BooleanVar(
            value=read_stories_first_enabled(self.connection)
        )
        ttk.Checkbutton(
            frame,
            text=t("settings.stories_first"),
            variable=self.stories_first,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=t("settings.stories_first_help"), wraplength=500).grid(
            row=1, column=0, sticky="w", pady=(2, 12)
        )
        ttk.Button(
            frame,
            text=t("settings.purge_files"),
            command=lambda: self._purge_downloaded_files(),
        ).grid(row=2, column=0, sticky="w")

    def _build_catalog_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=t("settings.tabs.catalog"))

        ttk.Label(frame, text=t("settings.colors")).grid(row=0, column=0, sticky="w")
        color_row = ttk.Frame(frame)
        color_row.grid(row=1, column=0, sticky="w", pady=(0, 12))
        self.color_buttons: dict[str, ttk.Button] = {}
        for index, (key, label_key) in enumerate(
            (
                ("favorite", "settings.color_favorite"),
                ("in_batch", "settings.color_in_batch"),
                ("today", "settings.color_today"),
                ("inactive", "settings.color_inactive"),
                ("disabled", "settings.color_disabled"),
            )
        ):
            btn = ttk.Button(
                color_row,
                text=t(label_key),
                command=lambda k=key: self._pick_catalog_color(k),
            )
            btn.grid(row=0, column=index, padx=(0, 4))
            self.color_buttons[key] = btn

    def _build_notify_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=t("settings.tabs.notify"))

        self.notify_enabled = tk.BooleanVar(
            value=_gui_setting(self.connection, "notify.enabled", "0")
            in {"1", "true"}
        )
        ttk.Checkbutton(
            frame, text=t("settings.notify_enable"), variable=self.notify_enabled
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        ttk.Label(frame, text=t("settings.notify_target")).grid(
            row=1, column=0, sticky="w", pady=(0, 0)
        )
        self.target_var = tk.StringVar(
            value=_gui_setting(self.connection, "notify.target", "me")
        )
        ttk.Entry(frame, textvariable=self.target_var, width=32).grid(
            row=2, column=0, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text=t("settings.notify_template")).grid(
            row=3, column=0, sticky="w", pady=(0, 0)
        )
        self.template_var = tk.StringVar(
            value=_gui_setting(
                self.connection,
                "notify.template_batch_done",
                t("settings.notify_template_default"),
            )
        )
        ttk.Entry(frame, textvariable=self.template_var, width=64).grid(
            row=4, column=0, sticky="ew", pady=(0, 12)
        )

        ttk.Label(frame, text=t("settings.notify_errors")).grid(
            row=5, column=0, sticky="w", pady=(0, 4)
        )
        error_frame = ttk.Frame(frame)
        error_frame.grid(row=6, column=0, sticky="w")
        self.error_vars: dict[str, tk.BooleanVar] = {}
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
                self.error_vars[str(row["code"])] = var
                ttk.Checkbutton(
                    error_frame,
                    text=f"{row['code']}",
                    variable=var,
                ).grid(row=index, column=0, sticky="w")

        ttk.Button(
            frame,
            text=t("settings.notify_test"),
            command=self._send_test_notification,
        ).grid(row=7, column=0, sticky="w", pady=(12, 0))

    def _on_save(self) -> None:
        """Apply changes and close dialog."""
        if is_gui_schema(self.connection):
            # Language
            if self.language.get() != current_language():
                self.connection.execute(
                    """
                    INSERT INTO app_settings (key, value, value_type, updated_at)
                    VALUES ('ui.language', ?, 'TEXT', datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (self.language.get(),),
                )

            # Window position
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('ui.window_position', ?, 'TEXT', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (self.window_position.get(),),
            )

            # Stories first
            write_stories_first_enabled(self.connection, self.stories_first.get())

            # Notify settings
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('notify.enabled', ?, 'BOOLEAN', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                ("1" if self.notify_enabled.get() else "0",),
            )
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('notify.target', ?, 'TEXT', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                (self.target_var.get().strip() or "me",),
            )
            self.connection.execute(
                """
                INSERT INTO app_settings (key, value, value_type, updated_at)
                VALUES ('notify.template_batch_done', ?, 'TEXT', datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value, updated_at = excluded.updated_at
                """,
                (self.template_var.get() or " ",),
            )
            for code, var in self.error_vars.items():
                self.connection.execute(
                    """
                    UPDATE bot_errors
                    SET notify_on_match = ?
                    WHERE code = ?
                    """,
                    (int(var.get()), code),
                )
            self.connection.commit()

        self.saved = True
        if self.language.get() != current_language():
            self.dialog.destroy()
            import subprocess
            import sys
            subprocess.Popen([sys.executable, "-m", "ig_orchestrator", "gui"])
        else:
            self.dialog.destroy()

    def _on_cancel(self) -> None:
        """Close dialog without saving."""
        self.dialog.destroy()

    def _pick_catalog_color(self, key: str) -> None:
        from ig_orchestrator.gui.catalog_colors import load_catalog_colors

        catalog_colors = load_catalog_colors(self.connection)
        current = catalog_colors.get(key) or "#ffffff"
        _rgb, hex_color = colorchooser.askcolor(color=current, parent=self.dialog)
        if not hex_color:
            return
        save_color(self.connection, key, hex_color)

    def _send_test_notification(self) -> None:
        import asyncio

        try:
            from ig_orchestrator.settings import load_settings

            settings = load_settings()
            asyncio.run(_send_test_telegram(settings, self.target_var.get().strip() or "me"))
        except Exception as exc:
            messagebox.showerror(
                t("settings.notify_test"), str(exc), parent=self.dialog
            )
            return
        messagebox.showinfo(
            t("settings.notify_test"),
            t("settings.notify_test_ok"),
            parent=self.dialog,
        )

    def _purge_downloaded_files(self) -> None:
        if not messagebox.askyesno(
            t("settings.purge_files"),
            t("settings.purge_confirm"),
            parent=self.dialog,
        ):
            return
        count = purge_downloaded_files(self.connection)
        messagebox.showinfo(
            t("settings.purge_files"),
            t("settings.purged", count=count),
            parent=self.dialog,
        )


class SettingsDialogMixin:
    """Mixin: configuration dialog."""

    def _open_settings(self) -> None:
        dialog = SettingsDialogWithTabs(self.root, self.connection, self.root)
        self.root.wait_window(dialog.dialog)
        if dialog.saved and dialog.language.get() != current_language():
            return
        if dialog.saved:
            self.catalog_colors = load_catalog_colors(self.connection)
            self._refresh_catalog()


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

