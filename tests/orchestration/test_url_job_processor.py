from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    DownloadRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    DownloadFile,
    DownloadFileStatus,
    InputBatch,
    InputBatchStatus,
    MediaType,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration import UrlJobProcessor
from ig_orchestrator.telegram import BotConversationResult


@dataclass
class StoredEntities:
    connection: Connection
    account_repo: AccountRepository
    job_repo: UrlJobRepository
    download_repo: DownloadRepository
    account: Account
    job: UrlJob


class FakeConversationService:
    def __init__(self, result: BotConversationResult) -> None:
        self.result = result
        self.jobs: list[UrlJob] = []

    async def process_url_job(self, job: UrlJob) -> BotConversationResult:
        self.jobs.append(job)
        return self.result


def test_processor_moves_downloaded_files_and_marks_job_completed(
    tmp_path: Path,
) -> None:
    stored = _stored_entities(tmp_path)
    source = tmp_path / "downloads" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    download_file = stored.download_repo.create(_download_file(stored.job.id, source))
    downloaded_job = stored.job_repo.update_status(
        stored.job.id,
        UrlJobStatus.DOWNLOADED,
    )
    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=FakeConversationService(
            BotConversationResult(job=downloaded_job, files=(download_file,))
        ),
    )

    result = asyncio.run(processor.process(stored.job.id))

    destination = tmp_path / "working" / "example_user" / "reels" / "clip.mp4"
    assert result.job.status is UrlJobStatus.COMPLETED
    assert result.files[0].working_path == destination
    assert result.files[0].status is DownloadFileStatus.CLASSIFIED_AS_REEL
    assert destination.read_bytes() == b"video"
    assert stored.download_repo.list_by_url_job(stored.job.id) == list(result.files)


def test_processor_keeps_retry_pending_result_without_moving_files(
    tmp_path: Path,
) -> None:
    stored = _stored_entities(tmp_path)
    retry_job = stored.job_repo.update_error(
        stored.job.id,
        status=UrlJobStatus.RETRY_PENDING,
        last_error="The service is overloaded, please try again later.",
        last_error_type="SERVICE_OVERLOADED",
        non_retryable=False,
    )
    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=FakeConversationService(BotConversationResult(job=retry_job)),
    )

    result = asyncio.run(processor.process(stored.job.id))

    assert result.job.status is UrlJobStatus.RETRY_PENDING
    assert result.job.last_error_type == "SERVICE_OVERLOADED"
    assert result.files == ()


def test_processor_reclassifies_reel_with_only_images_as_post(
    tmp_path: Path,
) -> None:
    stored = _stored_entities(tmp_path)
    source = tmp_path / "downloads" / "photo.jpg"
    source.parent.mkdir()
    source.write_bytes(b"image")
    download_file = stored.download_repo.create(
        _download_file(stored.job.id, source, media_type=MediaType.IMAGE)
    )
    downloaded_job = stored.job_repo.update_status(
        stored.job.id,
        UrlJobStatus.DOWNLOADED,
    )
    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=FakeConversationService(
            BotConversationResult(job=downloaded_job, files=(download_file,))
        ),
    )

    result = asyncio.run(processor.process(stored.job.id))

    stored_job = stored.job_repo.get_by_id(stored.job.id)
    assert result.job.status is UrlJobStatus.COMPLETED
    assert stored_job is not None
    assert stored_job.publication_type is PublicationType.POST
    assert result.files[0].working_path == (
        tmp_path / "working" / "example_user" / "photo.jpg"
    )
    assert result.files[0].status is DownloadFileStatus.CLASSIFIED_AS_POST


def test_processor_marks_move_failure_as_retry_pending(tmp_path: Path) -> None:
    stored = _stored_entities(tmp_path)
    missing = tmp_path / "downloads" / "missing.mp4"
    download_file = stored.download_repo.create(_download_file(stored.job.id, missing))
    downloaded_job = stored.job_repo.update_status(
        stored.job.id,
        UrlJobStatus.DOWNLOADED,
    )
    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=FakeConversationService(
            BotConversationResult(job=downloaded_job, files=(download_file,))
        ),
    )

    result = asyncio.run(processor.process(stored.job.id))

    assert result.job.status is UrlJobStatus.RETRY_PENDING
    assert result.job.last_error_type == "MOVE_FILES_FAILED"


def _stored_entities(tmp_path: Path) -> StoredEntities:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    connection = connect(db_path)
    batch = BatchRepository(connection).create(
        InputBatch(
            batch_name="batch",
            schema_version="1.0",
            status=InputBatchStatus.IMPORTED,
        )
    )
    account_repo = AccountRepository(connection)
    account = account_repo.create(
        Account(
            batch_id=batch.id,
            username="example_user",
            start_now_date=date(2026, 6, 14),
            download_stories=False,
            working_folder=tmp_path / "working" / "example_user",
            status=AccountStatus.PENDING,
        )
    )
    job_repo = UrlJobRepository(connection)
    job = job_repo.create(
        UrlJob(
            account_id=account.id,
            url="https://www.instagram.com/reel/ABC123xyz/",
            publication_type=PublicationType.REEL,
            source=UrlSource.INPUT_URL,
            status=UrlJobStatus.PENDING,
            max_retries=5,
        )
    )
    return StoredEntities(
        connection=connection,
        account_repo=account_repo,
        job_repo=job_repo,
        download_repo=DownloadRepository(connection),
        account=account,
        job=job,
    )


def _download_file(
    job_id: int,
    path: Path,
    *,
    media_type: MediaType = MediaType.VIDEO,
) -> DownloadFile:
    return DownloadFile(
        url_job_id=job_id,
        original_path=path,
        media_type=media_type,
        file_extension=path.suffix,
        file_size=path.stat().st_size if path.exists() else None,
        status=DownloadFileStatus.DETECTED,
    )
