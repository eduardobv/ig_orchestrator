"""Pause between URLs and the unresponsive-bot guard (feat-run-39)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.db import DownloadRepository, UrlJobRepository
from ig_orchestrator.models import UrlJob, UrlJobStatus
from ig_orchestrator.telegram import BotConversationConfig, BotConversationService
from ig_orchestrator.telegram.bot_conversation_service import FirstResponseTimeouts

from tests.telegram.test_bot_conversation_service import (  # type: ignore
    _connection,
    _document,
    _stored_job,
)

REEL_A = "https://www.instagram.com/reel/AAAAAAAAAAA/"
REEL_B = "https://www.instagram.com/reel/BBBBBBBBBBB/"


class Reply:
    def __init__(self, reply_to_msg_id: int) -> None:
        self.reply_to_msg_id = reply_to_msg_id


@dataclass
class Msg:
    id: int
    text: str = ""
    date: datetime = field(
        default_factory=lambda: datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    )
    out: bool = False
    media: object | None = None
    document: object | None = None
    photo: object | None = None
    grouped_id: int | None = None
    reply_to: object | None = None


def video(msg_id: int, name: str, reply_to: int | None) -> Msg:
    document = _document(name, "video/mp4")
    document.size = 100  # type: ignore[attr-defined]
    return Msg(
        msg_id,
        media=object(),
        document=document,
        reply_to=None if reply_to is None else Reply(reply_to),
    )


def caption(msg_id: int, reply_to: int | None) -> Msg:
    return Msg(
        msg_id,
        text="description of the reel",
        reply_to=None if reply_to is None else Reply(reply_to),
    )


class StallClient:
    """Bot that answers each send after a scripted delay (or never).

    ``answers`` maps the 0-based number of the send to (delay, messages); a
    delay counts from the moment of that send. ``wake_at`` instead delivers the
    messages at an absolute time since the first send (a bot that was frozen).
    """

    def __init__(self) -> None:
        self.sent: list[tuple[float, str]] = []
        self.history: list[Msg] = []
        self.answers: dict[int, tuple[float, list[Msg]]] = {}
        self.wake_at: tuple[float, list[Msg]] | None = None
        self._queue: asyncio.Queue[Msg] = asyncio.Queue()
        self._t0: float | None = None
        self.downloaded: list[int] = []

    def subscribe_bot_messages(self) -> "StallClient":
        self._queue = asyncio.Queue()
        return self

    def _deliver(self, messages: list[Msg]) -> None:
        for message in messages:
            self.history.append(message)
            self._queue.put_nowait(message)

    async def send_message_to_bot(self, text: str) -> Msg:
        loop = asyncio.get_running_loop()
        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
            if self.wake_at is not None:
                loop.call_later(self.wake_at[0], self._deliver, self.wake_at[1])
        index = len(self.sent)
        self.sent.append((now, text))
        if index in self.answers:
            delay, messages = self.answers[index]
            loop.call_later(delay, self._deliver, messages)
        return Msg(100 + index, text=text, out=True)

    async def get(self, timeout: float) -> Msg | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def get_nowait(self) -> Msg | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def close(self) -> None:
        pass

    async def get_bot_messages_after(self, timestamp, *, limit=100):
        return list(self.history)[-limit:]

    async def download_message_media(self, message, destination):
        self.downloaded.append(message.id)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"media-{message.id}".encode("ascii"))
        return str(path)


def _build(tmp_path: Path, client: StallClient, **config):
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    folder = tmp_path / "downloads"
    folder.mkdir(exist_ok=True)
    statuses: list[str] = []
    defaults = dict(
        download_folder=folder,
        download_wait_timeout_seconds=2,
        download_stable_seconds=5,
        response_wait_timeout_seconds=2,
        completion_mode="EXPECTED_COUNT",
        grace_seconds=0.2,
        album_settle_seconds=0.1,
        response_fallback_poll_seconds=0.2,
        first_response_timeouts=FirstResponseTimeouts(0.3, 0.3, 0.3, 0.3),
    )
    defaults.update(config)
    service = BotConversationService(
        telegram_client=client,
        url_job_repository=job_repo,
        download_repository=DownloadRepository(connection),
        config=BotConversationConfig(**defaults),
        watcher=lambda *_a: [],
        status_callback=statuses.append,
    )
    first = _stored_job(job_repo, url=REEL_A)
    second = job_repo.create(
        UrlJob(
            account_id=first.account_id,
            url=REEL_B,
            publication_type=first.publication_type,
            source=first.source,
            status=UrlJobStatus.PENDING,
            max_retries=5,
        )
    )
    return service, job_repo, first, second, statuses


def test_pause_between_urls_spaces_the_sends(tmp_path: Path) -> None:
    client = StallClient()
    client.answers = {
        0: (0.02, [video(200, "a.mp4", 100), caption(201, 100)]),
        1: (0.02, [video(210, "b.mp4", 101), caption(211, 101)]),
    }
    service, _repo, first, second, _ = _build(tmp_path, client, between_urls_seconds=0.6)

    async def run():
        await service.process_url_job(first)
        return await service.process_url_job(second)

    result = asyncio.run(run())

    assert result.job.status is UrlJobStatus.DOWNLOADED
    assert client.sent[1][0] - client.sent[0][0] >= 0.6


def test_no_pause_before_the_first_url(tmp_path: Path) -> None:
    client = StallClient()
    client.answers = {0: (0.02, [video(200, "a.mp4", 100), caption(201, 100)])}
    service, _repo, first, _second, _ = _build(tmp_path, client, between_urls_seconds=30)

    started = time.monotonic()
    asyncio.run(service.process_url_job(first))

    assert time.monotonic() - started < 5


def test_silent_url_followed_by_an_answered_one_does_not_wait(tmp_path: Path) -> None:
    client = StallClient()
    client.answers = {1: (0.02, [video(210, "b.mp4", 101), caption(211, 101)])}
    service, repo, first, second, statuses = _build(
        tmp_path, client, stall_guard_enabled=True, stall_probe_delay_seconds=0.5
    )

    async def run():
        silent = await service.process_url_job(first)
        flag = service.has_unanswered
        answered = await service.process_url_job(second)
        return silent, flag, answered

    silent, flagged, answered = asyncio.run(run())

    assert silent.job.last_error_type == "NO_BOT_RESPONSE"
    assert flagged is True
    assert answered.job.status is UrlJobStatus.DOWNLOADED
    assert answered.late_results == ()
    assert service.has_unanswered is False
    assert statuses == []  # never entered wait mode
    assert client.sent[1][0] - client.sent[0][0] >= 0.5 + 0.3 - 0.05  # timeout + probe delay
    assert repo.get_by_id(first.id).status is UrlJobStatus.RETRY_PENDING


def test_two_silent_urls_wait_for_the_bot_and_collect_both_answers_out_of_order(
    tmp_path: Path,
) -> None:
    client = StallClient()
    # The frozen bot wakes up ~1.5 s after the first send and answers the
    # second URL before the first one.
    client.wake_at = (
        1.5,
        [
            video(300, "b.mp4", 101),
            caption(301, 101),
            video(302, "a.mp4", 100),
            caption(303, 100),
        ],
    )
    service, repo, first, second, statuses = _build(
        tmp_path, client, stall_guard_enabled=True, stall_probe_delay_seconds=0.2
    )

    async def run():
        await service.process_url_job(first)
        return await service.process_url_job(second)

    result = asyncio.run(run())

    assert len(client.sent) == 2  # nothing was sent while the bot was frozen
    assert statuses == ["STALLED", "RESUMED"]
    assert result.job.status is UrlJobStatus.DOWNLOADED
    assert [f.original_path.name for f in result.files] == ["b.mp4"]
    assert len(result.late_results) == 1
    late = result.late_results[0]
    assert late.job.id == first.id and late.job.status is UrlJobStatus.DOWNLOADED
    assert [f.original_path.name for f in late.files] == ["a.mp4"]
    assert service.has_unanswered is False
    assert repo.get_by_id(second.id).status is UrlJobStatus.DOWNLOADED


def test_two_silent_attempts_of_the_same_url_collect_one_answer(tmp_path: Path) -> None:
    client = StallClient()
    client.wake_at = (1.2, [video(300, "a.mp4", 101), caption(301, 101)])
    service, _repo, first, _second, statuses = _build(
        tmp_path, client, stall_guard_enabled=True, stall_probe_delay_seconds=0.2
    )

    async def run():
        await service.process_url_job(first)
        return await service.process_url_job(first)

    result = asyncio.run(run())

    assert statuses == ["STALLED", "RESUMED"]
    assert result.job.status is UrlJobStatus.DOWNLOADED
    assert result.late_results == ()
    assert [f.original_path.name for f in result.files] == ["a.mp4"]


def test_only_the_second_url_is_answered_after_the_stall(tmp_path: Path) -> None:
    client = StallClient()
    client.wake_at = (1.2, [video(300, "b.mp4", 101), caption(301, 101)])
    service, repo, first, second, _ = _build(
        tmp_path, client, stall_guard_enabled=True, stall_probe_delay_seconds=0.2
    )

    async def run():
        await service.process_url_job(first)
        return await service.process_url_job(second)

    result = asyncio.run(run())

    assert result.job.status is UrlJobStatus.DOWNLOADED
    assert result.late_results == ()
    # The first URL stays pending retry; it will be sent again later.
    assert repo.get_by_id(first.id).status is UrlJobStatus.RETRY_PENDING


def test_guard_is_off_by_default(tmp_path: Path) -> None:
    client = StallClient()
    service, _repo, first, second, statuses = _build(tmp_path, client)

    async def run():
        await service.process_url_job(first)
        return await service.process_url_job(second)

    result = asyncio.run(run())

    assert result.job.last_error_type == "NO_BOT_RESPONSE"
    assert statuses == []
    assert service.has_unanswered is False
