from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
from collections.abc import Callable
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
    BotResponseStatus,
    parse_bot_response,
)


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
            return BotConversationResult(job=failed_job)

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

        bot_message, direct_paths = await self._wait_for_bot_response_and_downloads(
            job_id=job_id,
            media_filename_prefix=_media_filename_prefix(job),
            since=started_at,
            sent_message_id=sent_message_id,
        )
        logger.info(
            "Bot response received: job_id={} response={}",
            job_id,
            bot_message or "<no text response>",
        )
        response = parse_bot_response(bot_message)

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
        if not detected_paths:
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
    ) -> tuple[str | None, list[Path]]:
        deadline = asyncio.get_running_loop().time() + max(
            self._config.response_wait_timeout_seconds,
            self._config.download_wait_timeout_seconds,
        )
        seen_message_ids: set[int] = set()
        bot_texts: list[str] = []
        downloads: list[_MediaDownload] = []
        last_media_at: float | None = None

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
                    bot_texts.append(text.strip())
                    if parse_bot_response(text).status is not BotResponseStatus.OK:
                        return _join_bot_texts(bot_texts), _finalize_media_downloads(
                            self._config.download_folder,
                            downloads,
                            media_filename_prefix,
                        )

                if _message_has_media(message) and _can_download_media(
                    self._telegram_client
                ):
                    download = await self._download_bot_message_media(job_id, message)
                    downloads.append(download)
                    if download.path or download.provisional_path:
                        last_media_at = asyncio.get_running_loop().time()

            now = asyncio.get_running_loop().time()
            if downloads and last_media_at is not None:
                quiet_seconds = now - last_media_at
                if quiet_seconds >= self._config.download_stable_seconds:
                    return _join_bot_texts(bot_texts), _finalize_media_downloads(
                        self._config.download_folder,
                        downloads,
                        media_filename_prefix,
                    )

            if now >= deadline:
                return _join_bot_texts(bot_texts), _finalize_media_downloads(
                    self._config.download_folder,
                    downloads,
                    media_filename_prefix,
                )

            await asyncio.sleep(
                min(self._config.response_poll_interval_seconds, deadline - now)
            )

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
