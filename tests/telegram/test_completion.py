"""End-of-conversation rules (count / description / grace) with the real bot
message sequences measured on 2026-10-24 (see tasks/feat-run-30.md §3.1)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.db import DownloadRepository, UrlJobRepository
from ig_orchestrator.telegram import BotConversationConfig, BotConversationService
from ig_orchestrator.telegram.bot_conversation_service import FirstResponseTimeouts

from tests.telegram.test_bot_conversation_service import (  # type: ignore
    EventTelegramClient,
    _connection,
    _document,
    _stored_job,
)


@dataclass
class Msg:
    id: int
    text: str = ""
    date: datetime = field(
        default_factory=lambda: datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    )
    out: bool = False
    media: object | None = None
    document: object | None = None
    photo: object | None = None
    grouped_id: int | None = None


def _doc(name: str, size: int = 100, mime: str = "image/jpeg") -> object:
    document = _document(name, mime)
    document.size = size  # type: ignore[attr-defined]
    return document


def doc_msg(i: int, name: str, *, group: int | None = None, mime: str = "image/jpeg") -> Msg:
    return Msg(i, media=object(), document=_doc(name, mime=mime), grouped_id=group)


def photo_msg(i: int, *, group: int | None = None) -> Msg:
    return Msg(i, media=object(), photo=object(), grouped_id=group)


def text_msg(i: int, text: str = "caption of the post") -> Msg:
    return Msg(i, text=text)


class ScriptedClient(EventTelegramClient):
    """Delivers (delay_seconds, message) pairs through the event queue."""

    def __init__(self, script: list[tuple[float, Msg]]) -> None:
        super().__init__([])
        self.script = script
        self.enable_direct_download = True
        self.downloaded: list[int] = []
        self._tasks: list[asyncio.Task] = []

    async def send_message_to_bot(self, text: str):
        sent = await super().send_message_to_bot(text)
        loop = asyncio.get_running_loop()
        for delay, message in self.script:
            loop.call_later(delay, self._queue.put_nowait, message)
        return sent

    async def download_message_media(self, message, destination):
        self.downloaded.append(message.id)
        return await super().download_message_media(message, destination)


def _run(tmp_path: Path, script, *, url="https://www.instagram.com/reel/ABC123xyz/",
         pub=None, **config):
    connection = _connection(tmp_path)
    job_repo = UrlJobRepository(connection)
    folder = tmp_path / "downloads"
    folder.mkdir(exist_ok=True)
    client = ScriptedClient(script)
    defaults = dict(
        download_folder=folder,
        download_wait_timeout_seconds=3,
        download_stable_seconds=5,
        response_wait_timeout_seconds=3,
        completion_mode="EXPECTED_COUNT",
        grace_seconds=0.3,
        album_settle_seconds=0.15,
        first_response_timeouts=FirstResponseTimeouts(2, 2, 2, 2),
    )
    defaults.update(config)
    service = BotConversationService(
        telegram_client=client,
        url_job_repository=job_repo,
        download_repository=DownloadRepository(connection),
        config=BotConversationConfig(**defaults),
        watcher=lambda *_a: [],
    )
    job = _stored_job(job_repo, url=url)
    started = time.monotonic()
    result = asyncio.run(service.process_url_job(job))
    return result, client, time.monotonic() - started


def test_reel_with_duplicate_attachment_ends_by_count_not_by_silence(tmp_path: Path) -> None:
    script = [
        (0.02, doc_msg(101, "4014272112143137696.mp4", mime="video/mp4")),
        (0.03, doc_msg(102, "4014272112143137696.mp4", mime="video/mp4")),
        (0.06, text_msg(103)),
    ]

    result, client, elapsed = _run(tmp_path, script)

    assert result.trace.exit_reason == "COUNT_REACHED"
    assert result.trace.expected_items == 1
    assert [f.original_path.name for f in result.files] == ["4014272112143137696.mp4"]
    assert client.downloaded == [101]
    assert elapsed < 1.5  # the legacy rule would have waited download_stable_seconds=5


def test_single_photo_post_counts_thumbnail_as_the_item(tmp_path: Path) -> None:
    script = [
        (0.02, photo_msg(101)),
        (0.04, doc_msg(102, "3918738646186472213.jpg")),
    ]

    result, client, _ = _run(tmp_path, script, url="https://www.instagram.com/p/ABC123xyz/")

    assert result.trace.exit_reason == "COUNT_REACHED"
    assert client.downloaded == [102]  # the unnamed thumbnail is never fetched
    assert [f.original_path.name for f in result.files] == ["3918738646186472213.jpg"]


def test_carousel_of_twelve_with_two_albums_waits_for_every_original(tmp_path: Path) -> None:
    names = [f"39000000000000{i:04d}.jpg" for i in range(12)]
    script = [(0.02, photo_msg(100 + i, group=1)) for i in range(10)]
    script += [(0.05, photo_msg(120 + i, group=2)) for i in range(2)]
    script += [(0.08 + 0.01 * i, doc_msg(200 + i, n)) for i, n in enumerate(names)]
    script += [(0.3, text_msg(300))]

    result, client, _ = _run(tmp_path, script, url="https://www.instagram.com/p/X/?img_index=1")

    assert result.trace.expected_items == 12
    assert result.trace.exit_reason == "COUNT_REACHED"
    assert sorted(f.original_path.name for f in result.files) == sorted(names)
    assert not any(i < 200 for i in client.downloaded)


def test_carousel_of_twenty_with_repeated_videos_counts_unique_names(tmp_path: Path) -> None:
    photos = [f"photo{i:02d}.jpg" for i in range(16)]
    videos = [f"video{i}.mp4" for i in range(4)]
    script = [(0.02, photo_msg(100 + i, group=1)) for i in range(6)]
    script += [(0.02, doc_msg(110 + i, v, group=1, mime="video/mp4")) for i, v in enumerate(videos)]
    script += [(0.03, photo_msg(120 + i, group=2)) for i in range(10)]
    script += [(0.2 + 0.005 * i, doc_msg(200 + i, n)) for i, n in enumerate(photos)]
    script += [(0.3 + 0.005 * i, doc_msg(300 + i, v, mime="video/mp4")) for i, v in enumerate(videos)]
    script += [(0.5, text_msg(400))]

    result, _, _ = _run(tmp_path, script, url="https://www.instagram.com/p/X/?img_index=1")

    assert result.trace.expected_items == 20
    assert result.trace.exit_reason == "COUNT_REACHED"
    assert len(result.files) == 20
    # the 4 video attachments are already known from the albums: no re-download
    assert len(set(f.original_path.name for f in result.files)) == 20


def test_highlights_end_after_the_last_album_settles(tmp_path: Path) -> None:
    script = [(0.02, doc_msg(100 + i, f"hl{i:02d}.mp4", group=1, mime="video/mp4")) for i in range(10)]
    script += [(0.06, doc_msg(120 + i, f"hl{10 + i:02d}.mp4", group=2, mime="video/mp4")) for i in range(6)]

    result, _, elapsed = _run(
        tmp_path, script, url="https://www.instagram.com/stories/highlights/1789/"
    )

    assert result.trace.exit_reason == "COUNT_REACHED"
    assert len(result.files) == 16
    assert elapsed < 1.5


def test_story_album_of_unnamed_photos_ends_by_grace_and_uses_previews(tmp_path: Path) -> None:
    script = [(0.02, photo_msg(100 + i, group=1)) for i in range(3)]

    result, client, elapsed = _run(
        tmp_path, script, url="https://www.instagram.com/stories/someone/"
    )

    assert result.trace.exit_reason == "GRACE"
    assert len(result.files) == 3 and len(client.downloaded) == 3
    assert elapsed < 1.5


def test_description_ends_the_wait_when_an_attachment_is_missing(tmp_path: Path) -> None:
    script = [(0.02, photo_msg(100 + i, group=1)) for i in range(3)]
    script += [(0.05, doc_msg(200, "a.jpg")), (0.06, doc_msg(201, "b.jpg")), (0.2, text_msg(300))]

    result, _, _ = _run(tmp_path, script, url="https://www.instagram.com/p/X/?img_index=1")

    assert result.trace.exit_reason == "DESCRIPTION"
    assert len(result.files) == 2


def test_first_response_timeout_depends_on_the_kind_of_url(tmp_path: Path) -> None:
    script = [(0.4, doc_msg(101, "late.mp4", mime="video/mp4"))]
    timeouts = FirstResponseTimeouts(default=0.15, story=0.15, carousel=1.0, highlights=1.0)

    reel, _, _ = _run(
        tmp_path / "a", script, first_response_timeouts=timeouts
    ) if (tmp_path / "a").mkdir() is None else (None, None, None)
    carousel, _, _ = _run(
        tmp_path / "b", script, url="https://www.instagram.com/p/X/?img_index=2",
        first_response_timeouts=timeouts,
    ) if (tmp_path / "b").mkdir() is None else (None, None, None)

    assert reel.job.last_error_type == "NO_BOT_RESPONSE"
    assert reel.trace.exit_reason == "DEADLINE_FIRST"
    assert carousel.trace.exit_reason == "COUNT_REACHED"
    assert len(carousel.files) == 1


def test_every_bot_message_renews_the_total_timeout(tmp_path: Path) -> None:
    # Four texts 0.2 s apart outlive the 0.3 s timeout only if each one renews it.
    script = [(0.1 * (i + 1) * 2, text_msg(100 + i, "still working")) for i in range(4)]
    script += [(1.0, doc_msg(200, "late.mp4", mime="video/mp4"))]

    result, _, _ = _run(
        tmp_path, script, download_wait_timeout_seconds=0.3, grace_seconds=5
    )

    assert result.trace.exit_reason == "COUNT_REACHED"
    assert len(result.files) == 1


def test_late_messages_of_the_previous_url_are_not_taken_as_a_response(tmp_path: Path) -> None:
    # FakeTelegramClient sends with id 99: anything below it predates this URL.
    script = [(0.02, doc_msg(50, "previous-url-late-duplicate.mp4", mime="video/mp4")),
              (0.04, text_msg(51, "description of the previous post"))]

    result, client, _ = _run(
        tmp_path, script, first_response_timeouts=FirstResponseTimeouts(0.3, 0.3, 0.3, 0.3)
    )

    assert result.job.last_error_type == "NO_BOT_RESPONSE"
    assert client.downloaded == []
