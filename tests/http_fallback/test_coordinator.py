from __future__ import annotations

import asyncio
import dataclasses
from datetime import date, datetime
from pathlib import Path

import pytest

from ig_orchestrator.http_fallback.client import (
    KIND_NOT_FOUND,
    KIND_RATE_LIMIT,
    KIND_SESSION,
    SESSION_ADVICE,
    HttpFallbackError,
    MediaFile,
)
from ig_orchestrator.http_fallback.config import HttpFallbackConfig
from ig_orchestrator.http_fallback.coordinator import HttpFallbackCoordinator
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration.url_job_processor import UrlJobProcessorResult

NOON = datetime(2026, 1, 1, 12, 0)
THREE_AM = datetime(2026, 1, 1, 3, 0)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class Jobs:
    def __init__(self, jobs: list[UrlJob]) -> None:
        self.jobs = {job.id: job for job in jobs}

    def get_by_id(self, job_id):
        return self.jobs.get(job_id)

    def list_by_account(self, account_id):
        return [j for j in self.jobs.values() if j.account_id == account_id]

    def update_error(self, job_id, *, status, last_error, last_error_type, non_retryable,
                     retries=None, next_retry_at=None):
        job = self.jobs[job_id]
        job.status, job.last_error = status, last_error
        job.last_error_type, job.non_retryable = last_error_type, non_retryable
        return job


class Accounts:
    def __init__(self, accounts: list[Account]) -> None:
        self.accounts = {a.id: a for a in accounts}

    def get_by_id(self, account_id):
        return self.accounts.get(account_id)

    def list_by_batch(self, batch_id):
        return [a for a in self.accounts.values() if a.batch_id == batch_id]

    def update_status(self, account_id, status):
        self.accounts[account_id].status = status
        return self.accounts[account_id]


class Processor:
    """``script`` maps job id -> list of 'silent'/'answer' for bot attempts."""

    def __init__(self, jobs: Jobs, script: dict[int, list[str]] | None = None) -> None:
        self.jobs = jobs
        self.script = script or {}
        self.bot_calls: list[int] = []
        self.http_done: list[int] = []

    async def process(self, job_id):
        self.bot_calls.append(job_id)
        job = self.jobs.jobs[job_id]
        step = (self.script.get(job_id) or ["silent"]).pop(0)
        if step == "answer":
            job.status, job.last_error_type = UrlJobStatus.COMPLETED, None
        return UrlJobProcessorResult(job=job)

    async def process_http(self, job_id, paths):
        self.http_done.append(job_id)
        job = self.jobs.jobs[job_id]
        job.status, job.last_error_type = UrlJobStatus.COMPLETED, None
        return UrlJobProcessorResult(job=job)


class Client:
    def __init__(self, errors: list[HttpFallbackError | None] | None = None) -> None:
        self.errors = errors or []
        self.fetched: list[str] = []

    def fetch_media_files(self, url):
        self.fetched.append(url)
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return [MediaFile(name=f"m{len(self.fetched)}", url="cdn", extension=".jpg")]

    def download(self, media, destination):
        destination.write_bytes(b"x")


def _job(job_id: int, account_id: int = 1, status=UrlJobStatus.RETRY_PENDING,
         error="NO_BOT_RESPONSE", kind=PublicationType.POST) -> UrlJob:
    return UrlJob(
        account_id=account_id,
        url=f"https://www.instagram.com/p/DJryedPJmGk/?n={job_id}",
        publication_type=kind,
        source=UrlSource.INPUT_URL,
        status=status,
        id=job_id,
        last_error_type=error,
    )


def _account(account_id: int = 1, name: str = "alice") -> Account:
    return Account(
        username=name, start_now_date=date(2026, 1, 1), download_stories=False,
        status=AccountStatus.PROCESSING, id=account_id, batch_id=1,
    )


def _config(**overrides) -> HttpFallbackConfig:
    base = HttpFallbackConfig(
        sessionid="S", jitter_percent=0, night_enabled=False, interval_seconds=30,
        retry_delay_seconds=10, botdown_enabled=False,
    )
    return dataclasses.replace(base, **overrides)


def _build(tmp_path: Path, jobs: list[UrlJob], accounts: list[Account], *, config=None,
           script=None, errors=None, probe=None, now=NOON):
    clock = Clock()
    job_repo, account_repo = Jobs(jobs), Accounts(accounts)
    processor = Processor(job_repo, script)
    client = Client(errors)
    messages: list[str] = []
    coordinator = HttpFallbackCoordinator(
        config=config or _config(),
        client=client,
        url_job_repository=job_repo,
        account_repository=account_repo,
        processor=processor,
        download_folder=tmp_path,
        probe=probe,
        status_callback=messages.append,
        clock=clock.monotonic,
        now=lambda: now,
        sleeper=clock.sleep,
    )
    return coordinator, processor, client, clock, messages, job_repo, account_repo


def _attempt(coordinator, job, account):
    return asyncio.run(coordinator.after_attempt(UrlJobProcessorResult(job=job), account))


def test_silent_twice_goes_to_http_and_completes(tmp_path) -> None:
    job, account = _job(1), _account()
    coordinator, processor, client, clock, *_ = _build(tmp_path, [job], [account])

    outcome = _attempt(coordinator, job, account)

    assert processor.bot_calls == [1]  # the second bot attempt
    assert processor.http_done == [1]
    assert outcome.result.job.status is UrlJobStatus.COMPLETED
    assert outcome.park_account is False
    assert clock.sleeps == [10]  # only the retry delay: the first HTTP call does not wait


def test_second_attempt_answered_means_no_http(tmp_path) -> None:
    job, account = _job(1), _account()
    coordinator, processor, client, *_ = _build(
        tmp_path, [job], [account], script={1: ["answer"]}
    )

    outcome = _attempt(coordinator, job, account)

    assert outcome.result.job.status is UrlJobStatus.COMPLETED
    assert client.fetched == [] and processor.http_done == []


def test_account_is_parked_after_three_consecutive_http_downloads(tmp_path) -> None:
    jobs = [_job(i) for i in range(1, 6)]
    account = _account()
    coordinator, processor, client, clock, *_ = _build(tmp_path, jobs, [account])

    parks = []
    for job in jobs:
        outcome = _attempt(coordinator, job, account)
        parks.append(outcome.park_account)
        if outcome.park_account:
            break

    assert parks == [False, False, True]
    assert processor.http_done == [1, 2, 3]
    assert coordinator.is_parked(account.id)
    # 30 s pause between the HTTP requests (10 s of retry delay already elapsed)
    assert clock.sleeps.count(20.0) == 2


def test_a_bot_answer_resets_the_consecutive_counter(tmp_path) -> None:
    jobs = [_job(1), _job(2), _job(3, status=UrlJobStatus.PENDING, error=None), _job(4), _job(5)]
    account = _account()
    coordinator, processor, *_ = _build(
        tmp_path, jobs, [account], script={3: ["answer"]}
    )

    _attempt(coordinator, jobs[0], account)
    _attempt(coordinator, jobs[1], account)
    answered = asyncio.run(processor.process(3))
    _attempt(coordinator, answered.job, account)
    _attempt(coordinator, jobs[3], account)
    outcome = _attempt(coordinator, jobs[4], account)

    assert outcome.park_account is False  # 2 HTTP after the reset, not 4 in a row


def test_night_window_uses_the_long_pause(tmp_path) -> None:
    jobs = [_job(1), _job(2)]
    account = _account()
    config = _config(night_enabled=True, night_interval_seconds=300)
    coordinator, _, _, clock, *_ = _build(tmp_path, jobs, [account], config=config, now=THREE_AM)

    _attempt(coordinator, jobs[0], account)
    _attempt(coordinator, jobs[1], account)

    # two retry delays (10 s each) + the 300 s night pause minus the 10 s already elapsed
    assert sum(clock.sleeps) == pytest.approx(310.0)


def test_session_error_disables_http_with_a_clear_message(tmp_path) -> None:
    jobs = [_job(1), _job(2)]
    account = _account()
    errors = [HttpFallbackError(KIND_SESSION, SESSION_ADVICE, 403)]
    coordinator, processor, client, _, messages, job_repo, _ = _build(
        tmp_path, jobs, [account], errors=errors
    )

    first = _attempt(coordinator, jobs[0], account)
    second = _attempt(coordinator, jobs[1], account)

    assert first.result.job.status is UrlJobStatus.RETRY_PENDING  # legacy retry queue
    assert processor.http_done == []
    assert len(client.fetched) == 1  # never retried after the 403
    assert coordinator.disabled_reason == SESSION_ADVICE
    assert any("caducada" in m and "Probar sesión" in m for m in messages)
    assert second.result.job.status is UrlJobStatus.RETRY_PENDING


def test_repeated_429_disables_http(tmp_path) -> None:
    jobs = [_job(i) for i in range(1, 4)]
    account = _account()
    errors = [HttpFallbackError(KIND_RATE_LIMIT, "429", 429)] * 3
    coordinator, *_ = _build(
        tmp_path, jobs, [account], config=_config(max_429=2, pause_429_minutes=1), errors=errors
    )

    _attempt(coordinator, jobs[0], account)
    assert coordinator.disabled_reason is None
    _attempt(coordinator, jobs[1], account)

    assert coordinator.disabled_reason is not None and "429" in coordinator.disabled_reason


def test_not_found_leaves_the_job_for_the_existing_removed_check(tmp_path) -> None:
    job, account = _job(1), _account()
    errors = [HttpFallbackError(KIND_NOT_FOUND, "nope", 404)]
    coordinator, processor, *_ , job_repo, _ = _build(tmp_path, [job], [account], errors=errors)

    outcome = _attempt(coordinator, job, account)

    assert processor.http_done == []
    assert outcome.result.job.last_error_type == "MEDIA_NOT_FOUND_OR_UNAVAILABLE"
    assert outcome.result.job.status is UrlJobStatus.RETRY_PENDING


def test_http_off_or_no_session_keeps_the_legacy_flow(tmp_path) -> None:
    job, account = _job(1), _account()
    coordinator, processor, client, *_ = _build(
        tmp_path, [job], [account], config=_config(sessionid="")
    )

    outcome = _attempt(coordinator, job, account)

    assert client.fetched == [] and outcome.park_account is False
    assert outcome.result.job.status is UrlJobStatus.RETRY_PENDING


def test_stories_are_never_downloaded_over_http(tmp_path) -> None:
    job, account = _job(1, kind=PublicationType.STORY), _account()
    coordinator, processor, client, *_ = _build(tmp_path, [job], [account])

    outcome = _attempt(coordinator, job, account)

    assert client.fetched == [] and processor.bot_calls == []
    assert outcome.result.job.status is UrlJobStatus.RETRY_PENDING


def test_final_mode_downloads_the_parked_account_and_rechecks_the_bot(tmp_path) -> None:
    jobs = [_job(i, status=UrlJobStatus.PENDING, error=None) for i in range(1, 6)]
    account = _account()
    config = _config(recheck_every=2)
    coordinator, processor, client, *_ = _build(
        tmp_path, jobs, [account], config=config, script={3: ["answer"]}
    )
    coordinator._parked.add(account.id)

    result = asyncio.run(coordinator.run_final_mode(1))

    # jobs 1 and 2 over HTTP, then the bot is asked about job 3 and answers
    assert processor.http_done == [1, 2]
    assert processor.bot_calls == [3]
    assert result == "RECOVERED"
    assert not coordinator.is_parked(account.id)


def test_final_mode_ends_unparking_when_everything_is_downloaded(tmp_path) -> None:
    jobs = [_job(i, status=UrlJobStatus.PENDING, error=None) for i in range(1, 4)]
    account = _account()
    coordinator, processor, *_ = _build(tmp_path, jobs, [account])
    coordinator._parked.add(account.id)

    result = asyncio.run(coordinator.run_final_mode(1))

    assert result == "DONE" and processor.http_done == [1, 2, 3]
    assert coordinator.parked_account_ids() == []


async def _dead_probe() -> bool:
    return False


def test_bot_down_downloads_in_blocks_and_fails_the_accounts_when_it_never_returns(
    tmp_path,
) -> None:
    jobs = [_job(i) for i in range(1, 40)]
    account = _account()
    config = _config(
        botdown_enabled=True, botdown_silences=2, botdown_interval_seconds=120,
        botdown_block_minutes=10, botdown_max_blocks=2, probe_gap_minutes=0, max_per_run=1000,
    )
    coordinator, processor, client, clock, messages, job_repo, accounts = _build(
        tmp_path, jobs, [account], config=config, probe=_dead_probe
    )

    _attempt(coordinator, jobs[0], account)  # streak 1: plain HTTP
    outcome = _attempt(coordinator, jobs[1], account)  # streak 2: probe -> dead

    assert coordinator.aborted and outcome.park_account
    assert accounts.accounts[1].status is AccountStatus.FAILED
    # 2 blocks of 10 min at one URL per 120 s (+ the first one before the probe)
    assert 8 <= len(processor.http_done) <= 14
    assert any("caído" in m for m in messages)


def test_bot_down_returns_to_normal_when_the_probe_answers(tmp_path) -> None:
    jobs = [_job(i) for i in range(1, 30)]
    account = _account()
    answers = iter([False, True])

    async def probe() -> bool:
        return next(answers)

    config = _config(
        botdown_enabled=True, botdown_silences=1, botdown_interval_seconds=120,
        botdown_block_minutes=10, probe_gap_minutes=0,
    )
    coordinator, processor, *_ , accounts = _build(
        tmp_path, jobs, [account], config=config, probe=probe
    )
    _ = accounts

    outcome = _attempt(coordinator, jobs[0], account)

    assert not coordinator.aborted and outcome.park_account is False
    assert len(processor.http_done) >= 4  # one block of HTTP downloads happened


def test_bot_down_without_http_waits_and_then_fails(tmp_path) -> None:
    jobs = [_job(i) for i in range(1, 4)]
    account = _account()
    config = _config(
        enabled=False, botdown_enabled=True, botdown_silences=1, botdown_wait_threshold=0,
        botdown_wait_minutes=60, botdown_wait_attempts=1, probe_gap_minutes=0,
    )
    coordinator, processor, client, clock, messages, _, accounts = _build(
        tmp_path, jobs, [account], config=config, probe=_dead_probe
    )

    _attempt(coordinator, jobs[0], account)

    assert coordinator.aborted
    assert sum(clock.sleeps) >= 3600  # waited the hour once
    assert client.fetched == []
    assert accounts.accounts[1].status is AccountStatus.FAILED


def test_probe_alive_means_the_problem_is_the_urls(tmp_path) -> None:
    jobs = [_job(1), _job(2)]
    account = _account()

    async def alive() -> bool:
        return True

    config = _config(botdown_enabled=True, botdown_silences=1, probe_gap_minutes=0)
    coordinator, processor, *_ = _build(tmp_path, jobs, [account], config=config, probe=alive)

    _attempt(coordinator, jobs[0], account)

    assert not coordinator.aborted
    assert processor.http_done == [1]


@pytest.mark.parametrize("posts,reels,kind,expected", [
    (True, False, PublicationType.REEL, False),
    (False, True, PublicationType.REEL, True),
    (True, True, PublicationType.HIGHLIGHTS, False),
])
def test_applies_follows_the_post_and_reel_switches(tmp_path, posts, reels, kind, expected) -> None:
    coordinator, *_ = _build(tmp_path, [], [], config=_config(posts=posts, reels=reels))

    assert coordinator.applies(_job(1, kind=kind)) is expected
