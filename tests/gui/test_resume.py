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


def test_gui_lists_and_recovers_pending_batch_from_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="recover_me",
        default_start_now_date="2026-07-18",
        accounts=[
            AccountDraft(
                username="new_recovered_user",
                download_stories=True,
                urls=["https://www.instagram.com/reel/RECOVER123/"],
                start_now_date="2026-07-17",
                is_new_account=True,
                owner_id="9988",
                start_init_date="2025-12-01",
                destination_path=r"G:\Models",
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        managed = list_managed_batches(connection)

        assert [(item.batch_id, item.batch_name) for item in managed] == [
            (result.batch.id, "recover_me")
        ]
        assert managed[0].status == "DRAFT"
        assert managed[0].total_accounts == 1
        assert managed[0].url_count == 1
        assert list_pending_batches(connection) == []

        recovered = load_batch_draft(connection, result.batch.id)
        assert recovered == draft


def test_gui_managed_batches_report_total_url_count(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="two_accounts_urls",
        default_start_now_date="2026-08-08",
        accounts=[
            AccountDraft(
                username="account_a",
                urls=[
                    f"https://www.instagram.com/reel/AAAA{i:02d}/"
                    for i in range(50)
                ],
            ),
            AccountDraft(
                username="account_b",
                urls=[
                    f"https://www.instagram.com/reel/BBBB{i:02d}/"
                    for i in range(50)
                ],
            ),
        ],
    )
    empty = BatchDraft(
        batch_name="empty_urls_batch",
        default_start_now_date="2026-08-08",
        accounts=[AccountDraft(username="no_urls_yet", download_stories=True)],
    )

    with connect(db_path) as connection:
        save_batch_draft(draft, connection)
        save_batch_draft(empty, connection)
        managed = {
            item.batch_name: item for item in list_managed_batches(connection)
        }

        assert managed["two_accounts_urls"].url_count == 100
        assert managed["two_accounts_urls"].total_accounts == 2
        assert managed["empty_urls_batch"].url_count == 0


def test_gui_resume_columns_are_added_to_an_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE input_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                source_file TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER,
                username TEXT NOT NULL,
                start_now_date TEXT NOT NULL,
                download_stories INTEGER NOT NULL DEFAULT 0,
                generated_story_url TEXT,
                working_folder TEXT,
                final_destination_folder TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        apply_migrations(connection)

        batch_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(input_batches)")
        }
        account_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
        }
        assert "default_start_now_date" in batch_columns
        assert {
            "is_new_account",
            "rename_owner_id",
            "rename_start_init_date",
            "rename_destination_path",
        } <= account_columns


def test_gui_runtime_progress_and_manual_finish(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="runtime_batch",
        default_start_now_date="2026-07-18",
        accounts=[
            AccountDraft(
                username="runtime_user",
                urls=[
                    "https://www.instagram.com/reel/RUNTIME1/",
                    "https://www.instagram.com/reel/RUNTIME2/",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        UrlJobRepository(connection).update_status(jobs[0].id, UrlJobStatus.COMPLETED)
        UrlJobRepository(connection).update_error(
            jobs[1].id,
            status=UrlJobStatus.RETRY_PENDING,
            last_error="temporary",
            last_error_type="TEMPORARY",
            non_retryable=False,
        )
        AccountRepository(connection).update_status(account.id, AccountStatus.PARTIAL)

        progress = get_account_runtime_progress(connection, result.batch.id)
        assert progress[0].completed_items == 1
        assert progress[0].retry_items == 1

        mark_batch_interrupted(connection, result.batch.id)
        assert BatchRepository(connection).get_by_id(result.batch.id).status is InputBatchStatus.PARTIAL
        assert list_pending_batches(connection)

        finish_batch(connection, result.batch.id)
        assert BatchRepository(connection).get_by_id(result.batch.id).status is InputBatchStatus.COMPLETED
        assert list_pending_batches(connection) == []


def test_list_account_problem_urls_filters_retry_and_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="problem_urls",
        default_start_now_date="2026-08-08",
        accounts=[
            AccountDraft(
                username="problem_user",
                urls=[
                    "https://www.instagram.com/reel/OKDONE01/",
                    "https://www.instagram.com/reel/RETRYME01/",
                    "https://www.instagram.com/reel/RETRYME02/",
                    "https://www.instagram.com/reel/FAILME01/",
                    "https://www.instagram.com/p/STILLPENDING/",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        repo = UrlJobRepository(connection)
        repo.update_status(jobs[0].id, UrlJobStatus.COMPLETED)
        repo.update_error(
            jobs[1].id,
            status=UrlJobStatus.RETRY_PENDING,
            last_error="timeout",
            last_error_type="TEMPORARY",
            non_retryable=False,
        )
        repo.update_error(
            jobs[2].id,
            status=UrlJobStatus.FAILED_TEMPORARY,
            last_error="Media not found or unavailable",
            last_error_type="TEMPORARY",
            non_retryable=False,
        )
        repo.update_error(
            jobs[3].id,
            status=UrlJobStatus.FAILED_FINAL,
            last_error="We're sorry, we couldn't find that.",
            last_error_type="NOT_FOUND",
            non_retryable=True,
        )
        # jobs[4] stays PENDING

        retry_rows = list_account_problem_urls(
            connection,
            account_id=account.id,
            kind="retry",
        )
        failed_rows = list_account_problem_urls(
            connection,
            account_id=account.id,
            kind="failed",
        )
        completed_rows = list_account_problem_urls(
            connection,
            account_id=account.id,
            kind="completed",
        )

        assert [row.url for row in retry_rows] == [
            "https://www.instagram.com/reel/RETRYME01/",
            "https://www.instagram.com/reel/RETRYME02/",
        ]
        assert retry_rows[0].last_error == "timeout"
        assert [row.url for row in failed_rows] == [
            "https://www.instagram.com/reel/FAILME01/",
        ]
        assert failed_rows[0].status == UrlJobStatus.FAILED_FINAL.value
        assert [row.url for row in completed_rows] == [
            "https://www.instagram.com/reel/OKDONE01/",
        ]
        assert completed_rows[0].status == UrlJobStatus.COMPLETED.value

        progress = get_account_runtime_progress(connection, result.batch.id)[0]
        status_label, status_tag = _account_display_status(
            draft.accounts[0],
            progress,
        )
        assert status_tag == "retry"
        assert "Reintento" in status_label
        assert progress.retry_items == 2
        assert progress.failed_items == 1
        assert progress.completed_items == 1


def test_list_historical_batches_only_completed(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft_active = BatchDraft(
        batch_name="still_active",
        default_start_now_date="2026-08-11",
        accounts=[
            AccountDraft(
                username="active_user",
                urls=["https://www.instagram.com/reel/ACTIVE01/"],
            )
        ],
    )
    draft_done = BatchDraft(
        batch_name="already_done",
        default_start_now_date="2026-08-10",
        accounts=[
            AccountDraft(
                username="done_user",
                urls=["https://www.instagram.com/reel/DONE01/"],
            )
        ],
    )
    with connect(db_path) as connection:
        active = save_batch_draft(draft_active, connection)
        done = save_batch_draft(draft_done, connection)
        finish_batch(connection, done.batch.id)

        historical = list_historical_batches(connection)
        managed = list_managed_batches(connection)

        assert [item.batch_id for item in historical] == [done.batch.id]
        assert historical[0].display_status == "COMPLETADO"
        assert historical[0].url_count == 1
        assert all(item.batch_id != done.batch.id for item in managed)
        assert any(item.batch_id == active.batch.id for item in managed)


def test_resolve_account_download_folder_prefers_stored_path(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    working_root = tmp_path / "working"
    stored_folder = working_root / "folder_user"
    stored_folder.mkdir(parents=True)
    fallback_folder = working_root / "fallback_user"
    fallback_folder.mkdir()
    draft = BatchDraft(
        batch_name="folder_resolve",
        default_start_now_date="2026-08-11",
        accounts=[
            AccountDraft(
                username="folder_user",
                urls=["https://www.instagram.com/reel/FOLDER01/"],
            ),
            AccountDraft(
                username="fallback_user",
                urls=["https://www.instagram.com/reel/FOLDER02/"],
            ),
            AccountDraft(
                username="missing_user",
                urls=["https://www.instagram.com/reel/FOLDER03/"],
            ),
        ],
    )
    settings = Settings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telethon_session_name="session",
        telegram_download_bot_username="@bot",
        telegram_desktop_download_folder=tmp_path / "tg",
        working_folder=working_root,
        reports_folder=tmp_path / "reports",
        sqlite_db_path=db_path,
        max_retries=3,
        retry_base_seconds=90,
        retry_max_seconds=900,
        download_wait_timeout_seconds=300,
        download_stable_seconds=10,
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection, settings=settings)
        by_name = {account.username: account for account in result.accounts}
        stored = by_name["folder_user"]
        connection.execute(
            "UPDATE accounts SET working_folder = ? WHERE id = ?",
            (str(stored_folder), stored.id),
        )
        connection.commit()

        assert resolve_account_download_folder(
            connection,
            account_id=stored.id,
            username="folder_user",
            working_folder_setting=working_root,
        ) == stored_folder

        fallback = by_name["fallback_user"]
        connection.execute(
            "UPDATE accounts SET working_folder = NULL WHERE id = ?",
            (fallback.id,),
        )
        connection.commit()
        assert resolve_account_download_folder(
            connection,
            account_id=fallback.id,
            username="fallback_user",
            working_folder_setting=working_root,
        ) == fallback_folder

        missing = by_name["missing_user"]
        assert (
            resolve_account_download_folder(
                connection,
                account_id=missing.id,
                username="missing_user",
                working_folder_setting=working_root,
            )
            is None
        )


def test_gui_manual_account_removal_marks_non_terminal_urls_and_account_failed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="remove_account",
        default_start_now_date="2026-07-22",
        accounts=[
            AccountDraft(
                username="blocked_user",
                urls=[
                    "https://www.instagram.com/reel/BLOCKED1/",
                    "https://www.instagram.com/reel/BLOCKED2/",
                ],
            )
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        UrlJobRepository(connection).update_status(jobs[0].id, UrlJobStatus.COMPLETED)

        affected = fail_account_manually(
            connection,
            batch_id=result.batch.id,
            account_id=account.id,
        )
        stored_account = AccountRepository(connection).get_by_id(account.id)
        stored_jobs = UrlJobRepository(connection).list_by_account(account.id)

    assert affected == 1
    assert stored_account.status is AccountStatus.FAILED
    assert stored_jobs[0].status is UrlJobStatus.COMPLETED
    assert stored_jobs[1].status is UrlJobStatus.FAILED_FINAL
    assert stored_jobs[1].last_error_type == "MANUAL_ACCOUNT_REMOVAL"
    assert stored_jobs[1].non_retryable is True


def test_gui_manual_completion_closes_stuck_account_and_enables_rename(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="stuck_account",
        default_start_now_date="2026-07-22",
        accounts=[
            AccountDraft(
                username="stuck_user",
                urls=["https://www.instagram.com/reel/STUCK1/"],
            )
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        activate_draft_batch(connection, result.batch.id)
        mark_batch_interrupted(connection, result.batch.id)
        RunRepository(connection).create(
            RunSummary(status=RunStatus.PROCESSING, total_urls=1, summary="Processing batch"),
            batch_id=result.batch.id,
        )
        account = result.accounts[0]

        affected = complete_account_manually(
            connection,
            batch_id=result.batch.id,
            account_id=account.id,
        )
        stored_job = UrlJobRepository(connection).list_by_account(account.id)[0]

        assert affected == 1
        assert AccountRepository(connection).get_by_id(account.id).status is AccountStatus.COMPLETED
        assert stored_job.status is UrlJobStatus.FAILED_FINAL
        assert stored_job.last_error_type == "MANUAL_ACCOUNT_COMPLETION"
        assert (
            BatchRepository(connection).get_by_id(result.batch.id).status
            is InputBatchStatus.AWAITING_RENAME
        )
        assert is_batch_ready_for_rename(connection, result.batch.id) is True
        managed = list_managed_batches(connection)
        assert any(
            item.batch_id == result.batch.id and item.is_awaiting_rename
            for item in managed
        )


def test_gui_mark_executed_elsewhere_moves_to_awaiting_rename(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="elsewhere_batch",
        default_start_now_date="2026-08-05",
        accounts=[
            AccountDraft(
                username="elsewhere_user",
                urls=["https://www.instagram.com/reel/ELSE1/"],
                start_now_date="2026-08-05",
            )
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        mark_batch_executed_elsewhere(connection, result.batch.id)
        stored = BatchRepository(connection).get_by_id(result.batch.id)
        account = AccountRepository(connection).get_by_id(result.accounts[0].id)
        jobs = UrlJobRepository(connection).list_by_account(result.accounts[0].id)

        assert stored.status is InputBatchStatus.AWAITING_RENAME
        assert account.status is AccountStatus.COMPLETED
        assert jobs[0].status is UrlJobStatus.FAILED_FINAL
        assert jobs[0].last_error_type == "EXECUTED_ELSEWHERE"
        assert is_batch_ready_for_rename(connection, result.batch.id) is True
        assert list_pending_batches(connection) == []
        assert any(
            item.batch_id == result.batch.id and item.display_status == "POR RENOMBRAR"
            for item in list_managed_batches(connection)
        )


