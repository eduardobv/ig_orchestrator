from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from ig_orchestrator.db import (
    AccountRepository,
    DownloadRepository,
    RunRecord,
    RunRepository,
    UrlJobRepository,
)
from ig_orchestrator.filesystem import ensure_account_folders
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    RunStatus,
    RunSummary,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration.retry_policy import (
    RetryQueue,
    calculate_retry_decision,
)
from ig_orchestrator.orchestration.url_job_processor import UrlJobProcessorResult


class AccountUrlJobProcessor(Protocol):
    async def process(self, url_job_id: int) -> UrlJobProcessorResult:
        """Process one URL job and return the persisted result."""


RetryDelayHandler = Callable[[int], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AccountOrchestratorConfig:
    default_working_folder: Path | None = None
    max_retries: int = 5
    retry_base_seconds: int = 90
    retry_max_seconds: int = 900
    wait_between_retries: bool = False
    retry_delay_handler: RetryDelayHandler | None = None

    def __post_init__(self) -> None:
        if self.default_working_folder is not None and not isinstance(
            self.default_working_folder, Path
        ):
            raise ValueError("default_working_folder must be a pathlib.Path")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if self.retry_base_seconds <= 0:
            raise ValueError("retry_base_seconds must be positive")
        if self.retry_max_seconds <= 0:
            raise ValueError("retry_max_seconds must be positive")


@dataclass(frozen=True, slots=True)
class AccountOrchestratorResult:
    account: Account
    run: RunRecord
    summary: RunSummary
    processed_job_ids: tuple[int, ...] = ()
    error: str | None = None


class AccountOrchestrator:
    """Coordinate folder setup, URL ordering and retry rounds for one account."""

    def __init__(
        self,
        *,
        account_repository: AccountRepository,
        url_job_repository: UrlJobRepository,
        download_repository: DownloadRepository,
        run_repository: RunRepository,
        url_job_processor: AccountUrlJobProcessor,
        config: AccountOrchestratorConfig | None = None,
    ) -> None:
        self._account_repository = account_repository
        self._url_job_repository = url_job_repository
        self._download_repository = download_repository
        self._run_repository = run_repository
        self._url_job_processor = url_job_processor
        self._config = config or AccountOrchestratorConfig()

    async def process_account(self, account_id: int) -> AccountOrchestratorResult:
        if account_id <= 0:
            raise ValueError("account_id must be positive")

        account = self._account_repository.get_by_id(account_id)
        if account is None:
            raise ValueError(f"Account not found: {account_id}")

        jobs = self._url_job_repository.list_by_account(account_id)
        run = self._run_repository.create(
            RunSummary(
                status=RunStatus.PROCESSING,
                total_urls=len(jobs),
                summary=f"Processing account {account.username}",
            ),
            batch_id=account.batch_id,
            account_id=account_id,
        )
        processed_job_ids: list[int] = []

        try:
            account = self._account_repository.update_status(
                account_id,
                AccountStatus.PROCESSING,
            )
            ensure_account_folders(
                account.username,
                _working_base_folder(account, self._config.default_working_folder),
            )

            retry_queue: RetryQueue[int] = RetryQueue()
            for job in _ordered_main_pass_jobs(jobs):
                result = await self._url_job_processor.process(_require_job_id(job))
                processed_job_ids.append(_require_job_id(result.job))
                self._enqueue_or_finalize_retry(result.job, retry_queue)

            for job in _existing_retry_jobs(jobs):
                self._enqueue_or_finalize_retry(job, retry_queue)

            while retry_queue:
                job_id = retry_queue.pop_next()
                if job_id is None:
                    break
                job = self._url_job_repository.get_by_id(job_id)
                if job is None or job.status in _TERMINAL_URL_STATUSES:
                    continue

                decision = self._retry_decision(job)
                if decision.is_final_failure:
                    self._mark_failed_final(job, reason=decision.reason)
                    continue

                if self._config.wait_between_retries and decision.delay_seconds:
                    await self._wait_retry_delay(decision.delay_seconds)

                result = await self._url_job_processor.process(job_id)
                processed_job_ids.append(_require_job_id(result.job))
                if result.job.status in _RETRYABLE_URL_STATUSES:
                    failed_retry = self._increment_retry_failure(result.job)
                    retry_decision = self._retry_decision(failed_retry)
                    if retry_decision.is_final_failure:
                        self._mark_failed_final(
                            failed_retry,
                            reason=retry_decision.reason,
                        )
                    else:
                        retry_queue.requeue(_require_job_id(failed_retry))

            summary = self._build_account_summary(account_id)
            account_status = _account_status_from_summary(summary)
            account = self._account_repository.update_status(account_id, account_status)
            run = self._run_repository.update_summary(
                run.id,
                summary,
                finished_at=datetime.now(timezone.utc),
            )
            return AccountOrchestratorResult(
                account=account,
                run=run,
                summary=summary,
                processed_job_ids=tuple(processed_job_ids),
            )
        except Exception as exc:
            failed_summary = RunSummary(
                status=RunStatus.FAILED,
                total_urls=len(jobs),
                summary=f"Infrastructure failure while processing account {account.username}: {exc}",
            )
            account = self._account_repository.update_status(
                account_id,
                AccountStatus.FAILED,
            )
            run = self._run_repository.update_summary(
                run.id,
                failed_summary,
                finished_at=datetime.now(timezone.utc),
            )
            return AccountOrchestratorResult(
                account=account,
                run=run,
                summary=failed_summary,
                processed_job_ids=tuple(processed_job_ids),
                error=str(exc),
            )

    def _enqueue_or_finalize_retry(
        self,
        job: UrlJob,
        retry_queue: RetryQueue[int],
    ) -> None:
        if job.status not in _RETRYABLE_URL_STATUSES:
            return

        decision = self._retry_decision(job)
        if decision.is_final_failure:
            self._mark_failed_final(job, reason=decision.reason)
            return

        next_retry_at = None
        if decision.delay_seconds is not None:
            next_retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=decision.delay_seconds
            )
        updated = self._url_job_repository.update_error(
            _require_job_id(job),
            status=UrlJobStatus.RETRY_PENDING,
            last_error=job.last_error or "Retry pending",
            last_error_type=job.last_error_type or "RETRY_PENDING",
            non_retryable=job.non_retryable,
            retries=job.retries,
            next_retry_at=next_retry_at,
        )
        retry_queue.enqueue(_require_job_id(updated))

    def _retry_decision(self, job: UrlJob):
        return calculate_retry_decision(
            retries=job.retries,
            max_retries=job.max_retries
            if job.max_retries is not None
            else self._config.max_retries,
            base_seconds=self._config.retry_base_seconds,
            max_seconds=self._config.retry_max_seconds,
            non_retryable=job.non_retryable,
        )

    def _increment_retry_failure(self, job: UrlJob) -> UrlJob:
        return self._url_job_repository.update_error(
            _require_job_id(job),
            status=UrlJobStatus.RETRY_PENDING,
            last_error=job.last_error or "Retry failed",
            last_error_type=job.last_error_type or "RETRY_FAILED",
            non_retryable=job.non_retryable,
            retries=job.retries + 1,
        )

    def _mark_failed_final(self, job: UrlJob, *, reason: str | None) -> UrlJob:
        return self._url_job_repository.update_error(
            _require_job_id(job),
            status=UrlJobStatus.FAILED_FINAL,
            last_error=job.last_error or reason or "Failed final",
            last_error_type=job.last_error_type or reason or "FAILED_FINAL",
            non_retryable=job.non_retryable,
            retries=job.retries,
        )

    async def _wait_retry_delay(self, delay_seconds: int) -> None:
        if self._config.retry_delay_handler is not None:
            await self._config.retry_delay_handler(delay_seconds)
            return

        import asyncio

        await asyncio.sleep(delay_seconds)

    def _build_account_summary(self, account_id: int) -> RunSummary:
        jobs = self._url_job_repository.list_by_account(account_id)
        completed = sum(1 for job in jobs if job.status is UrlJobStatus.COMPLETED)
        failed = sum(1 for job in jobs if job.status is UrlJobStatus.FAILED_FINAL)
        downloaded_files = sum(
            len(self._download_repository.list_by_url_job(_require_job_id(job)))
            for job in jobs
        )
        return RunSummary(
            status=_run_status_from_counts(
                total=len(jobs),
                completed=completed,
                failed=failed,
            ),
            total_urls=len(jobs),
            completed_urls=completed,
            failed_urls=failed,
            downloaded_files=downloaded_files,
            summary=(
                f"Completed {completed}/{len(jobs)} URLs; "
                f"failed final {failed}; files {downloaded_files}."
            ),
        )


_RETRYABLE_URL_STATUSES = {
    UrlJobStatus.RETRY_PENDING,
    UrlJobStatus.FAILED_TEMPORARY,
}
_TERMINAL_URL_STATUSES = {
    UrlJobStatus.COMPLETED,
    UrlJobStatus.FAILED_FINAL,
}


def _ordered_main_pass_jobs(jobs: list[UrlJob]) -> list[UrlJob]:
    pending = [job for job in jobs if job.status is UrlJobStatus.PENDING]
    generated_stories = [
        job for job in pending if job.source is UrlSource.GENERATED_STORY
    ]
    manual_urls = [job for job in pending if job.source is not UrlSource.GENERATED_STORY]
    return [*generated_stories, *manual_urls]


def _existing_retry_jobs(jobs: list[UrlJob]) -> list[UrlJob]:
    return [job for job in jobs if job.status in _RETRYABLE_URL_STATUSES]


def _working_base_folder(account: Account, default_working_folder: Path | None) -> Path:
    if account.working_folder is not None:
        if account.working_folder.name.lower() == account.username.lower():
            return account.working_folder.parent
        return account.working_folder
    if default_working_folder is not None:
        return default_working_folder
    raise ValueError("No working folder is configured for the account")


def _account_status_from_summary(summary: RunSummary) -> AccountStatus:
    if summary.status is RunStatus.COMPLETED:
        return AccountStatus.COMPLETED
    if summary.status is RunStatus.PARTIAL:
        return AccountStatus.PARTIAL
    return AccountStatus.FAILED


def _run_status_from_counts(*, total: int, completed: int, failed: int) -> RunStatus:
    if total == 0 or completed == total:
        return RunStatus.COMPLETED
    if failed == total:
        return RunStatus.FAILED
    return RunStatus.PARTIAL


def _require_job_id(job: UrlJob) -> int:
    if job.id is None:
        raise ValueError("UrlJob.id is required")
    return job.id


__all__ = [
    "AccountOrchestrator",
    "AccountOrchestratorConfig",
    "AccountOrchestratorResult",
]
