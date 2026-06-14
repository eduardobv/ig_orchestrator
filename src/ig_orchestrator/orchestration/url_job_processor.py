from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ig_orchestrator.db import AccountRepository, DownloadRepository, UrlJobRepository
from ig_orchestrator.filesystem import (
    move_downloaded_files,
    resolve_publication_type_after_download,
)
from ig_orchestrator.models import DownloadFile, PublicationType, UrlJob, UrlJobStatus
from ig_orchestrator.telegram import BotConversationResult


class UrlJobConversationService(Protocol):
    async def process_url_job(self, job: UrlJob) -> BotConversationResult:
        """Process a URL job against Telegram and persist detected downloads."""


FileMover = Callable[
    [str, Path | str, PublicationType, list[DownloadFile]],
    list[DownloadFile],
]


@dataclass(frozen=True, slots=True)
class UrlJobProcessorConfig:
    default_working_folder: Path | None = None

    def __post_init__(self) -> None:
        if self.default_working_folder is not None and not isinstance(
            self.default_working_folder, Path
        ):
            raise ValueError("default_working_folder must be a pathlib.Path")


@dataclass(frozen=True, slots=True)
class UrlJobProcessorResult:
    job: UrlJob
    files: tuple[DownloadFile, ...] = ()


class UrlJobProcessor:
    """Coordinate processing, movement and persistence for one URL job."""

    def __init__(
        self,
        *,
        url_job_repository: UrlJobRepository,
        account_repository: AccountRepository,
        download_repository: DownloadRepository,
        conversation_service: UrlJobConversationService,
        config: UrlJobProcessorConfig | None = None,
        file_mover: FileMover = move_downloaded_files,
    ) -> None:
        self._url_job_repository = url_job_repository
        self._account_repository = account_repository
        self._download_repository = download_repository
        self._conversation_service = conversation_service
        self._config = config or UrlJobProcessorConfig()
        self._file_mover = file_mover

    async def process(self, url_job_id: int) -> UrlJobProcessorResult:
        if url_job_id <= 0:
            raise ValueError("url_job_id must be positive")

        job = self._url_job_repository.get_by_id(url_job_id)
        if job is None:
            raise ValueError(f"URL job not found: {url_job_id}")

        account = self._account_repository.get_by_id(job.account_id)
        if account is None:
            raise ValueError(f"Account not found for URL job: {job.account_id}")

        conversation_result = await self._conversation_service.process_url_job(job)
        processed_job = conversation_result.job
        detected_files = list(conversation_result.files)

        if processed_job.status is not UrlJobStatus.DOWNLOADED:
            return UrlJobProcessorResult(job=processed_job, files=tuple(detected_files))

        if not detected_files:
            failed_job = self._url_job_repository.update_error(
                _require_job_id(processed_job),
                status=UrlJobStatus.RETRY_PENDING,
                last_error="No downloaded files were returned by the conversation service.",
                last_error_type="NO_FILES_DETECTED",
                non_retryable=False,
            )
            return UrlJobProcessorResult(job=failed_job)

        working_base = _working_base_folder(
            account_username=account.username,
            account_working_folder=account.working_folder,
            default_working_folder=self._config.default_working_folder,
        )
        final_publication_type = resolve_publication_type_after_download(
            processed_job.publication_type,
            detected_files,
        )
        if final_publication_type is not processed_job.publication_type:
            processed_job = self._url_job_repository.update_publication_type(
                _require_job_id(processed_job),
                final_publication_type,
            )

        try:
            moved_files = self._file_mover(
                account.username,
                working_base,
                final_publication_type,
                detected_files,
            )
        except Exception as exc:
            failed_job = self._url_job_repository.update_error(
                _require_job_id(processed_job),
                status=UrlJobStatus.RETRY_PENDING,
                last_error=str(exc),
                last_error_type="MOVE_FILES_FAILED",
                non_retryable=False,
            )
            return UrlJobProcessorResult(job=failed_job, files=tuple(detected_files))

        stored_files = tuple(
            self._download_repository.update(moved_file) for moved_file in moved_files
        )
        completed_job = self._url_job_repository.update_status(
            _require_job_id(processed_job),
            UrlJobStatus.COMPLETED,
            finished_at=processed_job.finished_at,
        )
        return UrlJobProcessorResult(job=completed_job, files=stored_files)


def _working_base_folder(
    *,
    account_username: str,
    account_working_folder: Path | None,
    default_working_folder: Path | None,
) -> Path:
    if account_working_folder is not None:
        if account_working_folder.name.lower() == account_username.lower():
            return account_working_folder.parent
        return account_working_folder

    if default_working_folder is not None:
        return default_working_folder

    raise ValueError(
        "No working folder is configured for the account or URL job processor"
    )


def _require_job_id(job: UrlJob) -> int:
    if job.id is None:
        raise ValueError("UrlJob.id is required")
    return job.id


__all__ = [
    "UrlJobProcessor",
    "UrlJobProcessorConfig",
    "UrlJobProcessorResult",
]
