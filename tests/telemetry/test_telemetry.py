from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_database
from ig_orchestrator.db.gui_migrations import init_gui_database
from ig_orchestrator.telemetry import (
    AttemptTrace,
    NullObserver,
    SqliteObserver,
    build_observer,
    purge_telemetry,
)
from ig_orchestrator.telemetry.observer import install_flood_wait_capture
from ig_orchestrator.telemetry.trace import (
    EXIT_STABLE,
    TEXT_CLASS_DESCRIPTION,
    album_size_bucket,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _gui_connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    return connect(db_path)


def _trace(clock: FakeClock) -> AttemptTrace:
    return AttemptTrace.start(
        url_job_id=7,
        account_id=3,
        batch_run_id=11,
        attempt_no=2,
        publication_type="REEL",
        clock=clock,
    )


def _reel_attempt(clock: FakeClock) -> AttemptTrace:
    """Reel with the real sequence: file, duplicate file, description."""

    trace = _trace(clock)
    clock.advance(0.2)
    trace.mark_sent()
    clock.advance(3.8)
    trace.on_message(
        message_id=1, grouped_id=None, kind="DOCUMENT_FILE", mime="video/mp4",
        has_filename=True, size_bytes=2_300_000,
    )
    trace.on_download(1, 1500, 2_300_000)
    clock.advance(0.3)
    trace.on_message(
        message_id=3, grouped_id=None, kind="TEXT",
        text_class=TEXT_CLASS_DESCRIPTION, text_len=42,
    )
    clock.advance(10.0)
    trace.end_wait(EXIT_STABLE)
    trace.t_download_ms = 120
    trace.finish(outcome="COMPLETED", error_code=None)
    return trace


def test_trace_measures_phases_from_the_send_moment() -> None:
    trace = _reel_attempt(FakeClock())

    assert trace.t_send_ms == 200
    assert trace.t_first_response_ms == 3800
    assert trace.t_first_media_ms == 3800
    assert trace.t_description_ms == 4100
    assert trace.t_end_wait_ms == 10000
    assert trace.t_total_ms == 14300
    assert trace.messages_count == 2
    assert trace.media_count == 1
    assert trace.bytes_downloaded == 2_300_000
    assert trace.events[0].download_ms == 1500


def test_album_size_buckets() -> None:
    assert [album_size_bucket(n) for n in (0, 1, 2, 4, 5, 10, 11, 30)] == [
        "1", "1", "2-4", "2-4", "5-10", "5-10", "11+", "11+",
    ]


def test_gui_migration_creates_telemetry_tables(tmp_path: Path) -> None:
    connection = _gui_connection(tmp_path)
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert {"url_job_attempts", "bot_message_events", "run_wait_events"} <= tables
    # idempotent
    init_gui_database(tmp_path / "orchestrator_gui.sqlite")


def test_sqlite_observer_writes_attempt_events_and_waits(tmp_path: Path) -> None:
    connection = _gui_connection(tmp_path)
    observer = SqliteObserver(connection)
    trace = _reel_attempt(FakeClock())
    trace.batch_id = 5
    observer.begin_attempt(trace)
    observer.record_flood_wait(11)

    observer.finish_attempt(trace)

    row = connection.execute("SELECT * FROM url_job_attempts").fetchone()
    assert row["url_job_id"] == 7 and row["batch_id"] == 5
    assert row["attempt_no"] == 2 and row["outcome"] == "COMPLETED"
    assert row["t_first_response_ms"] == 3800 and row["flood_wait_ms"] == 11000
    assert row["exit_reason"] == EXIT_STABLE and row["album_size_bucket"] == "1"
    events = connection.execute("SELECT * FROM bot_message_events").fetchall()
    assert [e["kind"] for e in events] == ["DOCUMENT_FILE", "TEXT"]
    # privacy: only class and length of the description are stored
    assert events[1]["text_class"] == "DESCRIPTION" and events[1]["text_len"] == 42
    wait = connection.execute("SELECT kind, ms FROM run_wait_events").fetchone()
    assert (wait["kind"], wait["ms"]) == ("FLOOD_WAIT", 11000)


def test_attempts_level_skips_message_events(tmp_path: Path) -> None:
    connection = _gui_connection(tmp_path)
    observer = SqliteObserver(connection, level="ATTEMPTS")

    observer.finish_attempt(_reel_attempt(FakeClock()))

    assert connection.execute("SELECT COUNT(*) FROM url_job_attempts").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM bot_message_events").fetchone()[0] == 0


def test_observer_failure_never_raises(tmp_path: Path) -> None:
    connection = _gui_connection(tmp_path)
    connection.execute("DROP TABLE url_job_attempts")

    SqliteObserver(connection).finish_attempt(_reel_attempt(FakeClock()))


def test_build_observer_is_null_for_v1_database_and_when_off(tmp_path: Path) -> None:
    v1_path = tmp_path / "orchestrator.db"
    init_database(v1_path)

    assert isinstance(build_observer(connect(v1_path)), NullObserver)
    assert isinstance(build_observer(_gui_connection(tmp_path), level="OFF"), NullObserver)
    with pytest.raises(ValueError):
        build_observer(_gui_connection(tmp_path), level="LOUD")


def test_purge_removes_old_attempts_with_their_events(tmp_path: Path) -> None:
    connection = _gui_connection(tmp_path)
    observer = SqliteObserver(connection)
    old, new = _reel_attempt(FakeClock()), _reel_attempt(FakeClock())
    old.started_at = (
        datetime.now(timezone.utc) - timedelta(days=120)
    ).isoformat(timespec="seconds")
    old.batch_id, new.batch_id = 1, 2
    observer.finish_attempt(old)
    observer.finish_attempt(new)

    assert purge_telemetry(connection, older_than_days=90) == 1
    assert connection.execute("SELECT COUNT(*) FROM url_job_attempts").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM bot_message_events").fetchone()[0] == 2
    assert purge_telemetry(connection, batch_id=2) == 1
    assert connection.execute("SELECT COUNT(*) FROM bot_message_events").fetchone()[0] == 0
    with pytest.raises(ValueError):
        purge_telemetry(connection)


def test_flood_wait_log_line_is_recorded_on_current_attempt(tmp_path: Path) -> None:
    connection = _gui_connection(tmp_path)
    observer = SqliteObserver(connection)
    trace = _trace(FakeClock())
    observer.begin_attempt(trace)
    handler = install_flood_wait_capture(observer)
    try:
        logging.getLogger("telethon.client.users").info(
            "Sleeping for %ds on GetHistoryRequest flood wait", 11
        )
    finally:
        logging.getLogger("telethon.client.users").removeHandler(handler)

    assert trace.flood_wait_ms == 11000
    assert [w.kind for w in trace.waits] == ["FLOOD_WAIT"]


def test_service_attaches_trace_with_exit_reason_and_events(tmp_path: Path) -> None:
    from tests.telegram.test_bot_conversation_service import (  # type: ignore
        _incoming,
        _service,
        _stored_job,
    )
    from ig_orchestrator.db import DownloadRepository, UrlJobRepository

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    connection = connect(db_path)
    job_repo = UrlJobRepository(connection)
    service = _service(
        tmp_path,
        job_repo,
        DownloadRepository(connection),
        messages=[_incoming("The service is overloaded, please try again later.")],
        watcher=lambda *_a: [],
    )

    result = asyncio.run(service.process_url_job(_stored_job(job_repo)))

    assert result.trace is not None
    assert result.trace.exit_reason == "ERROR_TEXT"
    assert result.trace.messages_count == 1
    assert result.trace.events[0].text_class == "ERROR"
    assert result.trace.aes_backend in {"cryptg", "pyaes"}
    assert result.trace.attempt_no == 1


def test_processor_flushes_one_row_with_move_time_and_outcome(tmp_path: Path) -> None:
    from tests.orchestration.test_url_job_processor import (  # type: ignore
        FakeConversationService,
        _download_file,
        _stored_entities,
    )
    from ig_orchestrator.models import UrlJobStatus
    from ig_orchestrator.orchestration import UrlJobProcessor
    from ig_orchestrator.telegram import BotConversationResult
    from ig_orchestrator.telemetry import ensure_telemetry_schema

    stored = _stored_entities(tmp_path)
    source = tmp_path / "downloads" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    download_file = stored.download_repo.create(_download_file(stored.job.id, source))
    downloaded = stored.job_repo.update_status(stored.job.id, UrlJobStatus.DOWNLOADED)
    telemetry_db = sqlite3.connect(":memory:")
    telemetry_db.row_factory = sqlite3.Row
    ensure_telemetry_schema(telemetry_db)
    trace = _reel_attempt(FakeClock())
    processor = UrlJobProcessor(
        url_job_repository=stored.job_repo,
        account_repository=stored.account_repo,
        download_repository=stored.download_repo,
        conversation_service=FakeConversationService(
            BotConversationResult(job=downloaded, files=(download_file,), trace=trace)
        ),
        observer=SqliteObserver(telemetry_db),
    )

    asyncio.run(processor.process(stored.job.id))

    row = telemetry_db.execute("SELECT * FROM url_job_attempts").fetchone()
    assert row["outcome"] == "COMPLETED" and row["files_count"] == 1
    assert row["batch_id"] == stored.account.batch_id
    assert row["t_move_ms"] is not None
