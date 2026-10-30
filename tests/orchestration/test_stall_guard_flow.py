"""Orchestration side of the unresponsive-bot guard (feat-run-39)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ig_orchestrator.models import AccountStatus, UrlJob, UrlJobStatus
from ig_orchestrator.orchestration import UrlJobProcessor
from ig_orchestrator.telegram import BotConversationResult

from tests.orchestration.test_global_retry_queue import Env, ScriptedProcessor  # type: ignore
from tests.orchestration.test_url_job_processor import (  # type: ignore
    FakeConversationService,
    _download_file,
    _stored_entities,
)


class ProbingProcessor(ScriptedProcessor):
    def __init__(self, job_repo, outcomes, *, stall_pending: bool) -> None:
        super().__init__(job_repo, outcomes)
        self.stall_pending = stall_pending


def _retry_round_waits(tmp_path: Path, *, stall_pending: bool) -> list[float]:
    env = Env(tmp_path, ["a"])
    job = env.job(env.accounts[0])
    processor = ProbingProcessor(
        env.job_repo, {job.id: ["no_response", "ok"]}, stall_pending=stall_pending
    )
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    orchestrator = env.batch_orchestrator(
        env.account_orchestrator(processor, defer_retries=True, retry_base_seconds=60),
        global_retry_queue=True,
        wait_between_retries=True,
        retry_delay_handler=record,
    )

    asyncio.run(orchestrator.process_batch(env.batch.id))

    assert processor.calls == [job.id, job.id]
    return waits


def test_retry_round_waits_the_backoff_when_the_bot_is_fine(tmp_path: Path) -> None:
    waits = _retry_round_waits(tmp_path, stall_pending=False)

    assert len(waits) == 1 and waits[0] > 30


def test_retry_round_skips_the_backoff_while_the_bot_is_being_probed(tmp_path: Path) -> None:
    # The service waits the (short) probe delay itself before re-sending.
    assert _retry_round_waits(tmp_path, stall_pending=True) == []


def test_processor_finishes_the_late_answer_of_an_earlier_url(tmp_path: Path) -> None:
    stored = _stored_entities(tmp_path)
    first = stored.job
    second = stored.job_repo.create(
        UrlJob(
            account_id=first.account_id,
            url="https://www.instagram.com/reel/BBBBBBBBBBB/",
            publication_type=first.publication_type,
            source=first.source,
            status=UrlJobStatus.PENDING,
            max_retries=5,
        )
    )
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "first.mp4").write_bytes(b"first")
    (downloads / "second.mp4").write_bytes(b"second")
    # The first URL went unanswered earlier and was left waiting for a retry.
    stored.job_repo.update_error(
        first.id,
        status=UrlJobStatus.RETRY_PENDING,
        last_error="no response",
        last_error_type="NO_BOT_RESPONSE",
        non_retryable=False,
    )
    stored.account_repo.update_status(stored.account.id, AccountStatus.PARTIAL)
    late_file = stored.download_repo.create(_download_file(first.id, downloads / "first.mp4"))
    late = BotConversationResult(
        job=stored.job_repo.update_status(first.id, UrlJobStatus.DOWNLOADED),
        files=(late_file,),
    )
    own_file = stored.download_repo.create(_download_file(second.id, downloads / "second.mp4"))
    own = BotConversationResult(
        job=stored.job_repo.update_status(second.id, UrlJobStatus.DOWNLOADED),
        files=(own_file,),
        late_results=(late,),
    )
    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=FakeConversationService(own),
    )

    result = asyncio.run(processor.process(second.id))

    reels = tmp_path / "working" / "example_user" / "reels"
    assert result.job.status is UrlJobStatus.COMPLETED
    assert stored.job_repo.get_by_id(first.id).status is UrlJobStatus.COMPLETED
    assert (reels / "first.mp4").read_bytes() == b"first"
    assert (reels / "second.mp4").read_bytes() == b"second"
    # Every URL is done now, so the account no longer waits for a retry.
    assert stored.account_repo.get_by_id(stored.account.id).status is AccountStatus.COMPLETED


def test_processor_reports_whether_the_bot_is_being_probed(tmp_path: Path) -> None:
    stored = _stored_entities(tmp_path)

    class Service(FakeConversationService):
        has_unanswered = True

    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=Service(BotConversationResult(job=stored.job)),
    )

    assert processor.stall_pending is True
