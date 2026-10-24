from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

Clock = Callable[[], float]

TEXT_CLASS_DESCRIPTION = "DESCRIPTION"
TEXT_CLASS_ERROR = "ERROR"
TEXT_CLASS_LARGE_FILE_LINK = "LARGE_FILE_LINK"
TEXT_CLASS_UNKNOWN = "UNKNOWN"

# Why the wait for the bot ended.
EXIT_ERROR_TEXT = "ERROR_TEXT"
EXIT_LARGE_FILE_LINK = "LARGE_FILE_LINK"
EXIT_STABLE = "STABLE"
EXIT_DEADLINE_FIRST = "DEADLINE_FIRST"
EXIT_DEADLINE_TOTAL = "DEADLINE_TOTAL"
EXIT_SEND_FAILED = "SEND_FAILED"


@dataclass(slots=True)
class MessageEvent:
    """One bot message seen during an attempt (no text is stored)."""

    message_id: int | None
    grouped_id: int | None
    offset_ms: int
    kind: str
    mime: str | None
    has_filename: bool
    size_bytes: int | None
    text_class: str | None = None
    text_len: int | None = None
    download_ms: int | None = None


@dataclass(slots=True)
class WaitEvent:
    kind: str
    ms: int
    at: str


@dataclass(slots=True)
class AttemptTrace:
    """In-memory timings of one URL attempt, flushed once when it ends.

    Offsets are milliseconds on a monotonic clock; ``t_first_*`` and later
    fields count from the moment the URL was sent to the bot.
    """

    url_job_id: int
    account_id: int | None = None
    batch_id: int | None = None
    batch_run_id: int | None = None
    attempt_no: int = 1
    publication_type: str | None = None
    started_at: str = ""
    clock: Clock = field(default=time.monotonic, repr=False)

    t_send_ms: int | None = None
    t_first_response_ms: int | None = None
    t_first_media_ms: int | None = None
    t_last_media_ms: int | None = None
    t_description_ms: int | None = None
    t_end_wait_ms: int | None = None
    t_download_ms: int | None = None
    t_move_ms: int | None = None
    t_total_ms: int | None = None
    flood_wait_ms: int = 0
    exit_reason: str | None = None
    outcome: str | None = None
    error_code: str | None = None
    messages_count: int = 0
    media_count: int = 0
    files_count: int = 0
    bytes_downloaded: int = 0
    duplicates_skipped: int = 0
    aes_backend: str | None = None
    settings: dict[str, object] = field(default_factory=dict)
    events: list[MessageEvent] = field(default_factory=list)
    waits: list[WaitEvent] = field(default_factory=list)

    _t0: float = field(default=0.0, repr=False)
    _sent_at: float | None = field(default=None, repr=False)
    _last_message_at: float | None = field(default=None, repr=False)

    @classmethod
    def start(
        cls,
        *,
        url_job_id: int,
        account_id: int | None,
        batch_run_id: int | None,
        attempt_no: int,
        publication_type: str | None,
        clock: Clock = time.monotonic,
    ) -> AttemptTrace:
        trace = cls(
            url_job_id=url_job_id,
            account_id=account_id,
            batch_run_id=batch_run_id,
            attempt_no=attempt_no,
            publication_type=publication_type,
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            clock=clock,
        )
        trace._t0 = clock()
        return trace

    # -- recording -------------------------------------------------------
    def mark_sent(self) -> None:
        now = self.clock()
        self._sent_at = now
        self.t_send_ms = _ms(now - self._t0)

    def _since_sent(self) -> int:
        base = self._sent_at if self._sent_at is not None else self._t0
        return _ms(self.clock() - base)

    def on_message(
        self,
        *,
        message_id: int | None,
        grouped_id: int | None,
        kind: str,
        mime: str | None = None,
        has_filename: bool = False,
        size_bytes: int | None = None,
        text_class: str | None = None,
        text_len: int | None = None,
    ) -> None:
        offset = self._since_sent()
        self._last_message_at = self.clock()
        self.messages_count += 1
        if self.t_first_response_ms is None:
            self.t_first_response_ms = offset
        if kind != "TEXT":
            self.media_count += 1
            if self.t_first_media_ms is None:
                self.t_first_media_ms = offset
            self.t_last_media_ms = offset
        elif text_class == TEXT_CLASS_DESCRIPTION and self.t_description_ms is None:
            self.t_description_ms = offset
        self.events.append(
            MessageEvent(
                message_id=message_id,
                grouped_id=grouped_id,
                offset_ms=offset,
                kind=kind,
                mime=mime,
                has_filename=has_filename,
                size_bytes=size_bytes,
                text_class=text_class,
                text_len=text_len,
            )
        )

    def on_download(self, message_id: int | None, ms: int, size_bytes: int | None) -> None:
        if size_bytes:
            self.bytes_downloaded += size_bytes
        for event in reversed(self.events):
            if event.message_id == message_id and event.download_ms is None:
                event.download_ms = ms
                break

    def on_wait(self, kind: str, ms: int) -> None:
        self.waits.append(
            WaitEvent(
                kind=kind,
                ms=ms,
                at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        )
        if kind == "FLOOD_WAIT":
            self.flood_wait_ms += ms

    def end_wait(self, exit_reason: str) -> None:
        """Close the wait for the bot, recording how long it idled at the end."""

        self.exit_reason = exit_reason
        if self._last_message_at is not None:
            self.t_end_wait_ms = _ms(self.clock() - self._last_message_at)

    def finish(self, *, outcome: str, error_code: str | None) -> None:
        self.outcome = outcome
        self.error_code = error_code
        self.t_total_ms = _ms(self.clock() - self._t0)


def album_size_bucket(media_count: int) -> str:
    if media_count <= 1:
        return "1"
    if media_count <= 4:
        return "2-4"
    if media_count <= 10:
        return "5-10"
    return "11+"


def _ms(seconds: float) -> int:
    return max(int(round(seconds * 1000)), 0)


__all__ = [
    "AttemptTrace",
    "MessageEvent",
    "WaitEvent",
    "album_size_bucket",
]
