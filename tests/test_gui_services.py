from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

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
from ig_orchestrator.gui.app import _latest_executed_batch_name
from ig_orchestrator.gui.account_catalog_service import AccountCatalogService
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    inspect_account_draft,
    normalize_url_lines,
    save_batch_draft,
)
from ig_orchestrator.gui.process_runner import build_run_continue_command
from ig_orchestrator.input import DuplicateBatchNameError
from ig_orchestrator.models import PublicationType, RunStatus, RunSummary, UrlSource


def test_gui_draft_is_persisted_as_sqlite_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    draft = BatchDraft(
        batch_name="gui_batch",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="@new_user",
                download_stories=True,
                urls=[
                    "https://www.instagram.com/reel/ABC123xyz/",
                    "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)

        assert result.batch.source_file is None
        assert result.batch.batch_name == "gui_batch"
        account = AccountRepository(connection).list_by_batch(result.batch.id)[0]
        assert account.username == "new_user"
        assert account.download_stories is True
        assert account.generated_story_url == "https://www.instagram.com/stories/new_user/"

        jobs = UrlJobRepository(connection).list_by_account(account.id)
        assert [(job.publication_type, job.source) for job in jobs] == [
            (PublicationType.STORY, UrlSource.GENERATED_STORY),
            (PublicationType.REEL, UrlSource.INPUT_URL),
            (PublicationType.POST, UrlSource.INPUT_URL),
        ]
        assert [row.user_name for row in AccountHistoryRepository(connection).list_all()] == [
            "new_user"
        ]


def test_account_catalog_reads_account_history(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        AccountHistoryRepository(connection).create_or_get("known_user")

        entries = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_entries()

    assert [entry.username for entry in entries] == ["known_user"]
    assert entries[0].source == "account_history"


def test_account_catalog_reads_config_batch_json(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_json_path = tmp_path / "batch.json"
    batch_json_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_name": "catalog",
                "defaults": {"start_now_date": "2026-07-06"},
                "accounts": [
                    {"username": "first_user", "start_now_date": "2026-06-21"},
                    {"username": ""},
                    {"username": "@second_user"},
                ],
            }
        ),
        encoding="utf-8",
    )
    init_database(db_path)

    with connect(db_path) as connection:
        entries = AccountCatalogService(
            connection,
            batch_json_path=batch_json_path,
        ).list_entries()

    assert [entry.username for entry in entries] == ["first_user", "second_user"]
    assert entries[0].start_now_date == "2026-06-21"
    assert all(entry.source == "batch.json" for entry in entries)


def test_account_catalog_is_sorted_alphabetically_case_insensitive(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        history = AccountHistoryRepository(connection)
        history.create_or_get("zeta_user")
        history.create_or_get("Alpha_user")
        history.create_or_get("middle_user")

        entries = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_entries()

    assert [entry.username for entry in entries] == [
        "Alpha_user",
        "middle_user",
        "zeta_user",
    ]


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


def test_gui_draft_rejects_account_without_stories_or_urls(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="empty_account",
        default_start_now_date="2026-07-06",
        accounts=[AccountDraft(username="empty_user")],
    )

    with connect(db_path) as connection:
        with pytest.raises(BatchDraftValidationError, match="enable stories"):
            save_batch_draft(draft, connection)


def test_gui_draft_rejects_duplicate_batch_name(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="duplicate_gui_batch",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="first_user",
                urls=["https://www.instagram.com/reel/ABC123xyz/"],
            )
        ],
    )

    with connect(db_path) as connection:
        save_batch_draft(draft, connection)
        assert BatchRepository(connection).get_by_name("duplicate_gui_batch") is not None

        with pytest.raises(DuplicateBatchNameError, match="already exists"):
            save_batch_draft(draft, connection)


def test_gui_url_normalization_accepts_quoted_comma_lists() -> None:
    assert normalize_url_lines(
        [
            '"https://www.instagram.com/p/DaGP2rHuY0P/",',
            '"https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",',
            '"https://www.instagram.com/p/DaO63b4t9_h/"',
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
        "https://www.instagram.com/p/DaO63b4t9_h/",
    ]


def test_gui_url_normalization_accepts_trailing_comma() -> None:
    assert normalize_url_lines(
        [
            '"https://www.instagram.com/p/DaGP2rHuY0P/",',
            '"https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",',
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
    ]


def test_gui_url_normalization_keeps_clean_line_lists() -> None:
    assert normalize_url_lines(
        [
            "https://www.instagram.com/p/DaGP2rHuY0P/",
            "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
    ]


def test_gui_url_normalization_removes_duplicate_clean_urls() -> None:
    assert normalize_url_lines(
        [
            "https://www.instagram.com/p/DaGP2rHuY0P/",
            '"https://www.instagram.com/p/DaGP2rHuY0P/",',
            "'https://www.instagram.com/p/DaGP2rHuY0P/'",
            "https://www.instagram.com/reel/ABC123xyz/",
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/reel/ABC123xyz/",
    ]


def test_gui_inspection_counts_duplicates_after_cleaning() -> None:
    summary = inspect_account_draft(
        AccountDraft(
            username="duplicate_user",
            urls=[
                "https://www.instagram.com/p/DaGP2rHuY0P/",
                '"https://www.instagram.com/p/DaGP2rHuY0P/",',
                "'https://www.instagram.com/p/DaGP2rHuY0P/'",
            ],
        ),
        default_start_now_date="2026-07-11",
    )

    assert summary.url_count == 1
    assert summary.duplicate_count == 2


def test_gui_normalization_treats_post_and_reel_with_same_shortcode_as_duplicate() -> None:
    assert normalize_url_lines(
        [
            "https://www.instagram.com/p/DWl1cUrD4gW/",
            "https://www.instagram.com/reel/DWl1cUrD4gW/",
            "https://www.instagram.com/reel/OTHER123/",
        ]
    ) == [
        "https://www.instagram.com/p/DWl1cUrD4gW/",
        "https://www.instagram.com/reel/OTHER123/",
    ]


def test_gui_inspection_counts_equivalent_post_and_reel_as_duplicate() -> None:
    summary = inspect_account_draft(
        AccountDraft(
            username="duplicate_format_user",
            urls=[
                "https://www.instagram.com/p/DWl1cUrD4gW/",
                "https://www.instagram.com/reel/DWl1cUrD4gW/",
            ],
        ),
        default_start_now_date="2026-07-11",
    )

    assert summary.url_count == 1
    assert summary.duplicate_count == 1


def test_gui_draft_validation_uses_comma_url_normalization(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="comma_urls",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="comma_user",
                urls=[
                    '"https://www.instagram.com/p/DaGP2rHuY0P/",',
                    '"https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",',
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = AccountRepository(connection).list_by_batch(result.batch.id)[0]

        jobs = UrlJobRepository(connection).list_by_account(account.id)

    assert [job.url for job in jobs] == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
    ]


def test_gui_draft_validation_removes_duplicate_clean_urls(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="duplicate_clean_urls",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="duplicate_user",
                urls=[
                    "https://www.instagram.com/p/DaGP2rHuY0P/",
                    '"https://www.instagram.com/p/DaGP2rHuY0P/",',
                    "https://www.instagram.com/reel/ABC123xyz/",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = AccountRepository(connection).list_by_batch(result.batch.id)[0]

        jobs = UrlJobRepository(connection).list_by_account(account.id)

    assert [job.url for job in jobs] == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/reel/ABC123xyz/",
    ]


def test_gui_initial_batch_name_uses_latest_executed_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        older = save_batch_draft(
            BatchDraft(
                batch_name="older_batch",
                default_start_now_date="2026-07-06",
                accounts=[
                    AccountDraft(
                        username="older_user",
                        urls=["https://www.instagram.com/reel/ABC123xyz/"],
                    )
                ],
            ),
            connection,
        ).batch
        newer = save_batch_draft(
            BatchDraft(
                batch_name="newer_batch",
                default_start_now_date="2026-07-06",
                accounts=[
                    AccountDraft(
                        username="newer_user",
                        urls=["https://www.instagram.com/reel/DEF123xyz/"],
                    )
                ],
            ),
            connection,
        ).batch
        run_repository = RunRepository(connection)
        run_repository.create(
            RunSummary(status=RunStatus.COMPLETED),
            batch_id=newer.id,
            started_at=datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc),
        )
        run_repository.create(
            RunSummary(status=RunStatus.COMPLETED),
            batch_id=older.id,
            started_at=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
        )

        assert _latest_executed_batch_name(connection) == "older_batch"


def test_gui_initial_batch_name_falls_back_to_latest_saved_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        save_batch_draft(
            BatchDraft(
                batch_name="saved_batch",
                default_start_now_date="2026-07-06",
                accounts=[
                    AccountDraft(
                        username="saved_user",
                        urls=["https://www.instagram.com/reel/ABC123xyz/"],
                    )
                ],
            ),
            connection,
        )

        assert _latest_executed_batch_name(connection) == "saved_batch"
