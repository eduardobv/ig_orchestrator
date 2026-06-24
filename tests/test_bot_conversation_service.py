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


def test_process_url_job_discards_exact_duplicate_downloaded_files(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(job_repo)
    downloads = tmp_path / "downloads"
    original = downloads / "3705629594894863521.mp4"
    duplicate = downloads / "3705629594894863521_1.mp4"
    downloads.mkdir()
    original.write_bytes(b"same video bytes")
    duplicate.write_bytes(b"same video bytes")
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[_incoming("Download completed successfully")],
        watcher=lambda *_args: [original, duplicate],
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.DOWNLOADED
    assert [file.original_path for file in result.files] == [original]
    assert download_repo.list_by_url_job(job.id) == list(result.files)
    assert original.exists()
    assert not duplicate.exists()


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
    assert [file.original_path.name for file in result.files] == [
        f"telegram_media_{job.id}-20260614_150000.jpg",
        f"telegram_media_{job.id}-20260614_150000_1.jpg",
    ]
    assert all(file.original_path.exists() for file in result.files)


def test_process_photo_post_discards_previews_when_original_documents_arrive(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(
        job_repo,
        url="https://www.instagram.com/p/DZ2161yFvGK/?img_index=1",
        publication_type=PublicationType.POST,
    )
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[
            _incoming_media(
                101,
                document=_document("3924561065093328270.jpg", "image/jpeg"),
            ),
            _incoming_media(102, photo=object()),
            _incoming_media(
                103,
                document=_document("3924561073456629396.jpg", "image/jpeg"),
            ),
            _incoming_media(104, photo=object()),
        ],
        watcher=lambda *_args: [],
        enable_direct_download=True,
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.DOWNLOADED
    assert [file.original_path.name for file in result.files] == [
        "3924561065093328270.jpg",
        "3924561073456629396.jpg",
    ]
    assert download_repo.list_by_url_job(job.id) == list(result.files)
    assert not list((tmp_path / "downloads").glob("telegram_media_*"))
    assert not (tmp_path / "downloads" / "_tmp_telethon_downloads").exists()


def test_process_story_job_keeps_video_document_and_photo_previews(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(
        job_repo,
        url="https://www.instagram.com/stories/iarabroinn/",
        publication_type=PublicationType.STORY,
        source=UrlSource.GENERATED_STORY,
        username="iarabroinn",
    )
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[
            _incoming_media(
                101,
                document=_document("3924073435592992042.mp4", "video/mp4"),
            ),
            _incoming_media(102, photo=object()),
            _incoming_media(103, photo=object()),
            _incoming_media(104, photo=object()),
            _incoming_media(105, photo=object()),
        ],
        watcher=lambda *_args: [],
        enable_direct_download=True,
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.DOWNLOADED
    assert [file.original_path.name for file in result.files] == [
        "3924073435592992042.mp4",
        "iarabroinn-20260614_150000.jpg",
        "iarabroinn-20260614_150000_1.jpg",
        "iarabroinn-20260614_150000_2.jpg",
        "iarabroinn-20260614_150000_3.jpg",
    ]
    assert [file.media_type for file in result.files] == [
        MediaType.VIDEO,
        MediaType.IMAGE,
        MediaType.IMAGE,
        MediaType.IMAGE,
        MediaType.IMAGE,
    ]


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


def test_process_story_not_found_with_dynamic_username_is_failed_final(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    download_repo = DownloadRepository(connection)
    job = _stored_job(
        job_repo,
        url="https://www.instagram.com/stories/superlisha/",
        publication_type=PublicationType.STORY,
        source=UrlSource.GENERATED_STORY,
        username="superlisha",
    )
    service = _service(
        tmp_path,
        job_repo,
        download_repo,
        messages=[_incoming("Stories for superlisha not found")],
        watcher=lambda *_args: [],
    )

    result = asyncio.run(service.process_url_job(job))

    assert result.job.status == UrlJobStatus.FAILED_FINAL
    assert result.job.non_retryable is True
    assert result.job.last_error_type == "STORIES_NOT_FOUND"


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


def _stored_job(
    job_repo: UrlJobRepository,
    *,
    url: str = "https://www.instagram.com/reel/ABC123xyz/",
    publication_type: PublicationType = PublicationType.REEL,
    source: UrlSource = UrlSource.INPUT_URL,
    username: str = "example_user",
) -> UrlJob:
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
            username=username,
            start_now_date=date(2026, 6, 14),
            download_stories=False,
            status=AccountStatus.PENDING,
        )
    )
    return job_repo.create(
        UrlJob(
            account_id=account.id,
            url=url,
            publication_type=publication_type,
            source=source,
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
