"""Global retry queue (feat-run-35): retries run once, at the end of the batch."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

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
    AccountStatus,
    InputBatch,
    InputBatchStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration import (
    AccountOrchestrator,
    AccountOrchestratorConfig,
    BatchOrchestrator,
    BatchOrchestratorConfig,
    UrlJobProcessorResult,
)
from ig_orchestrator.orchestration.retry_policy import calculate_retry_decision


class ScriptedProcessor:
    """Pops one outcome per call: 'ok', 'retry' or 'no_response'."""

    def __init__(self, job_repo: UrlJobRepository, outcomes: dict[int, list[str]]) -> None:
        self.job_repo = job_repo
        self.outcomes = outcomes
        self.calls: list[int] = []

    async def process(self, url_job_id: int) -> UrlJobProcessorResult:
        self.calls.append(url_job_id)
        outcome = self.outcomes[url_job_id].pop(0)
        if outcome == "ok":
            return UrlJobProcessorResult(
                job=self.job_repo.update_status(url_job_id, UrlJobStatus.COMPLETED)
            )
        error_type = "NO_BOT_RESPONSE" if outcome == "no_response" else "TEMPORARY"
        return UrlJobProcessorResult(
            job=self.job_repo.update_error(
                url_job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error="temporary",
                last_error_type=error_type,
                non_retryable=False,
            )
        )


class Env:
    def __init__(self, tmp_path: Path, usernames: list[str]) -> None:
        db_path = tmp_path / "orchestrator.db"
        init_database(db_path)
        self.connection = connect(db_path)
        self.batch_repo = BatchRepository(self.connection)
        self.account_repo = AccountRepository(self.connection)
        self.job_repo = UrlJobRepository(self.connection)
        self.download_repo = DownloadRepository(self.connection)
        self.run_repo = RunRepository(self.connection)
        self.tmp_path = tmp_path
        self.batch = self.batch_repo.create(
            InputBatch(batch_name="b", schema_version="1.0", status=InputBatchStatus.IMPORTED)
        )
        self.accounts = [
            self.account_repo.create(
                Account(
                    batch_id=self.batch.id,
                    username=name,
                    start_now_date=date(2026, 10, 24),
                    download_stories=False,
                    working_folder=tmp_path / "w" / name,
                    status=AccountStatus.PENDING,
                )
            )
            for name in usernames
        ]

    def job(self, account: Account) -> UrlJob:
        return self.job_repo.create(
            UrlJob(
                account_id=account.id,
                url="https://www.instagram.com/reel/ABC123xyz/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.PENDING,
                max_retries=5,
            )
        )

    def account_orchestrator(self, processor, **config) -> AccountOrchestrator:
        return AccountOrchestrator(
            account_repository=self.account_repo,
            url_job_repository=self.job_repo,
            download_repository=self.download_repo,
            run_repository=self.run_repo,
            url_job_processor=processor,
            config=AccountOrchestratorConfig(max_retries=5, **config),
        )

    def batch_orchestrator(self, account_orchestrator, **config) -> BatchOrchestrator:
        return BatchOrchestrator(
            batch_repository=self.batch_repo,
            account_repository=self.account_repo,
            account_history_repository=AccountHistoryRepository(self.connection),
            url_job_repository=self.job_repo,
            download_repository=self.download_repo,
            run_repository=self.run_repo,
            account_orchestrator=account_orchestrator,
            config=BatchOrchestratorConfig(stories_first=False, **config),
        )


def test_no_response_has_its_own_retry_cap() -> None:
    def decide(error_type: str, cap: int | None):
        return calculate_retry_decision(
            retries=3,
            max_retries=5,
            base_seconds=90,
            max_seconds=900,
            non_retryable=False,
            last_error_type=error_type,
            no_response_max_retries=cap,
        )

    assert decide("NO_BOT_RESPONSE", 3).is_final_failure
    assert not decide("TEMPORARY", 3).is_final_failure
    assert not decide("NO_BOT_RESPONSE", None).is_final_failure


def test_deferred_account_leaves_the_failure_scheduled_instead_of_retrying(tmp_path: Path) -> None:
    env = Env(tmp_path, ["a"])
    job = env.job(env.accounts[0])
    processor = ScriptedProcessor(env.job_repo, {job.id: ["retry", "ok"]})
    orchestrator = env.account_orchestrator(processor, defer_retries=True)

    result = asyncio.run(orchestrator.process_account(env.accounts[0].id))

    stored = env.job_repo.get_by_id(job.id)
    assert processor.calls == [job.id]
    assert stored.status is UrlJobStatus.RETRY_PENDING
    assert stored.next_retry_at is not None
    assert result.account.status is AccountStatus.PARTIAL


def test_batch_retries_every_account_after_all_main_passes(tmp_path: Path) -> None:
    env = Env(tmp_path, ["a", "b"])
    a, b = (env.job(account) for account in env.accounts)
    processor = ScriptedProcessor(env.job_repo, {a.id: ["retry", "ok"], b.id: ["ok"]})
    orchestrator = env.batch_orchestrator(
        env.account_orchestrator(processor, defer_retries=True),
        global_retry_queue=True,
    )

    result = asyncio.run(orchestrator.process_batch(env.batch.id))

    assert processor.calls == [a.id, b.id, a.id]  # B is not blocked by A's failure
    assert env.job_repo.get_by_id(a.id).status is UrlJobStatus.COMPLETED
    assert env.account_repo.get_by_id(env.accounts[0].id).status is AccountStatus.COMPLETED
    assert result.summary.completed_urls == 2


def test_retry_round_orders_by_next_retry_at_and_ends_in_final_failure(tmp_path: Path) -> None:
    env = Env(tmp_path, ["a", "b"])
    a, b = (env.job(account) for account in env.accounts)
    processor = ScriptedProcessor(
        env.job_repo,
        {a.id: ["retry"] + ["retry"] * 10, b.id: ["no_response"] + ["no_response"] * 10},
    )
    orchestrator = env.batch_orchestrator(
        env.account_orchestrator(
            processor, defer_retries=True, no_response_max_retries=2, retry_base_seconds=1,
            retry_max_seconds=1,
        ),
        global_retry_queue=True,
    )

    asyncio.run(orchestrator.process_batch(env.batch.id))

    assert env.job_repo.get_by_id(a.id).status is UrlJobStatus.FAILED_FINAL
    assert env.job_repo.get_by_id(b.id).status is UrlJobStatus.FAILED_FINAL
    # NO_BOT_RESPONSE stops at its own cap (2 retries) well before max_retries=5
    assert processor.calls.count(b.id) == 3
    assert processor.calls.count(a.id) == 6
    assert processor.calls[:2] == [a.id, b.id]  # main pass first, then the round


def test_without_the_queue_the_old_in_place_behaviour_is_kept(tmp_path: Path) -> None:
    env = Env(tmp_path, ["a", "b"])
    a, b = (env.job(account) for account in env.accounts)
    processor = ScriptedProcessor(env.job_repo, {a.id: ["retry", "ok"], b.id: ["ok"]})
    orchestrator = env.batch_orchestrator(env.account_orchestrator(processor))

    asyncio.run(orchestrator.process_batch(env.batch.id))

    assert processor.calls == [a.id, a.id, b.id]
