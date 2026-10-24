from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ig_orchestrator.db import DownloadRepository, UrlJobRepository
from ig_orchestrator.filesystem.file_classifier import classify_file_media_type
from ig_orchestrator.filesystem.file_watcher import watch_downloaded_files
from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.models import (
    DownloadFile,
    DownloadFileStatus,
    UrlJob,
    UrlJobStatus,
)
from ig_orchestrator.telegram.bot_response_parser import (
    BotResponse,
    BotResponseStatus,
    parse_bot_response,
)
from ig_orchestrator.telemetry.observer import NullObserver, RunObserver
from ig_orchestrator.telemetry.trace import (
    EXIT_DEADLINE_FIRST,
    EXIT_DEADLINE_TOTAL,
    EXIT_ERROR_TEXT,
    EXIT_LARGE_FILE_LINK,
    EXIT_SEND_FAILED,
    EXIT_STABLE,
    TEXT_CLASS_DESCRIPTION,
    TEXT_CLASS_ERROR,
    TEXT_CLASS_LARGE_FILE_LINK,
    AttemptTrace,
)
from ig_orchestrator.telegram.large_file import (
    FILE_TOO_LARGE_DOWNLOAD_FAILED,
    LargeFileConfig,
    LargeFileDownloadError,
    download_large_file,
    media_id_from_url,
)
from ig_orchestrator.telegram.telegram_client import cryptg_available


logger = get_logger()


class TelegramBotClient(Protocol):
    async def send_message_to_bot(self, text: str) -> Any:
        """Send text to the configured bot and return the sent message."""

    async def get_bot_messages_after(
        self,
        timestamp: datetime,
        *,
        limit: int = 100,
    ) -> list[Any]:
        """Return conversation messages after timestamp."""

    async def download_message_media(self, message: Any, destination: str) -> str | None:
        """Download media from a bot message to destination."""


Watcher = Callable[[Path, datetime, float, float], list[Path]]
LargeFileDownloader = Callable[[str, Path, LargeFileConfig], Awaitable[Path]]


@dataclass(frozen=True, slots=True)
class BotConversationConfig:
    download_folder: Path
    download_wait_timeout_seconds: float
    download_stable_seconds: float
    response_wait_timeout_seconds: float = 30.0
    response_poll_interval_seconds: float = 0.5
    response_message_limit: int = 50
    response_fallback_poll_seconds: float = 1.5
    parallel_downloads: int = 4
    watcher_fallback_enabled: bool = True
    large_file: LargeFileConfig = LargeFileConfig()
    use_events: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.download_folder, Path):
            raise ValueError("download_folder must be a pathlib.Path")
        _validate_non_negative(
            "download_wait_timeout_seconds", self.download_wait_timeout_seconds
        )
        _validate_non_negative("download_stable_seconds", self.download_stable_seconds)
        _validate_non_negative(
            "response_wait_timeout_seconds", self.response_wait_timeout_seconds
        )
        if self.response_poll_interval_seconds <= 0:
            raise ValueError("response_poll_interval_seconds must be positive")
        if self.parallel_downloads <= 0:
            raise ValueError("parallel_downloads must be positive")
        if self.response_fallback_poll_seconds <= 0:
            raise ValueError("response_fallback_poll_seconds must be positive")
        if self.response_message_limit <= 0:
            raise ValueError("response_message_limit must be positive")


@dataclass(frozen=True, slots=True)
class BotConversationResult:
    job: UrlJob
    files: tuple[DownloadFile, ...] = ()
    bot_message: str | None = None
    trace: AttemptTrace | None = None


@dataclass(slots=True)
class _MediaDownload:
    message_id: int
    message_date: datetime | None
    path: Path | None
    provisional_path: Path | None
    original_file_name: str | None
    error: str | None = None


class BotConversationService:
    """Process one URL against the Telegram download bot.

    The service owns an async lock so a single instance never sends two URLs to
    the bot at the same time, matching the conservative v1.0.1 workflow.
    """

    def __init__(
        self,
        *,
        telegram_client: TelegramBotClient,
        url_job_repository: UrlJobRepository,
        download_repository: DownloadRepository,
        config: BotConversationConfig,
        watcher: Watcher = watch_downloaded_files,
        large_file_downloader: LargeFileDownloader = download_large_file,
        clock: Callable[[], float] = time.monotonic,
        observer: RunObserver | None = None,
    ) -> None:
        self._telegram_client = telegram_client
        self._url_job_repository = url_job_repository
        self._download_repository = download_repository
        self._config = config
        self._watcher = watcher
        self._large_file_downloader = large_file_downloader
        self._clock = clock
        self._observer: RunObserver = observer or NullObserver()
        self._trace: AttemptTrace | None = None
        self._lock = asyncio.Lock()
        self._subscription: Any | None = None
        self._download_tasks: list[asyncio.Task[_MediaDownload]] = []

    async def process_url_job(self, job: UrlJob) -> BotConversationResult:
        if job.id is None:
            raise ValueError("UrlJob.id is required to process a conversation")

        async with self._lock:
            # Subscribe before sending so no bot reply can be missed.
            self._subscription = self._open_subscription()
            trace = AttemptTrace.start(
                url_job_id=job.id,
                account_id=job.account_id,
                batch_run_id=job.run_id,
                attempt_no=job.retries + 1,
                publication_type=job.publication_type.value,
                clock=self._clock,
            )
            trace.aes_backend = "cryptg" if cryptg_available() else "pyaes"
            trace.settings = {
                "events": self._subscription is not None,
                "parallel_downloads": self._config.parallel_downloads,
                "watcher_fallback": self._config.watcher_fallback_enabled,
                "fallback_poll_s": self._config.response_fallback_poll_seconds,
            }
            self._trace = trace
            self._observer.begin_attempt(trace)
            try:
                result = await self._process_url_job_locked(job)
                trace.files_count = len(result.files)
                return dataclasses.replace(result, trace=trace)
            finally:
                self._trace = None
                if self._subscription is not None:
                    self._subscription.close()
                self._subscription = None
                for task in self._download_tasks:
                    task.cancel()
                self._download_tasks = []

    def _open_subscription(self) -> Any | None:
        subscribe = getattr(self._telegram_client, "subscribe_bot_messages", None)
        if not self._config.use_events or not callable(subscribe):
            return None
        try:
            return subscribe()
        except Exception as exc:
            logger.warning("Event subscription failed, falling back to polling: {}", exc)
            return None

    async def _process_url_job_locked(self, job: UrlJob) -> BotConversationResult:
        job_id = _require_job_id(job)
        started_at = _utc_now()
        current_job = self._url_job_repository.update_status(
            job_id,
            UrlJobStatus.SENT_TO_BOT,
            started_at=started_at,
        )
        logger.info(
            "Sending message to Telegram bot: job_id={} url={}",
            job_id,
            job.url,
        )

        try:
            sent_message = await self._telegram_client.send_message_to_bot(job.url)
        except Exception as exc:
            logger.exception(
                "Telegram send failed: job_id={} error={}",
                job_id,
                exc,
            )
            failed_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error=str(exc),
                last_error_type="SEND_MESSAGE_FAILED",
                non_retryable=False,
            )
            if self._trace is not None:
                self._trace.end_wait(EXIT_SEND_FAILED)
            return BotConversationResult(job=failed_job)

        if self._trace is not None:
            self._trace.mark_sent()
        sent_message_id = _message_id(sent_message)
        if sent_message_id is not None:
            current_job = self._url_job_repository.update_sent_message_id(
                job_id,
                sent_message_id,
            )
        logger.info(
            "Message sent to Telegram bot: job_id={} sent_message_id={}",
            job_id,
            sent_message_id or "-",
        )

        current_job = self._url_job_repository.update_status(
            job_id,
            UrlJobStatus.WAITING_DOWNLOAD,
        )

        bot_message, direct_paths, bot_responded = (
            await self._wait_for_bot_response_and_downloads(
                job_id=job_id,
                media_filename_prefix=_media_filename_prefix(job),
                since=started_at,
                sent_message_id=sent_message_id,
            )
        )
        logger.info(
            "Bot response received: job_id={} response={}",
            job_id,
            bot_message or "<no text response>",
        )
        if not bot_responded and not direct_paths:
            logger.warning("Telegram bot did not respond before timeout: job_id={}", job_id)
            retry_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error="Telegram bot returned no response before timeout.",
                last_error_type="NO_BOT_RESPONSE",
                non_retryable=False,
            )
            return BotConversationResult(job=retry_job)

        response = parse_bot_response(bot_message)

        if response.status is BotResponseStatus.LARGE_FILE_LINK and not direct_paths:
            return await self._download_large_file_result(job, response, bot_message)

        if (
            response.status is BotResponseStatus.NON_RETRYABLE_ERROR
            and not direct_paths
        ):
            logger.warning(
                "Bot returned non-retryable error: job_id={} error_type={} error={}",
                job_id,
                _error_type_value(response.last_error_type),
                response.last_error or "",
            )
            failed_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.FAILED_FINAL,
                last_error=response.last_error or "",
                last_error_type=_error_type_value(response.last_error_type),
                non_retryable=True,
            )
            return BotConversationResult(job=failed_job, bot_message=bot_message)

        if response.status is BotResponseStatus.RETRYABLE_ERROR and not direct_paths:
            logger.warning(
                "Bot returned retryable error: job_id={} error_type={} error={}",
                job_id,
                _error_type_value(response.last_error_type),
                response.last_error or "",
            )
            retry_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error=response.last_error or "",
                last_error_type=_error_type_value(response.last_error_type),
                non_retryable=False,
            )
            return BotConversationResult(job=retry_job, bot_message=bot_message)

        detected_paths = direct_paths
        if not detected_paths and self._config.watcher_fallback_enabled:
            detected_paths = self._watcher(
                self._config.download_folder,
                started_at,
                self._config.download_wait_timeout_seconds,
                self._config.download_stable_seconds,
            )
        logger.info(
            "Downloaded files detected: job_id={} count={} files={}",
            job_id,
            len(detected_paths),
            [str(path) for path in detected_paths],
        )
        detected_paths = _remove_duplicate_download_paths(detected_paths)

        if not detected_paths:
            logger.warning("No downloaded files detected: job_id={}", job_id)
            failed_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error="No downloaded files detected after sending URL to bot.",
                last_error_type="NO_FILES_DETECTED",
                non_retryable=False,
            )
            return BotConversationResult(job=failed_job, bot_message=bot_message)

        files = tuple(self._store_detected_file(job_id, path) for path in detected_paths)
        downloaded_job = self._url_job_repository.update_status(
            job_id,
            UrlJobStatus.DOWNLOADED,
            finished_at=_utc_now(),
        )
        logger.info(
            "URL job downloaded: job_id={} stored_files={}",
            job_id,
            len(files),
        )
        return BotConversationResult(
            job=downloaded_job,
            files=files,
            bot_message=bot_message,
        )

    async def _wait_for_bot_response_and_downloads(
        self,
        *,
        job_id: int,
        media_filename_prefix: str,
        since: datetime,
        sent_message_id: int | None,
    ) -> tuple[str | None, list[Path], bool]:
        deadline = asyncio.get_running_loop().time() + max(
            self._config.response_wait_timeout_seconds,
            self._config.download_wait_timeout_seconds,
        )
        seen_message_ids: set[int] = set()
        bot_texts: list[str] = []
        seen_files: set[tuple[str, int | None]] = set()
        previews: list[Any] = []
        semaphore = asyncio.Semaphore(self._config.parallel_downloads)
        self._download_tasks = []
        last_media_at: float | None = None
        bot_responded = False

        subscription = self._subscription
        last_fallback_poll = asyncio.get_running_loop().time()
        while True:
            if subscription is None:
                messages = await self._telegram_client.get_bot_messages_after(
                    since,
                    limit=self._config.response_message_limit,
                )
            else:
                messages, polled = await self._next_event_messages(
                    subscription,
                    since=since,
                    deadline=deadline,
                    last_fallback_poll=last_fallback_poll,
                )
                if polled:
                    last_fallback_poll = asyncio.get_running_loop().time()
            for message in messages:
                message_id = _message_id(message)
                if message_id is not None:
                    if message_id in seen_message_ids:
                        continue
                    seen_message_ids.add(message_id)
                if _is_outgoing_message(message):
                    continue
                if sent_message_id is not None and message_id == sent_message_id:
                    continue

                bot_responded = True

                text = _message_text(message)
                has_text = text is not None and bool(text.strip())
                parsed = parse_bot_response(text) if has_text else None
                self._record_message(message, text if has_text else None, parsed)
                if has_text and parsed is not None:
                    bot_texts.append(text.strip())
                    if parsed.status is not BotResponseStatus.OK:
                        self._end_wait(
                            EXIT_LARGE_FILE_LINK
                            if parsed.status is BotResponseStatus.LARGE_FILE_LINK
                            else EXIT_ERROR_TEXT
                        )
                        return (
                            _join_bot_texts(bot_texts),
                            await self._finish_downloads(
                                job_id, previews, media_filename_prefix
                            ),
                            bot_responded,
                        )

                if _message_has_media(message) and _can_download_media(
                    self._telegram_client
                ):
                    last_media_at = asyncio.get_running_loop().time()
                    file_name = _original_file_name(message)
                    if file_name is None:
                        # Unnamed media are previews; downloaded only if needed.
                        previews.append(message)
                        continue
                    file_key = (file_name.casefold(), _document_size(message))
                    if file_key in seen_files:
                        if self._trace is not None:
                            self._trace.duplicates_skipped += 1
                        logger.info(
                            "Duplicate bot attachment skipped: job_id={} file={}",
                            job_id,
                            file_name,
                        )
                        continue
                    seen_files.add(file_key)
                    self._download_tasks.append(
                        asyncio.create_task(
                            self._download_with_limit(semaphore, job_id, message)
                        )
                    )

            now = asyncio.get_running_loop().time()
            if last_media_at is not None:
                quiet_seconds = now - last_media_at
                if quiet_seconds >= self._config.download_stable_seconds:
                    self._end_wait(EXIT_STABLE)
                    return (
                        _join_bot_texts(bot_texts),
                        await self._finish_downloads(
                            job_id, previews, media_filename_prefix
                        ),
                        bot_responded,
                    )

            if now >= deadline:
                self._end_wait(
                    EXIT_DEADLINE_TOTAL if bot_responded else EXIT_DEADLINE_FIRST
                )
                return (
                    _join_bot_texts(bot_texts),
                    await self._finish_downloads(job_id, previews, media_filename_prefix),
                    bot_responded,
                )

            if subscription is None:
                await asyncio.sleep(
                    min(self._config.response_poll_interval_seconds, deadline - now)
                )

    async def _download_large_file_result(
        self,
        job: UrlJob,
        response: BotResponse,
        bot_message: str | None,
    ) -> BotConversationResult:
        """Download a file the bot only offered as a link (> 50 MB)."""

        job_id = _require_job_id(job)
        media_id = media_id_from_url(job.url)
        try:
            if not self._config.large_file.enabled:
                raise LargeFileDownloadError("Large file download is disabled.")
            if not response.download_url:
                raise LargeFileDownloadError("Bot message has no download link.")
            if media_id is None:
                raise LargeFileDownloadError(
                    "Large file links are only supported for posts and reels."
                )
            target = _unique_path(self._config.download_folder, f"{media_id}.mp4")
            logger.info(
                "Downloading large file from bot link: job_id={} media_id={}",
                job_id,
                media_id,
            )
            large_started = self._clock()
            downloaded = await self._large_file_downloader(
                response.download_url, target, self._config.large_file
            )
            if self._trace is not None:
                self._trace.t_download_ms = int((self._clock() - large_started) * 1000)
                self._trace.bytes_downloaded += (
                    downloaded.stat().st_size if downloaded.exists() else 0
                )
        except LargeFileDownloadError as exc:
            logger.warning(
                "Large file download failed: job_id={} error={}", job_id, exc
            )
            failed_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error=f"Large file download failed: {exc}",
                last_error_type=FILE_TOO_LARGE_DOWNLOAD_FAILED,
                non_retryable=False,
            )
            return BotConversationResult(job=failed_job, bot_message=bot_message)

        stored = self._store_detected_file(job_id, downloaded)
        downloaded_job = self._url_job_repository.update_status(
            job_id,
            UrlJobStatus.DOWNLOADED,
            finished_at=_utc_now(),
        )
        return BotConversationResult(
            job=downloaded_job, files=(stored,), bot_message=bot_message
        )

    async def _download_with_limit(
        self,
        semaphore: asyncio.Semaphore,
        job_id: int,
        message: Any,
    ) -> _MediaDownload:
        async with semaphore:
            return await self._download_bot_message_media(job_id, message)

    def _end_wait(self, exit_reason: str) -> None:
        if self._trace is not None:
            self._trace.end_wait(exit_reason)

    def _record_message(
        self,
        message: Any,
        text: str | None,
        parsed: BotResponse | None,
    ) -> None:
        trace = self._trace
        if trace is None:
            return
        document = getattr(message, "document", None)
        has_name = _original_file_name(message) is not None
        if document is not None:
            kind = "DOCUMENT_FILE" if has_name else "VIDEO_NONAME"
        elif getattr(message, "photo", None):
            kind = "PHOTO"
        else:
            kind = "TEXT"
        text_class: str | None = None
        if parsed is not None:
            if parsed.status is BotResponseStatus.OK:
                text_class = TEXT_CLASS_DESCRIPTION
            elif parsed.status is BotResponseStatus.LARGE_FILE_LINK:
                text_class = TEXT_CLASS_LARGE_FILE_LINK
            else:
                text_class = TEXT_CLASS_ERROR
        trace.on_message(
            message_id=_message_id(message),
            grouped_id=_int_or_none(getattr(message, "grouped_id", None)),
            kind=kind,
            mime=getattr(document, "mime_type", None),
            has_filename=has_name,
            size_bytes=_document_size(message),
            text_class=text_class,
            text_len=len(text) if text else None,
        )

    async def _finish_downloads(
        self,
        job_id: int,
        previews: list[Any],
        media_filename_prefix: str,
    ) -> list[Path]:
        """Await named downloads; fetch unnamed previews only when needed."""

        started = self._clock()
        try:
            return await self._finish_downloads_inner(
                job_id, previews, media_filename_prefix
            )
        finally:
            if self._trace is not None:
                self._trace.t_download_ms = int((self._clock() - started) * 1000)

    async def _finish_downloads_inner(
        self,
        job_id: int,
        previews: list[Any],
        media_filename_prefix: str,
    ) -> list[Path]:
        downloads = list(await asyncio.gather(*self._download_tasks))
        self._download_tasks = []
        named_paths = [
            download.path
            for download in downloads
            if download.path is not None and download.path.exists()
        ]
        only_images = bool(named_paths) and all(_is_image_path(p) for p in named_paths)
        if previews and only_images:
            logger.info(
                "Telegram image previews not downloaded: job_id={} originals={} previews={}",
                job_id,
                len(named_paths),
                len(previews),
            )
        elif previews:
            semaphore = asyncio.Semaphore(self._config.parallel_downloads)
            downloads.extend(
                await asyncio.gather(
                    *(
                        self._download_with_limit(semaphore, job_id, message)
                        for message in previews
                    )
                )
            )
        return _finalize_media_downloads(
            self._config.download_folder,
            downloads,
            media_filename_prefix,
        )

    async def _next_event_messages(
        self,
        subscription: Any,
        *,
        since: datetime,
        deadline: float,
        last_fallback_poll: float,
    ) -> tuple[list[Any], bool]:
        """Wait for event messages; returns (messages, backup_poll_ran)."""

        loop = asyncio.get_running_loop()
        fallback_due = last_fallback_poll + self._config.response_fallback_poll_seconds
        wait = min(max(min(fallback_due, deadline) - loop.time(), 0.0), 0.5)
        first = await subscription.get(wait)
        if first is not None:
            messages = [first]
            while (extra := subscription.get_nowait()) is not None:
                messages.append(extra)
            return messages, False
        if loop.time() >= fallback_due:
            # Backup poll recovers messages lost to a reconnection.
            polled = await self._telegram_client.get_bot_messages_after(
                since,
                limit=self._config.response_message_limit,
            )
            return list(polled), True
        return [], False

    async def _download_bot_message_media(
        self,
        job_id: int,
        message: Any,
    ) -> _MediaDownload:
        message_id = _message_id(message) or 0
        message_date = _message_date(message)
        original_file_name = _original_file_name(message)
        extension = _message_file_extension(message, original_file_name)
        temp_folder = self._config.download_folder / "_tmp_telethon_downloads"
        provisional_folder = temp_folder / "_provisional_no_original_name"
        temp_folder.mkdir(parents=True, exist_ok=True)
        provisional_folder.mkdir(parents=True, exist_ok=True)

        target_folder = temp_folder if original_file_name else provisional_folder
        temp_path = target_folder / f"job_{job_id}_msg_{message_id}{extension}"
        temp_path.unlink(missing_ok=True)

        download_started = self._clock()
        try:
            downloaded_path_text = await self._telegram_client.download_message_media(
                message,
                str(temp_path),
            )
            if not downloaded_path_text:
                raise RuntimeError("Telethon returned empty downloaded path.")
            downloaded_path = Path(downloaded_path_text)
            if not downloaded_path.exists():
                raise RuntimeError(f"Downloaded file does not exist: {downloaded_path}")
            if self._trace is not None:
                self._trace.on_download(
                    message_id,
                    int((self._clock() - download_started) * 1000),
                    downloaded_path.stat().st_size,
                )

            if not original_file_name:
                return _MediaDownload(
                    message_id=message_id,
                    message_date=message_date,
                    path=None,
                    provisional_path=downloaded_path,
                    original_file_name=None,
                )

            final_path = _unique_path(
                self._config.download_folder,
                original_file_name,
            )
            shutil.move(str(downloaded_path), str(final_path))
            return _MediaDownload(
                message_id=message_id,
                message_date=message_date,
                path=final_path,
                provisional_path=None,
                original_file_name=original_file_name,
            )
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            logger.warning(
                "Direct Telegram media download failed: job_id={} message_id={} error={}",
                job_id,
                message_id or "-",
                exc,
            )
            return _MediaDownload(
                message_id=message_id,
                message_date=message_date,
                path=None,
                provisional_path=None,
                original_file_name=original_file_name,
                error=str(exc),
            )

    def _store_detected_file(self, job_id: int, path: Path) -> DownloadFile:
        media_type = classify_file_media_type(path)
        file_size = path.stat().st_size if path.exists() else None
        stored_file = self._download_repository.create(
            DownloadFile(
                url_job_id=job_id,
                original_path=path,
                media_type=media_type,
                file_extension=path.suffix.lower(),
                file_size=file_size,
                status=DownloadFileStatus.DETECTED,
            )
        )
        logger.info(
            "Detected file stored: job_id={} file_id={} path={} media_type={} size={}",
            job_id,
            stored_file.id,
            stored_file.original_path,
            stored_file.media_type.value,
            stored_file.file_size,
        )
        return stored_file


def _require_job_id(job: UrlJob) -> int:
    if job.id is None:
        raise ValueError("UrlJob.id is required")
    return job.id


def _message_id(message: Any) -> int | None:
    value = getattr(message, "id", None)
    return value if isinstance(value, int) and value > 0 else None


def _message_date(message: Any) -> datetime | None:
    value = getattr(message, "date", None)
    return value if isinstance(value, datetime) else None


def _message_text(message: Any) -> str | None:
    for attribute in ("text", "message", "raw_text"):
        value = getattr(message, attribute, None)
        if isinstance(value, str):
            return value
    return None


def _join_bot_texts(texts: list[str]) -> str | None:
    if not texts:
        return None
    return "\n\n".join(texts)


def _message_has_media(message: Any) -> bool:
    return bool(
        getattr(message, "media", None)
        or getattr(message, "document", None)
        or getattr(message, "photo", None)
    )


def _can_download_media(client: TelegramBotClient) -> bool:
    return callable(getattr(client, "download_message_media", None))


def _original_file_name(message: Any) -> str | None:
    document = getattr(message, "document", None)
    for attribute in getattr(document, "attributes", []) or []:
        file_name = getattr(attribute, "file_name", None)
        if isinstance(file_name, str) and file_name.strip():
            return _sanitize_windows_filename(file_name)
    return None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _document_size(message: Any) -> int | None:
    size = getattr(getattr(message, "document", None), "size", None)
    return size if isinstance(size, int) else None


def _message_file_extension(message: Any, original_file_name: str | None) -> str:
    if original_file_name:
        extension = Path(original_file_name).suffix.lower()
        if extension:
            return extension

    document = getattr(message, "document", None)
    mime_type = (getattr(document, "mime_type", "") or "").lower()
    if mime_type == "video/mp4":
        return ".mp4"
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/png":
        return ".png"
    if mime_type == "image/webp":
        return ".webp"
    if getattr(message, "photo", None):
        return ".jpg"
    return ".bin"


def _finalize_media_downloads(
    download_folder: Path,
    downloads: list[_MediaDownload],
    media_filename_prefix: str,
) -> list[Path]:
    final_paths = [
        download.path
        for download in downloads
        if download.path is not None and download.path.exists()
    ]
    provisional_paths = [
        download
        for download in downloads
        if download.provisional_path is not None and download.provisional_path.exists()
    ]

    if final_paths and all(_is_image_path(path) for path in final_paths):
        for download in provisional_paths:
            if download.provisional_path is None:
                continue
            download.provisional_path.unlink(missing_ok=True)
            download.provisional_path = None
        if provisional_paths:
            logger.info(
                "Telegram image previews discarded because original image documents exist: "
                "originals={} previews={}",
                len(final_paths),
                len(provisional_paths),
            )
        _cleanup_empty_temp_folders(download_folder)
        return final_paths

    promoted_paths: list[Path] = []
    for download in provisional_paths:
        if download.provisional_path is None:
            continue
        suffix = download.provisional_path.suffix or ".bin"
        timestamp = _media_timestamp(download.message_date)
        final_path = _unique_path(
            download_folder,
            f"{media_filename_prefix}-{timestamp}{suffix}",
        )
        shutil.move(str(download.provisional_path), str(final_path))
        download.path = final_path
        download.provisional_path = None
        promoted_paths.append(final_path)

    _cleanup_empty_temp_folders(download_folder)
    return [*final_paths, *promoted_paths]


def _is_image_path(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}


def _media_filename_prefix(job: UrlJob) -> str:
    story_match = re.search(
        r"/stories/([^/?#]+)/?",
        job.url,
        flags=re.IGNORECASE,
    )
    if story_match and story_match.group(1).casefold() != "highlights":
        return _sanitize_windows_filename(story_match.group(1))
    return f"telegram_media_{_require_job_id(job)}"


def _media_timestamp(message_date: datetime | None) -> str:
    value = message_date or _utc_now()
    if value.tzinfo is not None:
        value = value.astimezone()
    return value.strftime("%Y%m%d_%H%M%S")


def _remove_duplicate_download_paths(paths: list[Path]) -> list[Path]:
    kept: list[Path] = []
    groups: dict[tuple[str, str, int | None, str | None], Path] = {}

    for path in paths:
        key = _duplicate_path_key(path)
        if key is None:
            kept.append(path)
            continue

        existing = groups.get(key)
        if existing is None:
            groups[key] = path
            kept.append(path)
            continue

        winner, duplicate = _preferred_duplicate_path(existing, path)
        if winner != existing:
            groups[key] = winner
            kept[kept.index(existing)] = winner
        _delete_duplicate_path(duplicate)
        logger.warning(
            "Duplicate downloaded file ignored: kept={} removed={}",
            winner,
            duplicate,
        )

    return kept


def _duplicate_path_key(path: Path) -> tuple[str, str, int | None, str | None] | None:
    if not path.exists() or not path.is_file():
        return None
    return (
        _base_stem_without_numeric_suffix(path),
        path.suffix.lower(),
        path.stat().st_size,
        _sha256(path),
    )


def _base_stem_without_numeric_suffix(path: Path) -> str:
    return re.sub(r"_\d+$", "", path.stem)


def _preferred_duplicate_path(first: Path, second: Path) -> tuple[Path, Path]:
    first_size = first.stat().st_size if first.exists() else -1
    second_size = second.stat().st_size if second.exists() else -1
    if second_size > first_size:
        return second, first
    if first_size > second_size:
        return first, second
    if re.search(r"_\d+$", first.stem) and not re.search(r"_\d+$", second.stem):
        return second, first
    return first, second


def _delete_duplicate_path(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove duplicate downloaded file: path={} error={}", path, exc)


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _cleanup_empty_temp_folders(download_folder: Path) -> None:
    temp_folder = download_folder / "_tmp_telethon_downloads"
    provisional_folder = temp_folder / "_provisional_no_original_name"
    for folder in (provisional_folder, temp_folder):
        try:
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            pass


def _unique_path(folder: Path, filename: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_windows_filename(filename)
    candidate = folder / safe_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _sanitize_windows_filename(filename: str) -> str:
    clean_name = filename.strip()
    for char in r'<>:"/\|?*':
        clean_name = clean_name.replace(char, "_")
    clean_name = re.sub(r"[\r\n\t]", "_", clean_name)
    clean_name = clean_name.rstrip(" .")
    return clean_name or "telegram_media"


def _is_outgoing_message(message: Any) -> bool:
    return getattr(message, "out", False) is True or getattr(message, "outgoing", False) is True


def _error_type_value(error_type: Any) -> str:
    value = getattr(error_type, "value", None)
    return value if isinstance(value, str) else "UNKNOWN"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must not be negative")


__all__ = [
    "BotConversationConfig",
    "BotConversationResult",
    "BotConversationService",
]
