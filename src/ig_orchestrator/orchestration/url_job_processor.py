from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ig_orchestrator.db import AccountRepository, DownloadRepository, UrlJobRepository
from ig_orchestrator.filesystem import (
    move_downloaded_files,
    resolve_publication_type_after_download,
)
from ig_orchestrator.filesystem.file_classifier import classify_file_media_type
from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    DownloadFile,
    DownloadFileStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
)
from ig_orchestrator.orchestration.post_availability import (
    MEDIA_REMOVED_ERROR_TYPE,
    AvailabilityChecker,
    PostAvailability,
)
from ig_orchestrator.orchestration.processing_policy import (
    TERMINAL_URL_STATUSES,
    account_status_from_jobs,
)
from ig_orchestrator.orchestration.retry_policy import MEDIA_NOT_FOUND_ERROR_TYPE
from ig_orchestrator.telegram import BotConversationResult
from ig_orchestrator.telemetry.observer import NullObserver, RunObserver
from ig_orchestrator.telemetry.trace import AttemptTrace


logger = get_logger()


class UrlJobConversationService(Protocol):
    async def process_url_job(self, job: UrlJob) -> BotConversationResult:
        """Process a URL job against Telegram and persist detected downloads."""


FileMover = Callable[
    [str, Path | str, PublicationType, list[DownloadFile]],
    list[DownloadFile],
]


ErrorNotifier = Callable[[UrlJob, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class UrlJobProcessorConfig:
    default_working_folder: Path | None = None
    error_notifier: ErrorNotifier | None = None
    availability_checker: AvailabilityChecker | None = None

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
        observer: RunObserver | None = None,
    ) -> None:
        self._url_job_repository = url_job_repository
        self._account_repository = account_repository
        self._download_repository = download_repository
        self._conversation_service = conversation_service
        self._config = config or UrlJobProcessorConfig()
        self._file_mover = file_mover
        self._observer: RunObserver = observer or NullObserver()
        self._trace: AttemptTrace | None = None

    @property
    def stall_pending(self) -> bool:
        """True while the bot is being probed after a URL without an answer."""

        return bool(getattr(self._conversation_service, "has_unanswered", False))

    async def process(self, url_job_id: int) -> UrlJobProcessorResult:
        self._trace = None
        try:
            result = await self._process(url_job_id)
        except BaseException:
            self._finish_trace(None)
            raise
        self._finish_trace(result)
        return result

    def _finish_trace(self, result: UrlJobProcessorResult | None) -> None:
        trace, self._trace = self._trace, None
        if trace is None:
            return
        if result is None:
            trace.finish(outcome="EXCEPTION", error_code=None)
        else:
            trace.files_count = len(result.files)
            trace.finish(
                outcome=result.job.status.value,
                error_code=result.job.last_error_type,
            )
        self._observer.finish_attempt(trace)

    async def _process(self, url_job_id: int) -> UrlJobProcessorResult:
        if url_job_id <= 0:
            raise ValueError("url_job_id must be positive")

        job = self._url_job_repository.get_by_id(url_job_id)
        if job is None:
            raise ValueError(f"URL job not found: {url_job_id}")

        account = self._account_repository.get_by_id(job.account_id)
        if account is None:
            raise ValueError(f"Account not found for URL job: {job.account_id}")

        logger.info(
            "URL job processor started: job_id={} account_id={} type={} status={} url={}",
            url_job_id,
            job.account_id,
            job.publication_type.value,
            job.status.value,
            job.url,
        )
        conversation_result = await self._conversation_service.process_url_job(job)
        # Answers of earlier silent URLs that arrived once the bot woke up.
        late_accounts: list[Account] = []
        for late in conversation_result.late_results:
            late_account = await self._finish_late_result(late)
            if late_account is not None:
                late_accounts.append(late_account)
        self._trace = conversation_result.trace
        if self._trace is not None:
            self._trace.batch_id = account.batch_id
        result = await self._finalize_conversation(url_job_id, account, conversation_result)
        for late_account in late_accounts:
            self.refresh_account_status(late_account)
        return result

    async def process_http(self, url_job_id: int, paths: list[Path]) -> UrlJobProcessorResult:
        """Finish a URL whose files were downloaded over HTTP instead of the bot.

        Same path as a bot download: files are stored, moved to the account
        folders and the job ends COMPLETED.
        """

        job = self._url_job_repository.get_by_id(url_job_id)
        if job is None:
            raise ValueError(f"URL job not found: {url_job_id}")
        account = self._account_repository.get_by_id(job.account_id)
        if account is None:
            raise ValueError(f"Account not found for URL job: {job.account_id}")
        if not paths:
            raise ValueError("process_http needs at least one file")
        self._trace = None
        stored = [
            self._download_repository.create(
                DownloadFile(
                    url_job_id=url_job_id,
                    original_path=path,
                    media_type=classify_file_media_type(path),
                    file_extension=path.suffix.lower(),
                    file_size=path.stat().st_size if path.exists() else None,
                    status=DownloadFileStatus.DETECTED,
                )
            )
            for path in paths
        ]
        from datetime import datetime, timezone

        downloaded = self._url_job_repository.update_status(
            url_job_id,
            UrlJobStatus.DOWNLOADED,
            finished_at=datetime.now(timezone.utc),
        )
        result = await self._finalize_conversation(
            url_job_id,
            account,
            BotConversationResult(job=downloaded, files=tuple(stored)),
        )
        self.refresh_account_status(account)
        return result

    async def _finish_late_result(self, late: BotConversationResult) -> Account | None:
        """Move and store the files of a URL answered after its own attempt ended."""

        late_job_id = late.job.id
        try:
            if late_job_id is None:
                return None
            late_account = self._account_repository.get_by_id(late.job.account_id)
            if late_account is None:
                return None
            result = await self._finalize_conversation(late_job_id, late_account, late)
            logger.info(
                "Late bot answer finished: job_id={} status={} files={}",
                late_job_id,
                result.job.status.value,
                len(result.files),
            )
            return late_account
        except Exception:
            logger.exception("Finishing a late bot answer failed: job_id={}", late_job_id)
            return None

    def refresh_account_status(self, account: Account) -> None:
        """An account that already ended may become complete through a late answer."""

        if account.id is None:
            return
        current = self._account_repository.get_by_id(account.id)
        if current is None or current.status not in (
            AccountStatus.PARTIAL,
            AccountStatus.INCOMPLETE,
        ):
            return
        jobs = self._url_job_repository.list_by_account(account.id)
        if jobs and all(job.status in TERMINAL_URL_STATUSES for job in jobs):
            self._account_repository.update_status(account.id, account_status_from_jobs(jobs))

    async def _finalize_conversation(
        self,
        url_job_id: int,
        account: Account,
        conversation_result: BotConversationResult,
    ) -> UrlJobProcessorResult:
        processed_job = conversation_result.job
        detected_files = list(conversation_result.files)

        if processed_job.status is not UrlJobStatus.DOWNLOADED:
            processed_job = await self._finalize_if_removed(processed_job)
            logger.info(
                "URL job processor finished without download: job_id={} status={} error_type={}",
                url_job_id,
                processed_job.status.value,
                processed_job.last_error_type or "-",
            )
            await self._notify_error(processed_job, account.username)
            return UrlJobProcessorResult(job=processed_job, files=tuple(detected_files))

        if not detected_files:
            logger.warning("URL job downloaded but returned no files: job_id={}", url_job_id)
            failed_job = self._url_job_repository.update_error(
                _require_job_id(processed_job),
                status=UrlJobStatus.RETRY_PENDING,
                last_error="No downloaded files were returned by the conversation service.",
                last_error_type="NO_FILES_DETECTED",
                non_retryable=False,
            )
            await self._notify_error(failed_job, account.username)
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
            logger.info(
                "URL job publication type corrected: job_id={} from={} to={}",
                url_job_id,
                processed_job.publication_type.value,
                final_publication_type.value,
            )
            processed_job = self._url_job_repository.update_publication_type(
                _require_job_id(processed_job),
                final_publication_type,
            )

        move_started = time.monotonic()
        try:
            moved_files = self._file_mover(
                account.username,
                working_base,
                final_publication_type,
                detected_files,
            )
            if self._trace is not None:
                self._trace.t_move_ms = int((time.monotonic() - move_started) * 1000)
        except Exception as exc:
            logger.exception(
                "Moving downloaded files failed: job_id={} error={}",
                url_job_id,
                exc,
            )
            failed_job = self._url_job_repository.update_error(
                _require_job_id(processed_job),
                status=UrlJobStatus.RETRY_PENDING,
                last_error=str(exc),
                last_error_type="MOVE_FILES_FAILED",
                non_retryable=False,
            )
            await self._notify_error(failed_job, account.username)
            return UrlJobProcessorResult(job=failed_job, files=tuple(detected_files))

        stored_files = tuple(
            self._download_repository.update(moved_file) for moved_file in moved_files
        )
        logger.info(
            "Downloaded files moved: job_id={} count={} destinations={}",
            url_job_id,
            len(stored_files),
            [str(file.working_path or file.final_path or file.original_path) for file in stored_files],
        )
        completed_job = self._url_job_repository.update_status(
            _require_job_id(processed_job),
            UrlJobStatus.COMPLETED,
            finished_at=processed_job.finished_at,
        )
        logger.info(
            "URL job processor completed: job_id={} status={}",
            url_job_id,
            completed_job.status.value,
        )
        return UrlJobProcessorResult(job=completed_job, files=stored_files)

    async def _finalize_if_removed(self, job: UrlJob) -> UrlJob:
        """Stop retrying a ``Media not found`` job when Instagram shows it is gone."""

        checker = self._config.availability_checker
        if (
            checker is None
            or job.last_error_type != MEDIA_NOT_FOUND_ERROR_TYPE
            or job.status is UrlJobStatus.FAILED_FINAL
        ):
            return job
        try:
            availability = await checker(job.url)
        except Exception:
            logger.warning("Post availability check failed", exc_info=True)
            return job
        if availability is not PostAvailability.REMOVED:
            return job
        logger.warning(
            "Post no longer exists on Instagram; not retrying: job_id={} url={}",
            job.id,
            job.url,
        )
        return self._url_job_repository.update_error(
            _require_job_id(job),
            status=UrlJobStatus.FAILED_FINAL,
            last_error=(
                f"{job.last_error or 'Media not found or unavailable'} "
                "[Instagram: post unavailable, not retried]"
            ),
            last_error_type=MEDIA_REMOVED_ERROR_TYPE,
            non_retryable=True,
            retries=job.retries,
        )

    async def _notify_error(self, job: UrlJob, username: str) -> None:
        notifier = self._config.error_notifier
        if notifier is None or not job.last_error_type:
            return
        try:
            await notifier(job, username)
        except Exception:
            logger.warning(
                "URL job error notifier failed: job_id={} error_type={}",
                job.id,
                job.last_error_type,
            )


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
