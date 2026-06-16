from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    DownloadRepository,
    UrlJobRepository,
    init_database,
)
from ig_orchestrator.db.connection import connect
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    DownloadFileStatus,
    InputBatch,
    InputBatchStatus,
    MediaType,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.telegram import (
    BotConversationConfig,
    BotConversationService,
)


@dataclass
class FakeMessage:
    id: int
    text: str
    date: datetime
    out: bool = False
    media: object | None = None
    document: object | None = None
    photo: object | None = None


class FakeTelegramClient:
    def __init__(
        self,
        messages: list[FakeMessage] | None = None,
        *,
        enable_direct_download: bool = False,
    ) -> None:
        self.messages = messages or []
        self.sent_urls: list[str] = []
        self.enable_direct_download = enable_direct_download

    async def send_message_to_bot(self, text: str) -> FakeMessage:
        self.sent_urls.append(text)
        return FakeMessage(
            id=99,
            text=text,
            date=datetime(2026, 6, 14, 12, tzinfo=timezone.utc),
            out=True,
        )

    async def get_bot_messages_after(
        self,
        timestamp: datetime,
        *,
        limit: int = 100,
    ) -> list[FakeMessage]:
        return self.messages[-limit:]

    async def download_message_media(self, message: FakeMessage, destination: str) -> str | None:
        if not self.enable_direct_download:
            raise RuntimeError("direct download disabled")
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"media-{message.id}".encode("ascii"))
        return str(path)


def test_process_url_job_marks_downloaded_and_stores_detected_files(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    downloaded_file = tmp_path / "downloads" / "clip.mp4"
    downloaded_file.parent.mkdir()
    downloaded_file.write_bytes(b"video")
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[_incoming("Download completed successfully")],
        watcher=lambda *_args: [downloaded_file],
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.DOWNLOADED
    assert result.job.sent_message_id == 99
    assert len(result.files) == 1
    assert result.files[0].original_path == downloaded_file
    assert result.files[0].media_type == MediaType.VIDEO
    assert result.files[0].status == DownloadFileStatus.DETECTED
    assert download_repo.list_by_url_job(job.id) == list(result.files)


def test_process_url_job_downloads_document_media_without_desktop_watcher(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    document_message = _incoming_media(
        101,
        document=_document("3918738646186472213.jpg", "image/jpeg"),
    )
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[document_message, _incoming("caption")],
        watcher=lambda *_args: [],
        enable_direct_download=True,
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.DOWNLOADED
    assert len(result.files) == 1
    assert result.files[0].original_path.name == "3918738646186472213.jpg"
    assert result.files[0].original_path.exists()
    assert download_repo.list_by_url_job(job.id) == list(result.files)


def test_process_url_job_promotes_preview_media_when_no_document_arrives(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[_incoming_media(101, photo=object()), _incoming_media(102, photo=object())],
        watcher=lambda *_args: [],
        enable_direct_download=True,
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.DOWNLOADED
    assert [file.original_path.name for file in result.files] == ["101.jpg", "102.jpg"]
    assert all(file.original_path.exists() for file in result.files)


def test_process_url_job_marks_non_retryable_error_as_failed_final(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[_incoming("We're sorry, we couldn't find that.")],
        watcher=lambda *_args: [],
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.FAILED_FINAL
    assert result.job.non_retryable is True
    assert result.job.last_error == "We're sorry, we couldn't find that."
    assert result.job.last_error_type == "NOT_FOUND"
    assert download_repo.list_by_url_job(job.id) == []


def test_process_url_job_marks_retryable_error_as_retry_pending(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[_incoming("The service is overloaded, please try again later.")],
        watcher=lambda *_args: [],
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.RETRY_PENDING
    assert result.job.non_retryable is False
    assert result.job.last_error_type == "SERVICE_OVERLOADED"
    assert download_repo.list_by_url_job(job.id) == []


def test_process_url_job_marks_missing_files_as_retry_pending(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[],
        watcher=lambda *_args: [],
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.RETRY_PENDING
    assert result.job.last_error_type == "NO_FILES_DETECTED"
    assert download_repo.list_by_url_job(job.id) == []


def _connection(tmp_path: Path) -> Connection:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    return connect(db_path)


def _stored_job(job_repo: UrlJobRepository) -> UrlJob:
    batch = BatchRepository(job_repo.connection).create(
        InputBatch(
            batch_name="batch",
            schema_version="1.0",
            status=InputBatchStatus.IMPORTED,
        )
    )
    account = AccountRepository(job_repo.connection).create(
        Account(
            batch_id=batch.id,
            username="example_user",
            start_now_date=date(2026, 6, 14),
            download_stories=False,
            status=AccountStatus.PENDING,
        )
    )
    return job_repo.create(
        UrlJob(
            account_id=account.id,
            url="https://www.instagram.com/reel/ABC123xyz/",
            publication_type=PublicationType.REEL,
            source=UrlSource.INPUT_URL,
            status=UrlJobStatus.PENDING,
            max_retries=5,
        )
    )


def _service(
    tmp_path: Path,
    job_repo: UrlJobRepository,
    download_repo: DownloadRepository,
    *,
    messages: list[FakeMessage],
    watcher: object,
    enable_direct_download: bool = False,
) -> BotConversationService:
    download_folder = tmp_path / "downloads"
    download_folder.mkdir(exist_ok=True)
    return BotConversationService(
        telegram_client=FakeTelegramClient(
            messages,
            enable_direct_download=enable_direct_download,
        ),
        url_job_repository=job_repo,
        download_repository=download_repo,
        config=BotConversationConfig(
            download_folder=download_folder,
            download_wait_timeout_seconds=0,
            download_stable_seconds=0,
            response_wait_timeout_seconds=0,
        ),
        watcher=watcher,  # type: ignore[arg-type]
    )


def _incoming(text: str) -> FakeMessage:
    return FakeMessage(
        id=100,
        text=text,
        date=datetime(2026, 6, 14, 13, tzinfo=timezone.utc),
    )


def _incoming_media(
    message_id: int,
    *,
    document: object | None = None,
    photo: object | None = None,
) -> FakeMessage:
    return FakeMessage(
        id=message_id,
        text="",
        date=datetime(2026, 6, 14, 13, tzinfo=timezone.utc),
        media=object(),
        document=document,
        photo=photo,
    )


def _document(file_name: str, mime_type: str) -> object:
    return type(
        "FakeDocument",
        (),
        {
            "mime_type": mime_type,
            "attributes": [
                type("FakeDocumentAttributeFilename", (), {"file_name": file_name})()
            ],
        },
    )()
