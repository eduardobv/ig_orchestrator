from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
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
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration import (
    AccountOrchestrator,
    AccountOrchestratorConfig,
    UrlJobProcessorResult,
)


@dataclass
class StoredAccount:
    connection: Connection
    account_repo: AccountRepository
    batch_repo: BatchRepository
    job_repo: UrlJobRepository
    download_repo: DownloadRepository
    run_repo: RunRepository
    account: Account


class FakeUrlJobProcessor:
    def __init__(
        self,
        job_repo: UrlJobRepository,
        outcomes: dict[int, list[UrlJobStatus]],
    ) -> None:
        self.job_repo = job_repo
        self.outcomes = outcomes
        self.calls: list[int] = []

    async def process(self, url_job_id: int) -> UrlJobProcessorResult:
        self.calls.append(url_job_id)
        statuses = self.outcomes[url_job_id]
        status = statuses.pop(0)
        if status is UrlJobStatus.RETRY_PENDING:
            job = self.job_repo.update_error(
                url_job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error="temporary",
                last_error_type="TEMPORARY",
                non_retryable=False,
            )
        elif status is UrlJobStatus.FAILED_FINAL:
            job = self.job_repo.update_error(
                url_job_id,
                status=UrlJobStatus.FAILED_FINAL,
                last_error="final",
                last_error_type="FINAL",
                non_retryable=True,
            )
        else:
            job = self.job_repo.update_status(url_job_id, status)
        return UrlJobProcessorResult(job=job)


def test_account_orchestrator_processes_generated_story_before_manual_urls(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    manual = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    story = _create_job(stored.job_repo, stored.account.id, UrlSource.GENERATED_STORY)
    processor = FakeUrlJobProcessor(
        stored.job_repo,
        {
            manual.id: [UrlJobStatus.COMPLETED],
            story.id: [UrlJobStatus.COMPLETED],
        },
    )
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
    )

    result = asyncio.run(orchestrator.process_account(stored.account.id))

    assert processor.calls == [story.id, manual.id]
    assert result.account.status is AccountStatus.COMPLETED
    assert result.summary.status is RunStatus.COMPLETED
    assert (tmp_path / "working" / "example_user" / "story").is_dir()
    assert stored.job_repo.get_by_id(story.id).run_id == result.run.id
    assert stored.job_repo.get_by_id(manual.id).run_id == result.run.id


def test_account_orchestrator_retries_temporary_failures_fifo(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    first = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    second = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    processor = FakeUrlJobProcessor(
        stored.job_repo,
        {
            first.id: [
                UrlJobStatus.RETRY_PENDING,
                UrlJobStatus.RETRY_PENDING,
                UrlJobStatus.COMPLETED,
            ],
            second.id: [UrlJobStatus.RETRY_PENDING, UrlJobStatus.COMPLETED],
        },
    )
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
        config=AccountOrchestratorConfig(max_retries=5),
    )

    result = asyncio.run(orchestrator.process_account(stored.account.id))

    assert processor.calls == [first.id, second.id, first.id, second.id, first.id]
    assert result.account.status is AccountStatus.COMPLETED
    assert result.summary.completed_urls == 2
    assert stored.job_repo.get_by_id(first.id).retries == 1
    assert stored.job_repo.get_by_id(second.id).retries == 0


def test_account_orchestrator_reports_item_progress_including_story_and_retries(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    manual = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    story = _create_job(stored.job_repo, stored.account.id, UrlSource.GENERATED_STORY)
    processor = FakeUrlJobProcessor(
        stored.job_repo,
        {
            manual.id: [UrlJobStatus.COMPLETED],
            story.id: [UrlJobStatus.RETRY_PENDING, UrlJobStatus.COMPLETED],
        },
    )
    progress: list[tuple[int, int, int, bool]] = []
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
        config=AccountOrchestratorConfig(
            item_progress_callback=lambda current, total, _account, job, retry: (
                progress.append((current, total, job.id, retry))
            )
        ),
    )

    asyncio.run(orchestrator.process_account(stored.account.id))

    assert progress == [
        (1, 2, story.id, False),
        (2, 2, manual.id, False),
        (2, 2, story.id, True),
    ]


def test_account_orchestrator_retries_interrupted_waiting_download_job(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    interrupted = _create_job(
        stored.job_repo,
        stored.account.id,
        UrlSource.INPUT_URL,
        status=UrlJobStatus.WAITING_DOWNLOAD,
    )
    processor = FakeUrlJobProcessor(
        stored.job_repo,
        {interrupted.id: [UrlJobStatus.COMPLETED]},
    )
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
        config=AccountOrchestratorConfig(max_retries=5),
    )

    result = asyncio.run(orchestrator.process_account(stored.account.id))

    assert processor.calls == [interrupted.id]
    assert result.account.status is AccountStatus.COMPLETED
    assert stored.job_repo.get_by_id(interrupted.id).status is UrlJobStatus.COMPLETED


def test_account_orchestrator_marks_partial_when_some_urls_fail_final(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    completed = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    failed = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    processor = FakeUrlJobProcessor(
        stored.job_repo,
        {
            completed.id: [UrlJobStatus.COMPLETED],
            failed.id: [UrlJobStatus.FAILED_FINAL],
        },
    )
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
    )

    result = asyncio.run(orchestrator.process_account(stored.account.id))

    assert result.account.status is AccountStatus.PARTIAL
    assert result.summary.status is RunStatus.PARTIAL
    assert result.summary.completed_urls == 1
    assert result.summary.failed_urls == 1


def test_account_orchestrator_marks_failed_on_infrastructure_error(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path, with_working_folder=False)
    _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    processor = FakeUrlJobProcessor(stored.job_repo, {})
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
    )

    result = asyncio.run(orchestrator.process_account(stored.account.id))

    assert result.account.status is AccountStatus.FAILED
    assert result.summary.status is RunStatus.FAILED
    assert result.error == "No working folder is configured for the account"


def test_account_orchestrator_dry_run_does_not_process_urls_or_create_folders(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    _create_job(stored.job_repo, stored.account.id, UrlSource.GENERATED_STORY)
    _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    processor = FakeUrlJobProcessor(stored.job_repo, {})
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
        config=AccountOrchestratorConfig(dry_run=True),
    )

    result = asyncio.run(orchestrator.process_account(stored.account.id))

    assert processor.calls == []
    assert result.account.status is AccountStatus.PENDING
    assert result.summary.status is RunStatus.COMPLETED
    assert result.summary.total_urls == 2
    assert result.summary.completed_urls == 0
    assert "Dry-run account example_user" in result.summary.summary
    assert not (tmp_path / "working" / "example_user").exists()
    assert all(
        job.status is UrlJobStatus.PENDING
        for job in stored.job_repo.list_by_account(stored.account.id)
    )


def test_account_orchestrator_uses_execution_start_for_log_folder(
    tmp_path: Path,
) -> None:
    stored = _stored_account(tmp_path)
    job = _create_job(stored.job_repo, stored.account.id, UrlSource.INPUT_URL)
    processor = FakeUrlJobProcessor(
        stored.job_repo,
        {job.id: [UrlJobStatus.COMPLETED]},
    )
    execution_started_at = datetime(
        2026,
        6,
        21,
        11,
        15,
        19,
        tzinfo=timezone.utc,
    )
    orchestrator = AccountOrchestrator(
        account_repository=stored.account_repo,
        url_job_repository=stored.job_repo,
        download_repository=stored.download_repo,
        run_repository=stored.run_repo,
        url_job_processor=processor,
        config=AccountOrchestratorConfig(
            logs_folder=tmp_path / "logs",
            execution_started_at=execution_started_at,
        ),
    )

    asyncio.run(orchestrator.process_account(stored.account.id))

    assert (
        tmp_path / "logs" / "20260621_111519" / "example_user.log"
    ).is_file()


def _stored_account(
    tmp_path: Path,
    *,
    with_working_folder: bool = True,
) -> StoredAccount:
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
    account_repo = AccountRepository(connection)
    account = account_repo.create(
        Account(
            batch_id=batch.id,
            username="example_user",
            start_now_date=date(2026, 6, 14),
            download_stories=True,
            working_folder=tmp_path / "working" / "example_user"
            if with_working_folder
            else None,
            status=AccountStatus.PENDING,
        )
    )
    return StoredAccount(
        connection=connection,
        account_repo=account_repo,
        batch_repo=batch_repo,
        job_repo=UrlJobRepository(connection),
        download_repo=DownloadRepository(connection),
        run_repo=RunRepository(connection),
        account=account,
    )


def _create_job(
    job_repo: UrlJobRepository,
    account_id: int,
    source: UrlSource,
    *,
    status: UrlJobStatus = UrlJobStatus.PENDING,
) -> UrlJob:
    return job_repo.create(
        UrlJob(
            account_id=account_id,
            url=(
                "https://www.instagram.com/stories/example_user/"
                if source is UrlSource.GENERATED_STORY
                else "https://www.instagram.com/reel/ABC123xyz/"
            ),
            publication_type=(
                PublicationType.STORY
                if source is UrlSource.GENERATED_STORY
                else PublicationType.REEL
            ),
            source=source,
            status=status,
            max_retries=5,
        )
    )
