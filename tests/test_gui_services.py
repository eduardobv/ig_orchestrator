from __future__ import annotations

import json
from pathlib import Path

import pytest

from ig_orchestrator.db import (
    AccountHistoryRepository,
    AccountRepository,
    BatchRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.gui.account_catalog_service import AccountCatalogService
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    save_batch_draft,
)
from ig_orchestrator.input import DuplicateBatchNameError
from ig_orchestrator.models import PublicationType, UrlSource


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
