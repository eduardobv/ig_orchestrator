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


def test_gui_manual_rename_command_uses_global_start_date() -> None:
    script_path = Path(r"D:\tools\ManualRenameFiles\main.py")

    command = build_manual_rename_command("2026-07-16", script_path=script_path)

    assert command[1:] == [
        str(script_path),
        "--newRename",
        "--startNowDate",
        "2026-07-16",
        "--no-duplicated",
        "--move-renamed",
    ]


def test_gui_manual_rename_command_adds_all_new_accounts_in_order() -> None:
    script_path = Path(r"D:\tools\ManualRenameFiles\main.py")

    command = build_manual_rename_command(
        "2026-07-16",
        script_path=script_path,
        new_accounts=(
            NewAccountRenameParameters(
                username="ddmarii",
                owner_id="436651863",
                start_init_date="2025-12-14",
                destination_path=r"G:\4K Stogram\00.MODELS-D",
            ),
            NewAccountRenameParameters(
                username="second_account",
                owner_id="987654321",
                start_init_date="2026-01-10",
                destination_path=r"G:\4K Stogram\00.MODELS-C",
            ),
        ),
    )

    assert command[1:] == [
        str(script_path),
        "--newRename",
        "--startNowDate",
        "2026-07-16",
        "--new-account",
        "ddmarii",
        "436651863",
        "2025-12-14",
        r"G:\4K Stogram\00.MODELS-D",
        "--new-account",
        "second_account",
        "987654321",
        "2026-01-10",
        r"G:\4K Stogram\00.MODELS-C",
        "--no-duplicated",
        "--move-renamed",
    ]


def test_gui_manual_rename_command_preview_includes_shell_line_and_params() -> None:
    script_path = Path(r"D:\tools\ManualRenameFiles\main.py")
    new_accounts = (
        NewAccountRenameParameters(
            username="ddmarii",
            owner_id="436651863",
            start_init_date="2025-12-14",
            destination_path=r"G:\4K Stogram\00.MODELS-D",
        ),
    )
    command = build_manual_rename_command(
        "2026-07-16",
        script_path=script_path,
        new_accounts=new_accounts,
    )
    preview = format_manual_rename_command_preview(
        "2026-07-16",
        script_path=script_path,
        new_accounts=new_accounts,
    )

    assert format_command_for_shell(command) in preview
    assert "--newRename" in preview
    assert "--startNowDate 2026-07-16" in preview
    assert "ddmarii" in preview
    assert r"G:\4K Stogram\00.MODELS-D" in preview
    assert "--no-duplicated" in preview
    assert "--move-renamed" in preview
    assert "[0]" in preview


def test_list_unmoved_account_folders_ignores_files_and_hidden_dirs(tmp_path: Path) -> None:
    working = tmp_path / "working"
    working.mkdir()
    (working / "readme.txt").write_text("x", encoding="utf-8")
    (working / ".hidden").mkdir()
    leftover = working / "Some-Renamed-Account"
    leftover.mkdir()
    (working / "another_user").mkdir()

    leftovers = list_unmoved_account_folders(working)

    assert [path.name for path in leftovers] == ["another_user", "Some-Renamed-Account"]
    assert has_unmoved_account_folders(working) is True
    assert list_unmoved_account_folders(tmp_path / "missing") == []
    assert has_unmoved_account_folders(None) is False


def test_list_unmoved_account_folders_empty_when_only_files(tmp_path: Path) -> None:
    working = tmp_path / "working"
    working.mkdir()
    (working / "telegram_media.jpg").write_bytes(b"x")

    assert list_unmoved_account_folders(working) == []
    assert has_unmoved_account_folders(working) is False


def test_decide_rename_completion_keeps_button_when_folders_remain(tmp_path: Path) -> None:
    leftover = tmp_path / "still_here"
    leftover.mkdir()

    with_leftovers = decide_rename_completion(
        exit_code=0,
        leftover_folders=[leftover],
    )
    assert with_leftovers.mark_completed is False
    assert with_leftovers.keep_rename_enabled is True
    assert with_leftovers.leftover_folders == (leftover,)

    clean_success = decide_rename_completion(exit_code=0, leftover_folders=[])
    assert clean_success.mark_completed is True
    assert clean_success.keep_rename_enabled is False

    failed = decide_rename_completion(exit_code=1, leftover_folders=[])
    assert failed.mark_completed is False
    assert failed.keep_rename_enabled is True


def test_gui_rename_parameters_only_include_checked_new_accounts() -> None:
    parameters = _new_account_rename_parameters(
        [
            AccountDraft(username="existing", is_new_account=False),
            AccountDraft(
                username="update_user",
                is_catalog_update=True,
                owner_id="999",
                destination_path=r"G:\Models\Existing",
            ),
            AccountDraft(
                username="new_user",
                is_new_account=True,
                owner_id="123",
                start_init_date="2026-01-01",
                destination_path=r"G:\Models",
            ),
        ]
    )

    assert parameters == (
        NewAccountRenameParameters(
            username="new_user",
            owner_id="123",
            start_init_date="2026-01-01",
            destination_path=r"G:\Models",
        ),
    )


def test_rename_mixin_binds_manual_rename_script() -> None:
    from ig_orchestrator.gui.run import rename as rename_mod

    assert rename_mod.MANUAL_RENAME_SCRIPT.name == "main.py"
    assert rename_mod.NewAccountRenameParameters is NewAccountRenameParameters


