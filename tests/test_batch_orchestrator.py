from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db import (
    AccountHistoryRepository,
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
    AccountHistoryStatus,
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
from ig_orchestrator.orchestration import BatchOrchestrator, BatchOrchestratorConfig
from ig_orchestrator.orchestration.account_orchestrator import (
    AccountOrchestratorResult,
)
from ig_orchestrator.orchestration.processing_policy import (
    AccountJobScope,
    account_status_after_scope,
    account_status_from_jobs,
    job_in_scope,
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
        self.scopes: list[AccountJobScope] = []

    async def process_account(
        self,
        account_id: int,
        *,
        scope: AccountJobScope = AccountJobScope.ALL,
    ) -> AccountOrchestratorResult:
        self.calls.append(account_id)
        self.scopes.append(scope)
        desired = self.statuses[account_id]
        jobs = self.job_repo.list_by_account(account_id)
        for job in jobs:
            if not job_in_scope(job, scope):
                continue
            if desired is AccountStatus.FAILED:
                self.job_repo.update_error(
                    job.id,
                    status=UrlJobStatus.FAILED_FINAL,
                    last_error="failed",
                    last_error_type="FAILED",
                    non_retryable=True,
                )
            else:
                self.job_repo.update_status(job.id, UrlJobStatus.COMPLETED)
        jobs = self.job_repo.list_by_account(account_id)
        status = account_status_after_scope(
            jobs,
            scope,
            account_status_from_jobs(jobs),
        )
        account = self.account_repo.update_status(account_id, status)
        completed = sum(1 for job in jobs if job.status is UrlJobStatus.COMPLETED)
        failed = sum(1 for job in jobs if job.status is UrlJobStatus.FAILED_FINAL)
        run_status = RunStatus.COMPLETED
        if failed and completed != len(jobs):
            run_status = RunStatus.PARTIAL
        elif failed == len(jobs) and jobs:
            run_status = RunStatus.FAILED
        summary = RunSummary(
            status=run_status,
            total_urls=len(jobs),
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
    first_job = _create_job(stored.job_repo, first.id)
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
    assert result.batch.status is InputBatchStatus.AWAITING_RENAME
    assert result.summary.status is RunStatus.COMPLETED
    assert result.summary.completed_urls == 2
    assert stored.job_repo.get_by_id(first_job.id).run_id == result.run.id
    assert stored.job_repo.get_by_id(skipped_job.id).run_id == result.run.id


def test_batch_orchestrator_resumes_processing_accounts(
    tmp_path: Path,
) -> None:
    stored = _stored_batch(tmp_path)
    processing = _create_account(stored, "processing", AccountStatus.PROCESSING)
    _create_job(stored.job_repo, processing.id)
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {processing.id: AccountStatus.COMPLETED},
    )
    orchestrator = _batch_orchestrator(stored, fake)

    result = asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert fake.calls == [processing.id]
    assert result.batch.status is InputBatchStatus.AWAITING_RENAME


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


def test_batch_orchestrator_dry_run_processes_pending_accounts_without_status_changes(
    tmp_path: Path,
) -> None:
    stored = _stored_batch(tmp_path)
    first = _create_account(stored, "first", AccountStatus.PENDING)
    skipped = _create_account(stored, "skipped", AccountStatus.COMPLETED)
    _create_job(stored.job_repo, first.id)
    _create_job(stored.job_repo, skipped.id)
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {first.id: AccountStatus.COMPLETED},
    )
    orchestrator = _batch_orchestrator(
        stored,
        fake,
        config=BatchOrchestratorConfig(dry_run=True),
    )

    result = asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert fake.calls == [first.id]
    assert result.batch.status is InputBatchStatus.IMPORTED
    assert stored.batch_repo.get_by_id(stored.batch.id).status is InputBatchStatus.IMPORTED
    assert result.summary.status is RunStatus.COMPLETED
    assert result.summary.total_urls == 2
    assert result.summary.completed_urls == 0
    assert "Dry-run batch batch" in result.summary.summary


def test_real_batch_reactivates_participating_inactive_account(tmp_path: Path) -> None:
    stored = _stored_batch(tmp_path)
    account = _create_account(stored, "returning", AccountStatus.PENDING)
    _create_job(stored.job_repo, account.id)
    history = AccountHistoryRepository(stored.connection)
    history.create_or_get("returning")
    history.set_inactive("returning")
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {account.id: AccountStatus.COMPLETED},
    )

    asyncio.run(_batch_orchestrator(stored, fake).process_batch(stored.batch.id))

    assert history.get_by_user_name("returning").status is AccountHistoryStatus.ENABLED


def test_dry_run_does_not_reactivate_inactive_account(tmp_path: Path) -> None:
    stored = _stored_batch(tmp_path)
    account = _create_account(stored, "still_inactive", AccountStatus.PENDING)
    _create_job(stored.job_repo, account.id)
    history = AccountHistoryRepository(stored.connection)
    history.create_or_get("still_inactive")
    history.set_inactive("still_inactive")
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {account.id: AccountStatus.COMPLETED},
    )

    asyncio.run(
        _batch_orchestrator(
            stored,
            fake,
            config=BatchOrchestratorConfig(dry_run=True),
        ).process_batch(stored.batch.id)
    )

    assert (
        history.get_by_user_name("still_inactive").status
        is AccountHistoryStatus.INACTIVE
    )


def test_batch_orchestrator_reports_compact_account_progress(tmp_path: Path) -> None:
    stored = _stored_batch(tmp_path)
    first = _create_account(stored, "first", AccountStatus.PENDING)
    second = _create_account(stored, "second", AccountStatus.PENDING)
    _create_job(stored.job_repo, first.id)
    _create_job(stored.job_repo, second.id)
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {
            first.id: AccountStatus.COMPLETED,
            second.id: AccountStatus.COMPLETED,
        },
    )
    progress: list[tuple[int, int, str]] = []
    orchestrator = _batch_orchestrator(
        stored,
        fake,
        config=BatchOrchestratorConfig(
            progress_callback=lambda current, total, account: progress.append(
                (current, total, account.username)
            )
        ),
    )

    asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert progress == [(1, 2, "first"), (2, 2, "second")]


def test_batch_orchestrator_cleans_artifacts_after_real_batch(tmp_path: Path) -> None:
    stored = _stored_batch(tmp_path)
    account = _create_account(
        stored,
        "first",
        AccountStatus.PENDING,
        working_folder=tmp_path / "working" / "first",
    )
    _create_job(stored.job_repo, account.id)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    temporary = downloads / "telegram_media_leftover.mp4"
    temporary.write_bytes(b"temporary")
    reels = tmp_path / "working" / "first" / "reels"
    reels.mkdir(parents=True)
    (reels / "123.mp4").write_bytes(b"original")
    duplicate = reels / "123_1.mp4"
    duplicate.write_bytes(b"duplicate")
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {account.id: AccountStatus.COMPLETED},
    )
    orchestrator = _batch_orchestrator(
        stored,
        fake,
        config=BatchOrchestratorConfig(
            telegram_download_folder=downloads,
            default_working_folder=tmp_path / "working",
        ),
    )

    asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert not temporary.exists()
    assert not duplicate.exists()


def test_batch_orchestrator_does_not_clean_artifacts_in_dry_run(tmp_path: Path) -> None:
    stored = _stored_batch(tmp_path)
    account = _create_account(stored, "first", AccountStatus.PENDING)
    _create_job(stored.job_repo, account.id)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    temporary = downloads / "telegram_media_leftover.mp4"
    temporary.write_bytes(b"temporary")
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {account.id: AccountStatus.COMPLETED},
    )
    orchestrator = _batch_orchestrator(
        stored,
        fake,
        config=BatchOrchestratorConfig(
            dry_run=True,
            telegram_download_folder=downloads,
            default_working_folder=tmp_path / "working",
        ),
    )

    asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert temporary.is_file()


def test_batch_orchestrator_stories_first_sweeps_stories_then_remaining(
    tmp_path: Path,
) -> None:
    stored = _stored_batch(tmp_path)
    story_only = _create_account(stored, "story_only", AccountStatus.PENDING)
    mixed = _create_account(stored, "mixed", AccountStatus.PENDING)
    reels_only = _create_account(stored, "reels_only", AccountStatus.PENDING)
    _create_job(
        stored.job_repo,
        story_only.id,
        publication_type=PublicationType.STORY,
        source=UrlSource.GENERATED_STORY,
        url="https://www.instagram.com/stories/story_only/",
    )
    _create_job(
        stored.job_repo,
        mixed.id,
        publication_type=PublicationType.STORY,
        source=UrlSource.GENERATED_STORY,
        url="https://www.instagram.com/stories/mixed/",
    )
    mixed_reel = _create_job(
        stored.job_repo,
        mixed.id,
        url="https://www.instagram.com/reel/MIXED1/",
    )
    reels_job = _create_job(
        stored.job_repo,
        reels_only.id,
        url="https://www.instagram.com/reel/ONLY1/",
    )
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {
            story_only.id: AccountStatus.COMPLETED,
            mixed.id: AccountStatus.COMPLETED,
            reels_only.id: AccountStatus.COMPLETED,
        },
    )
    statuses_after_first: list[AccountStatus] = []

    original = fake.process_account

    async def tracking_process(account_id: int, *, scope=AccountJobScope.ALL):
        result = await original(account_id, scope=scope)
        if len(fake.calls) == 2:
            statuses_after_first.append(
                stored.account_repo.get_by_id(story_only.id).status
            )
            statuses_after_first.append(stored.account_repo.get_by_id(mixed.id).status)
            statuses_after_first.append(
                stored.account_repo.get_by_id(reels_only.id).status
            )
        return result

    fake.process_account = tracking_process  # type: ignore[method-assign]
    orchestrator = _batch_orchestrator(
        stored,
        fake,
        config=BatchOrchestratorConfig(stories_first=True),
    )

    result = asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert fake.calls == [story_only.id, mixed.id, mixed.id, reels_only.id]
    assert fake.scopes == [
        AccountJobScope.STORIES,
        AccountJobScope.STORIES,
        AccountJobScope.NON_STORIES,
        AccountJobScope.NON_STORIES,
    ]
    assert statuses_after_first == [
        AccountStatus.COMPLETED,
        AccountStatus.INCOMPLETE,
        AccountStatus.PENDING,
    ]
    assert stored.account_repo.get_by_id(story_only.id).status is AccountStatus.COMPLETED
    assert stored.account_repo.get_by_id(mixed.id).status is AccountStatus.COMPLETED
    assert stored.account_repo.get_by_id(reels_only.id).status is AccountStatus.COMPLETED
    assert stored.job_repo.get_by_id(mixed_reel.id).status is UrlJobStatus.COMPLETED
    assert stored.job_repo.get_by_id(reels_job.id).status is UrlJobStatus.COMPLETED
    assert result.batch.status is InputBatchStatus.AWAITING_RENAME


def test_batch_orchestrator_legacy_mode_processes_each_account_once(
    tmp_path: Path,
) -> None:
    stored = _stored_batch(tmp_path)
    mixed = _create_account(stored, "mixed", AccountStatus.PENDING)
    reels_only = _create_account(stored, "reels_only", AccountStatus.PENDING)
    _create_job(
        stored.job_repo,
        mixed.id,
        publication_type=PublicationType.STORY,
        source=UrlSource.GENERATED_STORY,
        url="https://www.instagram.com/stories/mixed/",
    )
    _create_job(stored.job_repo, mixed.id, url="https://www.instagram.com/reel/MIXED1/")
    _create_job(
        stored.job_repo,
        reels_only.id,
        url="https://www.instagram.com/reel/ONLY1/",
    )
    fake = FakeAccountOrchestrator(
        stored.account_repo,
        stored.job_repo,
        stored.run_repo,
        {
            mixed.id: AccountStatus.COMPLETED,
            reels_only.id: AccountStatus.COMPLETED,
        },
    )
    orchestrator = _batch_orchestrator(
        stored,
        fake,
        config=BatchOrchestratorConfig(stories_first=False),
    )

    asyncio.run(orchestrator.process_batch(stored.batch.id))

    assert fake.calls == [mixed.id, reels_only.id]
    assert fake.scopes == [AccountJobScope.ALL, AccountJobScope.ALL]
    assert stored.account_repo.get_by_id(mixed.id).status is AccountStatus.COMPLETED


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
    *,
    config: BatchOrchestratorConfig | None = None,
) -> BatchOrchestrator:
    return BatchOrchestrator(
        batch_repository=stored.batch_repo,
        account_repository=stored.account_repo,
        account_history_repository=AccountHistoryRepository(stored.connection),
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        account_orchestrator=fake,
        config=config,
    )


def _create_account(
    stored: StoredBatch,
    username: str,
    status: AccountStatus,
    *,
    working_folder: Path | None = None,
) -> Account:
    return stored.account_repo.create(
        Account(
            batch_id=stored.batch.id,
            username=username,
            start_now_date=date(2026, 6, 14),
            download_stories=False,
            working_folder=working_folder or Path("working") / username,
            status=status,
        )
    )


def _create_job(
    job_repo: UrlJobRepository,
    account_id: int,
    *,
    publication_type: PublicationType = PublicationType.REEL,
    source: UrlSource = UrlSource.INPUT_URL,
    url: str | None = None,
) -> UrlJob:
    if url is None:
        if publication_type is PublicationType.STORY:
            url = "https://www.instagram.com/stories/example_user/"
        else:
            url = "https://www.instagram.com/reel/ABC123xyz/"
    return job_repo.create(
        UrlJob(
            account_id=account_id,
            url=url,
            publication_type=publication_type,
            source=source,
            status=UrlJobStatus.PENDING,
            max_retries=5,
        )
    )
