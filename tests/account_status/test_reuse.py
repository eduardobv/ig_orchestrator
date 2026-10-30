from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ig_orchestrator.account_status.checker import HttpResult
from ig_orchestrator.account_status.schema import ensure_account_status_schema
from ig_orchestrator.account_status.service import (
    RUN_COMPLETED,
    RUN_STOPPED,
    AccountStatusService,
    reuse_hours,
    run_checks,
)
from ig_orchestrator.db import connect, init_gui_database

BS = chr(92)


@pytest.fixture()
def service(tmp_path: Path):
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    now = "2026-01-01T00:00:00"
    root = str(tmp_path / "lib")
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (root,))
    top = conn.execute(
        "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at, rel_path, kind)"
        " VALUES (NULL, 'root', ?, 0, ?, ?, '', 'ROOT')", (root, now, now)).lastrowid
    folders = {}
    for name in ("01.ACTIVE", "09.DELETED"):
        folders[name] = conn.execute(
            "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at, rel_path, kind)"
            " VALUES (?, ?, ?, 1, ?, ?, ?, 'CATEGORY')", (top, name, root + BS + name, now, now, name)).lastrowid
    for i, name in enumerate(("alice", "bob", "carol"), start=1):
        conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path,"
            " legacy_lite_id) VALUES (?, ?, 1, ?, ?, ?, ?)",
            (name, folders["09.DELETED"], now, now, "09.DELETED" + BS + name, i))
    conn.commit()
    svc = AccountStatusService(conn)
    svc.folders = folders  # type: ignore[attr-defined]
    yield svc
    conn.close()


def _answer(service, run_id, name, status, hours_ago):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    service.conn.execute(
        "UPDATE account_check_results SET status = ?, http_status = 200, checked_at = ? WHERE run_id = ? AND username = ?",
        (status, when, run_id, name))
    service.conn.commit()


def test_recent_answers_are_reused_and_old_ones_are_not(service) -> None:
    first = service.create_run(service.folders["09.DELETED"])
    _answer(service, first.id, "alice", "UNAVAILABLE", 1)
    _answer(service, first.id, "bob", "AVAILABLE", 100)  # older than the 48 h window
    second = service.create_run(service.folders["09.DELETED"], reuse_hours=48)
    by_name = {r.username: r for r in service.results(second.id)}
    assert by_name["alice"].reused and by_name["alice"].status == "UNAVAILABLE"
    assert by_name["alice"].source_run_id == first.id
    assert not by_name["bob"].reused and by_name["bob"].status == "PENDING"
    assert not by_name["carol"].reused


def test_zero_hours_never_reuses_and_unknown_is_not_reused(service) -> None:
    first = service.create_run(service.folders["09.DELETED"])
    _answer(service, first.id, "alice", "UNAVAILABLE", 1)
    _answer(service, first.id, "bob", "UNKNOWN", 1)
    second = service.create_run(service.folders["09.DELETED"], reuse_hours=0)
    assert not any(r.reused for r in service.results(second.id))
    third = service.create_run(service.folders["09.DELETED"], reuse_hours=48)
    by_name = {r.username: r for r in service.results(third.id)}
    assert by_name["alice"].reused and not by_name["bob"].reused


def test_reused_accounts_are_not_requested_and_run_can_complete(service) -> None:
    first = service.create_run(service.folders["09.DELETED"])
    for name in ("alice", "bob", "carol"):
        _answer(service, first.id, name, "UNAVAILABLE", 1)
    second = service.create_run(service.folders["09.DELETED"], reuse_hours=48)
    assert second.state == RUN_COMPLETED  # nothing left to ask
    calls: list[str] = []
    final = run_checks(service, second.id, interval_seconds=0, timeout_seconds=3, stop=threading.Event(),
                       fetcher=lambda url, t: calls.append(url) or HttpResult(404), sleep=lambda _s: None)
    assert calls == [] and final == RUN_COMPLETED


def test_force_reanalysis_asks_again_only_for_reused(service) -> None:
    first = service.create_run(service.folders["09.DELETED"])
    _answer(service, first.id, "alice", "UNAVAILABLE", 1)
    second = service.create_run(service.folders["09.DELETED"], reuse_hours=48)
    assert service.force_reanalysis(second.id) == 1
    assert service.run(second.id).state == RUN_STOPPED
    calls: list[str] = []
    run_checks(service, second.id, interval_seconds=0, timeout_seconds=3, stop=threading.Event(),
               fetcher=lambda url, t: calls.append(url.rstrip("/").rsplit("/", 1)[-1]) or HttpResult(200, "x"),
               sleep=lambda _s: None)
    assert sorted(calls) == ["alice", "bob", "carol"]
    assert not any(r.reused for r in service.results(second.id))


def test_reuse_setting_default_and_override(service) -> None:
    assert reuse_hours(service.conn) == 48
    service.conn.execute(
        "INSERT INTO app_settings (key, value, value_type, updated_at) VALUES ('accountcheck.reuse_hours', '6', 'TEXT', 'x')")
    assert reuse_hours(service.conn) == 6


def test_old_table_gets_the_new_column() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE account_check_runs (id INTEGER PRIMARY KEY, folder_id INTEGER, folder_rel TEXT,"
                 " state TEXT, stop_reason TEXT, total INTEGER, created_at TEXT, updated_at TEXT)")
    conn.execute("CREATE TABLE account_check_results (id INTEGER PRIMARY KEY, run_id INTEGER, account_id INTEGER,"
                 " username TEXT, rel_path TEXT, status TEXT, http_status INTEGER, detail TEXT, checked_at TEXT,"
                 " UNIQUE (run_id, username))")
    ensure_account_status_schema(conn)
    assert "source_run_id" in {r[1] for r in conn.execute("PRAGMA table_info(account_check_results)")}
