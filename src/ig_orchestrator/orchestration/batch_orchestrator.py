from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    DownloadRepository,
    RunRecord,
    RunRepository,
    UrlJobRepository,
)
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    InputBatch,
    InputBatchStatus,
    RunStatus,
    RunSummary,
    UrlJobStatus,
)
from ig_orchestrator.logging_config import configure_app_logging, get_logger
from ig_orchestrator.orchestration.account_orchestrator import (
    AccountOrchestratorResult,
)


logger = get_logger()


class BatchAccountOrchestrator(Protocol):
    async def process_account(self, account_id: int) -> AccountOrchestratorResult:
        """Process one account by id."""


@dataclass(frozen=True, slots=True)
class BatchOrchestratorResult:
    batch: InputBatch
    run: RunRecord
    summary: RunSummary
    account_results: tuple[AccountOrchestratorResult, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BatchOrchestratorConfig:
    dry_run: bool = False


class BatchOrchestrator:
    """Coordinate all pending accounts for one imported batch."""

    def __init__(
        self,
        *,
        batch_repository: BatchRepository,
        account_repository: AccountRepository,
        url_job_repository: UrlJobRepository,
        download_repository: DownloadRepository,
        run_repository: RunRepository,
        account_orchestrator: BatchAccountOrchestrator,
        config: BatchOrchestratorConfig | None = None,
    ) -> None:
        self._batch_repository = batch_repository
        self._account_repository = account_repository
        self._url_job_repository = url_job_repository
        self._download_repository = download_repository
        self._run_repository = run_repository
        self._account_orchestrator = account_orchestrator
        self._config = config or BatchOrchestratorConfig()

    async def process_batch(self, batch_id: int) -> BatchOrchestratorResult:
        if batch_id <= 0:
            raise ValueError("batch_id must be positive")

        batch = self._batch_repository.get_by_id(batch_id)
        if batch is None:
            raise ValueError(f"Input batch not found: {batch_id}")

        accounts = self._account_repository.list_by_batch(batch_id)
        run = self._run_repository.create(
            RunSummary(
                status=RunStatus.PROCESSING,
                total_urls=_count_batch_urls(
                    self._url_job_repository,
                    [account.id for account in accounts if account.id is not None],
                ),
                summary=f"Processing batch {batch.batch_name}",
            ),
            batch_id=batch_id,
        )
        account_results: list[AccountOrchestratorResult] = []

        try:
            configure_app_logging()
            logger.info(
                "Batch processing started: batch_id={} batch_name={} accounts={} total_urls={}",
                batch_id,
                batch.batch_name,
                len(accounts),
                run.total_urls,
            )
            if self._config.dry_run:
                return await self._process_batch_dry_run(
                    batch=batch,
                    batch_id=batch_id,
                    accounts=accounts,
                    run=run,
                )

            batch = self._batch_repository.update_status(
                batch_id,
                InputBatchStatus.PROCESSING,
            )
            for account in accounts:
                if account.id is None or account.status not in _PROCESSABLE_ACCOUNT_STATUSES:
                    continue
                logger.info(
                    "Processing batch account: batch_id={} account_id={} username={}",
                    batch_id,
                    account.id,
                    account.username,
                )
                account_results.append(
                    await self._account_orchestrator.process_account(account.id)
                )

            summary = self._build_batch_summary(batch_id)
            batch = self._batch_repository.update_status(
                batch_id,
                _batch_status_from_summary(summary),
            )
            run = self._run_repository.update_summary(
                run.id,
                summary,
                finished_at=datetime.now(timezone.utc),
            )
            logger.info(
                "Batch processing finished: batch_id={} status={} completed_urls={} failed_urls={} downloaded_files={}",
                batch_id,
                summary.status.value,
                summary.completed_urls,
                summary.failed_urls,
                summary.downloaded_files,
            )
            return BatchOrchestratorResult(
                batch=batch,
                run=run,
                summary=summary,
                account_results=tuple(account_results),
            )
        except Exception as exc:
            logger.exception(
                "Infrastructure failure while processing batch {}: {}",
                batch.batch_name,
                exc,
            )
            failed_summary = RunSummary(
                status=RunStatus.FAILED,
                total_urls=run.total_urls,
                summary=f"Infrastructure failure while processing batch {batch.batch_name}: {exc}",
            )
            batch = self._batch_repository.update_status(
                batch_id,
                InputBatchStatus.FAILED,
            )
            run = self._run_repository.update_summary(
                run.id,
                failed_summary,
                finished_at=datetime.now(timezone.utc),
            )
            return BatchOrchestratorResult(
                batch=batch,
                run=run,
                summary=failed_summary,
                account_results=tuple(account_results),
                error=str(exc),
            )

    async def process_batch_by_name(self, batch_name: str) -> BatchOrchestratorResult:
        if not batch_name.strip():
            raise ValueError("batch_name must not be blank")
        batch = self._batch_repository.get_by_name(batch_name)
        if batch is None or batch.id is None:
            raise ValueError(f"Input batch not found: {batch_name}")
        return await self.process_batch(batch.id)

    async def _process_batch_dry_run(
        self,
        *,
        batch: InputBatch,
        batch_id: int,
        accounts: list[Account],
        run: RunRecord,
    ) -> BatchOrchestratorResult:
        account_results: list[AccountOrchestratorResult] = []
        pending_accounts = [
            account
            for account in accounts
            if account.id is not None and account.status in _PROCESSABLE_ACCOUNT_STATUSES
        ]
        for account in pending_accounts:
            logger.info(
                "Dry-run would process batch account: batch_id={} account_id={} username={}",
                batch_id,
                account.id,
                account.username,
            )
            account_results.append(
                await self._account_orchestrator.process_account(account.id)
            )

        total_urls = _count_batch_urls(
            self._url_job_repository,
            [account.id for account in accounts if account.id is not None],
        )
        summary = RunSummary(
            status=RunStatus.COMPLETED,
            total_urls=total_urls,
            completed_urls=0,
            failed_urls=0,
            downloaded_files=0,
            summary=(
                f"Dry-run batch {batch.batch_name}: would process "
                f"{len(pending_accounts)} pending account(s) and {total_urls} URL(s); "
                "no Telegram messages sent and no files moved."
            ),
        )
        run = self._run_repository.update_summary(
            run.id,
            summary,
            finished_at=datetime.now(timezone.utc),
        )
        logger.info(
            "Dry-run batch processing finished: batch_id={} accounts={} total_urls={}",
            batch_id,
            len(pending_accounts),
            total_urls,
        )
        return BatchOrchestratorResult(
            batch=batch,
            run=run,
            summary=summary,
            account_results=tuple(account_results),
        )

    def _build_batch_summary(self, batch_id: int) -> RunSummary:
        accounts = self._account_repository.list_by_batch(batch_id)
        account_ids = [account.id for account in accounts if account.id is not None]
        jobs = [
            job
            for account_id in account_ids
            for job in self._url_job_repository.list_by_account(account_id)
        ]
        completed = sum(1 for job in jobs if job.status is UrlJobStatus.COMPLETED)
        failed = sum(1 for job in jobs if job.status is UrlJobStatus.FAILED_FINAL)
        downloaded_files = sum(
            len(self._download_repository.list_by_url_job(job.id))
            for job in jobs
            if job.id is not None
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


def _count_batch_urls(
    url_job_repository: UrlJobRepository,
    account_ids: list[int],
) -> int:
    return sum(
        len(url_job_repository.list_by_account(account_id)) for account_id in account_ids
    )


def _batch_status_from_summary(summary: RunSummary) -> InputBatchStatus:
    if summary.status is RunStatus.COMPLETED:
        return InputBatchStatus.COMPLETED
    if summary.status is RunStatus.PARTIAL:
        return InputBatchStatus.PARTIAL
    return InputBatchStatus.FAILED


def _run_status_from_counts(*, total: int, completed: int, failed: int) -> RunStatus:
    if total == 0 or completed == total:
        return RunStatus.COMPLETED
    if failed == total:
        return RunStatus.FAILED
    return RunStatus.PARTIAL


_PROCESSABLE_ACCOUNT_STATUSES = {
    AccountStatus.PENDING,
    AccountStatus.PROCESSING,
    AccountStatus.PARTIAL,
}


__all__ = [
    "BatchOrchestratorConfig",
    "BatchOrchestrator",
    "BatchOrchestratorResult",
]
