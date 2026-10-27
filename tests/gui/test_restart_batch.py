from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batches.restart import restart_batch
from ig_orchestrator.models import AccountStatus, InputBatchStatus, UrlJobStatus


def _draft() -> BatchDraft:
    return BatchDraft(
        batch_name="restart_me",
        default_start_now_date="2026-10-27",
        accounts=[
            AccountDraft(
                username="restart_user",
                urls=[
                    "https://www.instagram.com/reel/R1/",
                    "https://www.instagram.com/reel/R2/",
                ],
                start_now_date="2026-10-27",
            )
        ],
    )


def test_restart_resets_urls_accounts_and_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        result = save_batch_draft(_draft(), connection)
        batch_id = result.batch.id
        account_id = result.accounts[0].id
        jobs = UrlJobRepository(connection).list_by_account(account_id)
        connection.execute(
            "UPDATE url_jobs SET status = 'COMPLETED', retries = 2, "
            "last_error = 'x', last_error_type = 'Y', sent_message_id = 9, "
            "finished_at = datetime('now') WHERE id = ?",
            (jobs[0].id,),
        )
        connection.execute(
            "UPDATE url_jobs SET status = 'FAILED_FINAL', non_retryable = 1 WHERE id = ?",
            (jobs[1].id,),
        )
        connection.execute(
            "INSERT INTO download_files (url_job_id, original_path, media_type, "
            "file_extension, status, created_at, updated_at) "
            "VALUES (?, 'a.mp4', 'VIDEO', '.mp4', 'MOVED_TO_WORKING_FOLDER', "
            "datetime('now'), datetime('now'))",
            (jobs[0].id,),
        )
        connection.execute(
            "UPDATE accounts SET status = 'PARTIAL' WHERE id = ?", (account_id,)
        )
        connection.execute(
            "UPDATE input_batches SET status = 'PARTIAL' WHERE id = ?", (batch_id,)
        )
        connection.commit()

        outcome = restart_batch(connection, batch_id)

        assert (outcome.accounts_reset, outcome.urls_reset) == (1, 2)
        assert outcome.download_records_discarded == 1
        for job in UrlJobRepository(connection).list_by_account(account_id):
            assert job.status is UrlJobStatus.PENDING
            assert job.retries == 0
            assert job.last_error is None and job.last_error_type is None
            assert job.sent_message_id is None and job.finished_at is None
            assert job.non_retryable is False
        assert AccountRepository(connection).get_by_id(account_id).status is AccountStatus.PENDING
        assert BatchRepository(connection).get_by_id(batch_id).status is InputBatchStatus.IMPORTED
        assert connection.execute("SELECT COUNT(*) FROM download_files").fetchone()[0] == 0


def test_restart_rejects_unknown_batch_and_drafts(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        with pytest.raises(ValueError):
            restart_batch(connection, 999)
        result = save_batch_draft(_draft(), connection)
        with pytest.raises(ValueError):
            restart_batch(connection, result.batch.id)


def test_restart_works_on_the_gui_database(tmp_path: Path) -> None:
    from ig_orchestrator.db import DownloadRepository, init_gui_database
    from ig_orchestrator.models import (
        DownloadFile,
        DownloadFileStatus,
        MediaType,
    )

    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        result = save_batch_draft(_draft(), connection)
        batch_id = result.batch.id
        account_id = result.accounts[0].id
        job = UrlJobRepository(connection).list_by_account(account_id)[0]
        DownloadRepository(connection).create(
            DownloadFile(
                url_job_id=job.id,
                original_path=tmp_path / "a.mp4",
                media_type=MediaType.VIDEO,
                file_extension=".mp4",
                status=DownloadFileStatus.DETECTED,
            )
        )
        connection.execute(
            "UPDATE input_batches SET status = 'PARTIAL' WHERE id = ?", (batch_id,)
        )
        connection.commit()

        outcome = restart_batch(connection, batch_id)

        assert outcome.urls_reset == 2 and outcome.download_records_discarded == 1
        assert BatchRepository(connection).get_by_id(batch_id).status is InputBatchStatus.IMPORTED
        stored = DownloadRepository(connection).list_by_url_job(job.id)
        assert stored == []
