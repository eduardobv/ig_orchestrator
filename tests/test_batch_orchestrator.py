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
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    InputBatch,
    InputBatchStatus,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration import BatchOrchestrator
from ig_orchestrator.orchestration.account_orchestrator import (
    AccountOrchestratorResult,
)


@dataclass
class StoredBatch:
    connection: Connection
    batch_repo: BatchRepository
    account_repo: AccountRepository
    job_repo: UrlJobRepository
    download_repo: DownloadRepository
    run_repo: RunRepository
    batch: InputBatch


class FakeAccountOrchestrator:
    def __init__(
        self,
        account_repo: AccountRepository,
        job_repo: UrlJobRepository,
        run_repo: RunRepository,
        statuses: dict[int, AccountStatus],
    ) -> None:
        self.account_repo = account_repo
        self.job_repo = job_repo
        self.run_repo = run_repo
        self.statuses = statuses
        self.calls: list[int] = []

    async def process_account(self, account_id: int) -> AccountOrchestratorResult:
        self.calls.append(account_id)
        status = self.statuses[account_id]
        account = self.account_repo.update_status(account_id, status)
        jobs = self.job_repo.list_by_account(account_id)
        for job in jobs:
            if status is AccountStatus.COMPLETED:
                self.job_repo.update_status(job.id, UrlJobStatus.COMPLETED)
            elif status is AccountStatus.FAILED:
                self.job_repo.update_error(
                    job.id,
                    status=UrlJobStatus.FAILED_FINAL,
                    last_error="failed",
                    last_error_type="FAILED",
                    non_retryable=True,
                )
        completed = 1 if status is AccountStatus.COMPLETED else 0
        failed = 1 if status is AccountStatus.FAILED else 0
        summary = RunSummary(
            status=RunStatus(status.value),
            total_urls=1,
            completed_urls=completed,
            failed_urls=failed,
        )
        run = self.run_repo.create(summary, account_id=account_id)
        return AccountOrchestratorResult(account=account, run=run, summary=summary)


def test_batch_orchestrator_processes_pending_accounts_and_marks_completed(
    tmp_path: Path,
) -> None:
    stored = _stored_batch(tmp_path)
    first = _create_account(stored, "first", AccountStatus.PENDING)
    skipped = _create_account(stored, "skipped", AccountStatus.COMPLETED)
    _create_job(stored.job_repo, first.id)
    skipped_job = _create_job(stored.job_repo, skipped.id)
    stored.job_repo.update_status(skipped_job.id, UrlJobStatus.COMPLETED)
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {first.id: AccountStatus.COMPLETED},
    )
    orchestrator = _batch_orchestrator(stored, fake)

    result = asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert fake.calls == [first.id]
    assert result.batch.status is InputBatchStatus.COMPLETED
    assert result.summary.status is RunStatus.COMPLETED
    assert result.summary.completed_urls == 2


def test_batch_orchestrator_marks_partial_when_an_account_fails(
    tmp_path: Path,
) -> None:
    stored = _stored_batch(tmp_path)
    completed = _create_account(stored, "completed", AccountStatus.PENDING)
    failed = _create_account(stored, "failed", AccountStatus.PENDING)
    _create_job(stored.job_repo, completed.id)
    _create_job(stored.job_repo, failed.id)
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {
            completed.id: AccountStatus.COMPLETED,
            failed.id: AccountStatus.FAILED,
        },
    )
    orchestrator = _batch_orchestrator(stored, fake)

    result = asyncio.run(orchestrator.process_batch_by_name("batch"))

    assert fake.calls == [completed.id, failed.id]
    assert result.batch.status is InputBatchStatus.PARTIAL
    assert result.summary.status is RunStatus.PARTIAL
    assert result.summary.completed_urls == 1
    assert result.summary.failed_urls == 1


def _stored_batch(tmp_path: Path) -> StoredBatch:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    connection = connect(db_path)
    batch_repo = BatchRepository(connection)
    batch = batch_repo.create(
        InputBatch(
            batch_name="batch",
            schema_version="1.0",
            status=InputBatchStatus.IMPORTED,
        )
    )
    return StoredBatch(
        connection=connection,
        batch_repo=batch_repo,
        account_repo=AccountRepository(connection),
        job_repo=UrlJobRepository(connection),
        download_repo=DownloadRepository(connection),
        run_repo=RunRepository(connection),
        batch=batch,
    )


def _batch_orchestrator(
    stored: StoredBatch,
    fake: FakeAccountOrchestrator,
) -> BatchOrchestrator:
    return BatchOrchestrator(
        batch_repository=stored.batch_repo,
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        account_orchestrator=fake,
    )


def _create_account(
    stored: StoredBatch,
    username: str,
    status: AccountStatus,
) -> Account:
    return stored.account_repo.create(
        Account(
            batch_id=stored.batch.id,
            username=username,
            start_now_date=date(2026, 6, 14),
            download_stories=False,
            working_folder=Path("working") / username,
            status=status,
        )
    )


def _create_job(job_repo: UrlJobRepository, account_id: int) -> UrlJob:
    return job_repo.create(
        UrlJob(
            account_id=account_id,
            url="https://www.instagram.com/reel/ABC123xyz/",
            publication_type=PublicationType.REEL,
            source=UrlSource.INPUT_URL,
            status=UrlJobStatus.PENDING,
            max_retries=5,
        )
    )
