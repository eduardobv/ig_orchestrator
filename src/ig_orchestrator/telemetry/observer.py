from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Protocol

from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.telemetry.housekeeping import purge_telemetry
from ig_orchestrator.telemetry.schema import has_telemetry_schema
from ig_orchestrator.telemetry.trace import AttemptTrace, album_size_bucket

logger = get_logger()

LEVEL_OFF = "OFF"
LEVEL_ATTEMPTS = "ATTEMPTS"
LEVEL_FULL = "FULL"
TELEMETRY_LEVELS = (LEVEL_OFF, LEVEL_ATTEMPTS, LEVEL_FULL)

_FLOOD_RE = re.compile(r"Sleeping for (\d+)s on \w+ flood wait")
_FLOOD_LOGGER = "telethon.client.users"


class RunObserver(Protocol):
    """Sink for attempt traces; failures here must never break a batch."""

    def finish_attempt(self, trace: AttemptTrace) -> None:
        """Persist a finished attempt."""

    def record_flood_wait(self, seconds: float) -> None:
        """Note a Telethon FloodWait sleep for the attempt in progress."""

    def begin_attempt(self, trace: AttemptTrace) -> None:
        """Register the attempt that is now running."""


class NullObserver:
    """No-op observer (v1 database or telemetry OFF)."""

    def begin_attempt(self, trace: AttemptTrace) -> None:
        return None

    def finish_attempt(self, trace: AttemptTrace) -> None:
        return None

    def record_flood_wait(self, seconds: float) -> None:
        return None


class SqliteObserver:
    """Write one row per attempt (plus message/wait events at FULL level)."""

    def __init__(self, connection: Connection, *, level: str = LEVEL_FULL) -> None:
        if level not in (LEVEL_ATTEMPTS, LEVEL_FULL):
            raise ValueError("SqliteObserver level must be ATTEMPTS or FULL")
        self._connection = connection
        self._level = level
        self._current: AttemptTrace | None = None

    def begin_attempt(self, trace: AttemptTrace) -> None:
        self._current = trace

    def record_flood_wait(self, seconds: float) -> None:
        if self._current is not None:
            self._current.on_wait("FLOOD_WAIT", int(seconds * 1000))

    def finish_attempt(self, trace: AttemptTrace) -> None:
        if self._current is trace:
            self._current = None
        try:
            self._write(trace)
        except Exception:
            logger.warning("Telemetry write failed (ignored)", exc_info=True)
            try:
                self._connection.rollback()
            except Exception:
                pass

    def _write(self, trace: AttemptTrace) -> None:
        full = self._level == LEVEL_FULL
        finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO url_job_attempts (
                    url_job_id, batch_id, batch_run_id, account_id, attempt_no,
                    publication_type, album_size_bucket, started_at, finished_at,
                    t_send_ms, t_first_response_ms, t_first_media_ms,
                    t_last_media_ms, t_description_ms, t_end_wait_ms, t_download_ms,
                    t_move_ms, t_total_ms, flood_wait_ms, exit_reason, outcome,
                    error_code, messages_count, media_count, files_count,
                    bytes_downloaded, duplicates_skipped, aes_backend, settings_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trace.url_job_id,
                    trace.batch_id,
                    trace.batch_run_id,
                    trace.account_id,
                    trace.attempt_no,
                    trace.publication_type,
                    album_size_bucket(trace.media_count),
                    trace.started_at,
                    finished_at,
                    trace.t_send_ms,
                    trace.t_first_response_ms,
                    trace.t_first_media_ms,
                    trace.t_last_media_ms,
                    trace.t_description_ms,
                    trace.t_end_wait_ms,
                    trace.t_download_ms,
                    trace.t_move_ms,
                    trace.t_total_ms,
                    trace.flood_wait_ms,
                    trace.exit_reason,
                    trace.outcome,
                    (trace.error_code or "")[:120] or None,
                    trace.messages_count,
                    trace.media_count,
                    trace.files_count,
                    trace.bytes_downloaded,
                    trace.duplicates_skipped,
                    trace.aes_backend,
                    json.dumps(trace.settings, sort_keys=True),
                ),
            )
            attempt_id = cursor.lastrowid
            if full and trace.events:
                self._connection.executemany(
                    """
                    INSERT INTO bot_message_events (
                        attempt_id, message_id, grouped_id, offset_ms, kind, mime,
                        has_filename, size_bytes, download_ms, text_class, text_len
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            attempt_id,
                            e.message_id,
                            e.grouped_id,
                            e.offset_ms,
                            e.kind,
                            e.mime,
                            int(e.has_filename),
                            e.size_bytes,
                            e.download_ms,
                            e.text_class,
                            e.text_len,
                        )
                        for e in trace.events
                    ],
                )
            if trace.waits:
                self._connection.executemany(
                    "INSERT INTO run_wait_events (attempt_id, kind, ms, at) VALUES (?,?,?,?)",
                    [(attempt_id, w.kind, w.ms, w.at) for w in trace.waits],
                )


class _FloodWaitHandler(logging.Handler):
    """Turn Telethon's «Sleeping for Ns ... flood wait» log into a wait event."""

    def __init__(self, observer: RunObserver) -> None:
        super().__init__(level=logging.INFO)
        self._observer = observer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            match = _FLOOD_RE.search(record.getMessage())
            if match:
                self._observer.record_flood_wait(float(match.group(1)))
        except Exception:
            pass


def install_flood_wait_capture(observer: RunObserver) -> logging.Handler:
    """Attach the capture handler to Telethon's logger; returns it for removal."""

    target = logging.getLogger(_FLOOD_LOGGER)
    if target.level == logging.NOTSET or target.level > logging.INFO:
        target.setLevel(logging.INFO)
    handler = _FloodWaitHandler(observer)
    target.addHandler(handler)
    return handler


def build_observer(
    connection: Connection,
    *,
    level: str = LEVEL_FULL,
    retention_days: int | None = 90,
) -> RunObserver:
    """Return a SqliteObserver when the database has the telemetry tables."""

    if level not in TELEMETRY_LEVELS:
        raise ValueError(f"telemetry level must be one of {TELEMETRY_LEVELS}")
    if level == LEVEL_OFF or not has_telemetry_schema(connection):
        return NullObserver()
    if retention_days:
        try:
            removed = purge_telemetry(connection, older_than_days=retention_days)
            if removed:
                logger.info("Telemetry purged: attempts_removed={}", removed)
        except Exception:
            logger.warning("Telemetry purge failed (ignored)", exc_info=True)
    observer = SqliteObserver(connection, level=level)
    install_flood_wait_capture(observer)
    return observer


__all__ = [
    "LEVEL_ATTEMPTS",
    "LEVEL_FULL",
    "LEVEL_OFF",
    "NullObserver",
    "RunObserver",
    "SqliteObserver",
    "TELEMETRY_LEVELS",
    "build_observer",
    "install_flood_wait_capture",
]
