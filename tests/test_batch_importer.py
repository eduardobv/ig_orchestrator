from __future__ import annotations

import json
from pathlib import Path

from ig_orchestrator.db import (
    AccountRepository,
    ConfigRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.input import import_batch_json
from ig_orchestrator.models import ConfigValueType, PublicationType, UrlSource
from ig_orchestrator.settings import Settings


def test_import_batch_with_two_accounts_and_generated_story(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_path = _write_batch(tmp_path)
    init_database(db_path)

    with connect(db_path) as connection:
        result = import_batch_json(batch_path, connection)

        assert result.batch.batch_name == "descargas_junio_2026"
        assert len(result.accounts) == 2
        assert len(result.url_jobs) == 5

        first_account = result.accounts[0]
        assert first_account.download_stories is True
        assert (
            first_account.generated_story_url
            == "https://www.instagram.com/stories/example_user/"
        )

        jobs = UrlJobRepository(connection).list_by_account(first_account.id)
        assert [(job.url, job.publication_type, job.source) for job in jobs] == [
            (
                "https://www.instagram.com/stories/example_user/",
                PublicationType.STORY,
                UrlSource.GENERATED_STORY,
            ),
            (
                "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
                PublicationType.POST,
                UrlSource.INPUT_URL,
            ),
            (
                "https://www.instagram.com/reel/ABC123xyz/",
                PublicationType.REEL,
                UrlSource.INPUT_URL,
            ),
        ]

        second_account = result.accounts[1]
        jobs = UrlJobRepository(connection).list_by_account(second_account.id)
        assert [(job.publication_type, job.source) for job in jobs] == [
            (PublicationType.HIGHLIGHTS, UrlSource.INPUT_URL),
            (PublicationType.REEL, UrlSource.INPUT_URL),
        ]


def test_reimporting_same_batch_does_not_duplicate_accounts_or_urls(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_path = _write_batch(tmp_path)
    init_database(db_path)

    with connect(db_path) as connection:
        first_result = import_batch_json(batch_path, connection)
        second_result = import_batch_json(batch_path, connection)

        assert first_result.batch.id == second_result.batch.id
        assert [account.id for account in first_result.accounts] == [
            account.id for account in second_result.accounts
        ]

        accounts = AccountRepository(connection).list_by_batch(first_result.batch.id)
        jobs = [
            job
            for account in accounts
            for job in UrlJobRepository(connection).list_by_account(account.id)
        ]

        assert len(accounts) == 2
        assert len(jobs) == 5


def test_import_batch_persists_duplicate_urls_idempotently(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_name": "duplicated_urls",
                "defaults": {
                    "download_stories": False,
                    "start_now_date": "2026-06-04",
                },
                "accounts": [
                    {
                        "username": "example_user",
                        "urls": [
                            "https://www.instagram.com/reel/ABC123xyz/",
                            "https://www.instagram.com/reel/ABC123xyz/",
                            "https://www.instagram.com/p/XYZ789abc/",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    init_database(db_path)

    with connect(db_path) as connection:
        first_result = import_batch_json(batch_path, connection)
        second_result = import_batch_json(batch_path, connection)

        account = first_result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        duplicate_rows = connection.execute(
            "SELECT * FROM duplicate_url_jobs ORDER BY id"
        ).fetchall()

        assert first_result.batch.id == second_result.batch.id
        assert len(jobs) == 2
        assert len(duplicate_rows) == 1
        assert duplicate_rows[0]["account_id"] == account.id
        assert duplicate_rows[0]["duplicate_of_url_job_id"] == jobs[0].id
        assert duplicate_rows[0]["url"] == "https://www.instagram.com/reel/ABC123xyz/"
        assert duplicate_rows[0]["occurrence_index"] == 2


def test_import_batch_stores_operational_config_when_settings_are_provided(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_path = _write_batch(tmp_path)
    settings = Settings(
        telegram_api_id=12345,
        telegram_api_hash="secret",
        telethon_session_name="telegram_user_session",
        telegram_download_bot_username="@example_bot",
        telegram_desktop_download_folder=tmp_path / "telegram",
        working_folder=tmp_path / "working",
        reports_folder=tmp_path / "reports",
        sqlite_db_path=db_path,
        max_retries=5,
        retry_base_seconds=90,
        retry_max_seconds=900,
        download_wait_timeout_seconds=300,
        download_stable_seconds=10,
    )
    init_database(db_path)

    with connect(db_path) as connection:
        result = import_batch_json(batch_path, connection, settings=settings)

        first_account = result.accounts[0]
        assert first_account.working_folder == tmp_path / "working" / "example_user"

        config_repo = ConfigRepository(connection)
        max_retries = config_repo.get("max_retries")
        working_folder = config_repo.get("working_folder")
        api_hash = config_repo.get("telegram_api_hash")

        assert max_retries is not None
        assert max_retries.value == "5"
        assert max_retries.value_type == ConfigValueType.INTEGER
        assert working_folder is not None
        assert working_folder.value == str(tmp_path / "working")
        assert working_folder.value_type == ConfigValueType.PATH
        assert api_hash is None


def _write_batch(tmp_path: Path) -> Path:
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_name": "descargas_junio_2026",
                "defaults": {
                    "download_stories": False,
                    "start_now_date": "2026-06-04",
                },
                "accounts": [
                    {
                        "username": "example_user",
                        "download_stories": True,
                        "urls": [
                            "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
                            "https://www.instagram.com/reel/ABC123xyz/",
                        ],
                    },
                    {
                        "username": "another_user",
                        "urls": [
                            "https://www.instagram.com/stories/highlights/17851330941375169/",
                            "https://www.instagram.com/p/XYZ789abc/",
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return batch_path
