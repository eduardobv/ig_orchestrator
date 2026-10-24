"""Execution report over synthetic telemetry rows (feat-run-36)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ig_orchestrator.db import connect
from ig_orchestrator.db.gui_migrations import init_gui_database
from ig_orchestrator.telemetry.report import (
    attempts_to_csv,
    build_batch_report,
    has_report_data,
    percentile,
    report_to_markdown,
)

COLUMNS = (
    "url_job_id, batch_id, account_id, attempt_no, publication_type, album_size_bucket, "
    "expected_items, started_at, finished_at, t_first_response_ms, t_download_ms, "
    "t_end_wait_ms, t_move_ms, t_total_ms, flood_wait_ms, retry_wait_ms, exit_reason, "
    "outcome, error_code, files_count, bytes_downloaded, aes_backend"
)


def _connection(tmp_path: Path) -> sqlite3.Connection:
    path = tmp_path / "gui.sqlite"
    init_gui_database(path)
    return connect(path)


def _add(connection, job, kind="REEL", *, attempt=1, first=3000, download=1000,
         end_wait=500, flood=0, retry=0, total=6000, exit_reason="COUNT_REACHED",
         outcome="COMPLETED", error="", files=1, expected=1, aes="cryptg", batch=1):
    connection.execute(
        f"INSERT INTO url_job_attempts ({COLUMNS}) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (job, batch, 1, attempt, kind, "1" if kind == "REEL" else "11+", expected,
         "2026-10-24T10:00:00+00:00", "2026-10-24T11:00:00+00:00", first, download,
         end_wait, 0, total, flood, retry, exit_reason, outcome, error, files, 1000, aes),
    )
    connection.commit()


def test_empty_batch_has_no_data(tmp_path: Path) -> None:
    connection = _connection(tmp_path)

    report = build_batch_report(connection, 99)

    assert not has_report_data(connection, 99)
    assert report.attempts == ()
    assert "Sin telemetría" in report_to_markdown(report)


def test_report_phases_slowest_types_and_errors(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    _add(connection, 1, total=6000)
    _add(connection, 2, kind="POST", first=40000, download=2000, end_wait=0, total=60000,
         exit_reason="DESCRIPTION")
    _add(connection, 3, outcome="RETRY_PENDING", error="NO_BOT_RESPONSE", first=30000,
         total=31000, exit_reason="DEADLINE_FIRST", files=0)
    _add(connection, 3, attempt=2, retry=90000, total=95000)

    report = build_batch_report(connection, 1)

    assert report.urls == 3 and len(report.attempts) == 4
    assert report.slowest[0].total_ms == 95000
    assert report.phase_ms["backoff"] == 90000
    assert abs(sum(report.phase_percent().values()) - 100) < 0.01
    assert [e.code for e in report.errors] == ["NO_BOT_RESPONSE"]
    assert {s.label for s in report.by_type} == {"REEL (1)", "POST (11+)"}
    retries = {r.attempt_no: (r.attempts, r.completed) for r in report.retries}
    assert retries == {1: (3, 2), 2: (1, 1)}
    markdown = report_to_markdown(report)
    assert "## Recomendaciones" in markdown and "NO_BOT_RESPONSE" in markdown
    assert attempts_to_csv(report).count("\n") == 5  # header + 4 attempts


def test_recommendations_are_deterministic_rules(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    for job in range(1, 5):
        _add(connection, job, kind="POST", first=70000, total=80000, aes="pyaes",
             flood=20000, end_wait=30000, exit_reason="GRACE", files=2, expected=5)

    advice = " ".join(build_batch_report(connection, 1).recommendations)

    assert "cryptg" in advice
    assert "POST" in advice and "75 s" in advice
    assert "FloodWait" in advice
    assert "fin de espera" in advice.lower()
    assert "Silencio breve" in advice


def test_percentile_nearest_rank() -> None:
    assert percentile([], 0.9) is None
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9
    assert percentile([5], 0.5) == 5
