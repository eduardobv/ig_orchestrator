from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ig_orchestrator.db import DownloadRepository, UrlJobRepository
from ig_orchestrator.filesystem.file_classifier import classify_file_media_type
from ig_orchestrator.filesystem.file_watcher import watch_downloaded_files
from ig_orchestrator.models import (
    DownloadFile,
    DownloadFileStatus,
    UrlJob,
    UrlJobStatus,
)
from ig_orchestrator.telegram.bot_response_parser import (
    BotResponseStatus,
    parse_bot_response,
)


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


Watcher = Callable[[Path, datetime, float, float], list[Path]]


@dataclass(frozen=True, slots=True)
class BotConversationConfig:
    download_folder: Path
    download_wait_timeout_seconds: float
    download_stable_seconds: float
    response_wait_timeout_seconds: float = 30.0
    response_poll_interval_seconds: float = 0.5
    response_message_limit: int = 50

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
        if self.response_message_limit <= 0:
            raise ValueError("response_message_limit must be positive")


@dataclass(frozen=True, slots=True)
class BotConversationResult:
    job: UrlJob
    files: tuple[DownloadFile, ...] = ()
    bot_message: str | None = None


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
    ) -> None:
        self._telegram_client = telegram_client
        self._url_job_repository = url_job_repository
        self._download_repository = download_repository
        self._config = config
        self._watcher = watcher
        self._lock = asyncio.Lock()

    async def process_url_job(self, job: UrlJob) -> BotConversationResult:
        if job.id is None:
            raise ValueError("UrlJob.id is required to process a conversation")

        async with self._lock:
            return await self._process_url_job_locked(job)

    async def _process_url_job_locked(self, job: UrlJob) -> BotConversationResult:
        job_id = _require_job_id(job)
        started_at = _utc_now()
        current_job = self._url_job_repository.update_status(
            job_id,
            UrlJobStatus.SENT_TO_BOT,
            started_at=started_at,
        )

        try:
            sent_message = await self._telegram_client.send_message_to_bot(job.url)
        except Exception as exc:
            failed_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error=str(exc),
                last_error_type="SEND_MESSAGE_FAILED",
                non_retryable=False,
            )
            return BotConversationResult(job=failed_job)

        sent_message_id = _message_id(sent_message)
        if sent_message_id is not None:
            current_job = self._url_job_repository.update_sent_message_id(
                job_id,
                sent_message_id,
            )

        bot_message = await self._wait_for_bot_text_response(
            since=started_at,
            sent_message_id=sent_message_id,
        )
        response = parse_bot_response(bot_message)

        if response.status is BotResponseStatus.NON_RETRYABLE_ERROR:
            failed_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.FAILED_FINAL,
                last_error=response.last_error or "",
                last_error_type=_error_type_value(response.last_error_type),
                non_retryable=True,
            )
            return BotConversationResult(job=failed_job, bot_message=bot_message)

        if response.status is BotResponseStatus.RETRYABLE_ERROR:
            retry_job = self._url_job_repository.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error=response.last_error or "",
                last_error_type=_error_type_value(response.last_error_type),
                non_retryable=False,
            )
            return BotConversationResult(job=retry_job, bot_message=bot_message)

        current_job = self._url_job_repository.update_status(
            job_id,
            UrlJobStatus.WAITING_DOWNLOAD,
        )
        detected_paths = self._watcher(
            self._config.download_folder,
            started_at,
            self._config.download_wait_timeout_seconds,
            self._config.download_stable_seconds,
        )

        if not detected_paths:
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
        return BotConversationResult(
            job=downloaded_job,
            files=files,
            bot_message=bot_message,
        )

    async def _wait_for_bot_text_response(
        self,
        *,
        since: datetime,
        sent_message_id: int | None,
    ) -> str | None:
        deadline = asyncio.get_running_loop().time() + (
            self._config.response_wait_timeout_seconds
        )
        seen_message_ids: set[int] = set()

        while True:
            messages = await self._telegram_client.get_bot_messages_after(
                since,
                limit=self._config.response_message_limit,
            )
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

                text = _message_text(message)
                if text is not None and text.strip():
                    return text

            now = asyncio.get_running_loop().time()
            if now >= deadline:
                return None

            await asyncio.sleep(
                min(self._config.response_poll_interval_seconds, deadline - now)
            )

    def _store_detected_file(self, job_id: int, path: Path) -> DownloadFile:
        media_type = classify_file_media_type(path)
        file_size = path.stat().st_size if path.exists() else None
        return self._download_repository.create(
            DownloadFile(
                url_job_id=job_id,
                original_path=path,
                media_type=media_type,
                file_extension=path.suffix.lower(),
                file_size=file_size,
                status=DownloadFileStatus.DETECTED,
            )
        )


def _require_job_id(job: UrlJob) -> int:
    if job.id is None:
        raise ValueError("UrlJob.id is required")
    return job.id


def _message_id(message: Any) -> int | None:
    value = getattr(message, "id", None)
    return value if isinstance(value, int) and value > 0 else None


def _message_text(message: Any) -> str | None:
    for attribute in ("text", "message", "raw_text"):
        value = getattr(message, attribute, None)
        if isinstance(value, str):
            return value
    return None


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
