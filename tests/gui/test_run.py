from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk

import pytest

from ig_orchestrator.db import (
    AccountHistoryRepository,
    AccountRepository,
    BatchRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.db.migrations import apply_migrations
from ig_orchestrator.gui.app import (
    _BATCH_COLUMNS,
    InstagramOrchestratorApp,
    _account_display_status,
    _batch_column_samples,
    _batch_mode_details,
    batch_username_matches_filter,
    catalog_focus_username,
    _catalog_entry_colors,
    _catalog_width_chars,
    filter_batch_accounts,
    _half_screen_geometry,
    _instagram_profile_url,
    _open_chrome_tab,
    _play_completion_sound,
    _set_ttk_enabled,
    _latest_executed_batch_name,
    _new_account_rename_parameters,
    _sort_accounts_by_username,
    stories_cell_text,
    _timestamp_console_text,
    _username_heading_title,
)
from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogEntry,
    AccountCatalogService,
    filter_catalog_entries,
    list_usernames_active_on_date,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    inspect_account_draft,
    normalize_url_lines,
    save_batch_draft,
    validate_batch_draft,
)
from ig_orchestrator.gui.batch_resume_service import (
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
    list_pending_batches,
    load_batch_draft,
    mark_batch_executed_elsewhere,
    mark_batch_interrupted,
    resolve_account_download_folder,
)
from ig_orchestrator.gui.batch_transfer_service import (
    BatchTransferError,
    export_batch_payload,
    import_batch_from_payload,
)
from ig_orchestrator.gui.process_runner import (
    NewAccountRenameParameters,
    build_manual_rename_command,
    build_run_continue_command,
    format_command_for_shell,
    format_manual_rename_command_preview,
)
from ig_orchestrator.gui.rename_folder_status import (
    decide_rename_completion,
    has_unmoved_account_folders,
    list_unmoved_account_folders,
)
from ig_orchestrator.input import DuplicateBatchNameError
from ig_orchestrator.models import (
    AccountHistoryStatus,
    AccountStatus,
    InputBatchStatus,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.settings import Settings

def _draft_with_name(name: str, username: str, *, new_account: bool = False) -> BatchDraft:
    return BatchDraft(
        batch_name=name,
        default_start_now_date="2026-08-15",
        accounts=[
            AccountDraft(
                username=username,
                urls=["https://www.instagram.com/reel/QUEUE1/"],
                is_new_account=new_account,
                owner_id="111" if new_account else "",
                start_init_date="2025-01-01" if new_account else "",
                destination_path=r"G:\4K Stogram\00.MODELS-A" if new_account else "",
            )
        ],
    )


def test_gui_plays_native_completion_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beeps: list[int] = []
    bells: list[bool] = []
    fake_winsound = SimpleNamespace(
        MB_OK=0,
        MessageBeep=lambda sound: beeps.append(sound),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    root = SimpleNamespace(bell=lambda: bells.append(True))

    _play_completion_sound(root)

    assert beeps == [0]
    assert bells == []


def test_gui_run_continue_command_uses_current_python_and_batch_id() -> None:
    command = build_run_continue_command(42)

    assert command[1:] == ["-m", "ig_orchestrator", "run_continue", "--batch-id", "42"]


def test_gui_dry_run_option_is_placed_before_subcommand() -> None:
    command = build_run_continue_command(42, dry_run=True)

    assert command[1:] == [
        "-m",
        "ig_orchestrator",
        "--dry-run",
        "run_continue",
        "--batch-id",
        "42",
    ]


def test_gui_console_prefixes_every_line_with_millisecond_timestamp() -> None:
    formatted = _timestamp_console_text(
        "Primer evento\nSegundo evento\n",
        now=datetime(2026, 6, 21, 17, 48, 57, 983000),
    )

    assert formatted == (
        "2026-06-21 17:48:57.983 Primer evento\n"
        "2026-06-21 17:48:57.983 Segundo evento\n"
    )


