from __future__ import annotations

import threading
from pathlib import Path

import pytest

from ig_orchestrator.account_status.checker import (
    AccountStatus,
    HttpResult,
    check_account,
    classify_profile,
    is_valid_username,
    profile_url,
)
from ig_orchestrator.account_status.service import (
    RUN_COMPLETED,
    RUN_RATE_LIMITED,
    RUN_RUNNING,
    RUN_STOPPED,
    AccountStatusService,
    run_checks,
)
from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.orchestration.run_settings import RUN_SETTING_SPECS


def test_classify_profile_by_profile_id() -> None:
    assert classify_profile(HttpResult(200, '..."profile_id":"123456"...')).status is AccountStatus.AVAILABLE
    assert classify_profile(HttpResult(200, "<html>sin nada</html>")).status is AccountStatus.UNAVAILABLE
    assert classify_profile(HttpResult(404)).status is AccountStatus.UNAVAILABLE


def test_classify_profile_unknown_and_rate_limit() -> None:
    limited = classify_profile(HttpResult(429))
    assert limited.rate_limited and limited.status is AccountStatus.UNKNOWN
    assert classify_profile(HttpResult(None, error="timeout")).status is AccountStatus.UNKNOWN
    assert classify_profile(HttpResult(500)).status is AccountStatus.UNKNOWN


def test_username_validation_and_url() -> None:
    assert profile_url("@alice") == "https://www.instagram.com/alice/"
    assert is_valid_username("a.b_c9")
    assert not is_valid_username("../x")
    assert check_account("../x", fetcher=lambda *_: pytest.fail("no request")).status is AccountStatus.UNKNOWN


@pytest.fixture()
def service(tmp_path: Path):
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(tmp_path / "lib"),))
    now = "2026-01-01T00:00:00"
    root = str(tmp_path / "lib")
    cur = conn.execute(
        "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at, rel_path, kind)"
        " VALUES (NULL, 'root', ?, 0, ?, ?, '', 'ROOT')", (root, now, now))
    root_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at, rel_path, kind)"
        " VALUES (?, '09.DELETED', ?, 1, ?, ?, '09.DELETED', 'CATEGORY')", (root_id, root + "\\09.DELETED", now, now))
    folder_id = cur.lastrowid
    for i, name in enumerate(("alice", "bob", "carol"), start=1):
        conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path,"
            " legacy_lite_id) VALUES (?, ?, 1, ?, ?, ?, ?)",
            (name, folder_id, now, now, f"09.DELETED\\{name}", i))
    conn.commit()
    svc = AccountStatusService(conn)
    svc.folder_id = folder_id  # type: ignore[attr-defined]
    yield svc
    conn.close()


def _fetcher(answers: dict[str, HttpResult], calls: list[str]):
    def fetch(url: str, timeout: float) -> HttpResult:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        calls.append(name)
        return answers[name]
    return fetch


def test_run_completes_and_persists(service) -> None:
    run = service.create_run(service.folder_id)
    assert run.total == 3
    calls: list[str] = []
    answers = {
        "alice": HttpResult(200, '"profile_id":"1"'),
        "bob": HttpResult(200, "nada"),
        "carol": HttpResult(404),
    }
    slept: list[float] = []
    final = run_checks(service, run.id, interval_seconds=7, timeout_seconds=3, stop=threading.Event(),
                       fetcher=_fetcher(answers, calls), sleep=slept.append)
    assert final == RUN_COMPLETED
    assert slept == [7, 7]  # waits between accounts, not before the first
    assert service.summary(run.id) == {"AVAILABLE": 1, "UNAVAILABLE": 2}
    assert service.run(run.id).state == RUN_COMPLETED


def test_first_429_stops_and_resume_continues(service) -> None:
    run = service.create_run(service.folder_id)
    calls: list[str] = []
    answers = {"alice": HttpResult(200, '"profile_id":"1"'), "bob": HttpResult(429), "carol": HttpResult(404)}
    final = run_checks(service, run.id, interval_seconds=1, timeout_seconds=3, stop=threading.Event(),
                       fetcher=_fetcher(answers, calls), sleep=lambda _s: None)
    assert final == RUN_RATE_LIMITED
    assert calls == ["alice", "bob"]  # carol is never requested
    assert service.run(run.id).stop_reason == "RATE_LIMIT"

    answers["bob"] = HttpResult(200, "nada")
    calls.clear()
    final = run_checks(service, run.id, interval_seconds=1, timeout_seconds=3, stop=threading.Event(),
                       fetcher=_fetcher(answers, calls), sleep=lambda _s: None)
    assert final == RUN_COMPLETED
    assert calls == ["bob", "carol"]  # alice was already answered and is not asked again


def test_manual_stop_keeps_partial_results(service) -> None:
    run = service.create_run(service.folder_id)
    stop = threading.Event()
    calls: list[str] = []
    answers = {n: HttpResult(200, '"profile_id":"1"') for n in ("alice", "bob", "carol")}

    def sleep(_s: float) -> None:
        stop.set()  # the user presses Stop while waiting

    final = run_checks(service, run.id, interval_seconds=1, timeout_seconds=3, stop=stop,
                       fetcher=_fetcher(answers, calls), sleep=sleep)
    assert final == RUN_STOPPED
    assert calls == ["alice"]
    assert service.summary(run.id) == {"AVAILABLE": 1, "PENDING": 2}


def test_interrupted_run_is_recovered_and_paths_follow_moves(service) -> None:
    run = service.create_run(service.folder_id)
    service.set_state(run.id, RUN_RUNNING)
    assert service.recover_interrupted() == 1
    assert service.run(run.id).state == RUN_STOPPED
    service.conn.execute("UPDATE catalog_accounts SET rel_path = '01.ACTIVE\\alice' WHERE username = 'alice'")
    by_name = {r.username: r for r in service.results(run.id)}
    assert by_name["alice"].rel_path == "09.DELETED\\alice"  # the analysis keeps where it was found
    assert by_name["alice"].moved and by_name["alice"].destination == "01.ACTIVE\\alice"
    assert not by_name["bob"].moved and by_name["bob"].destination == ""


def test_movable_ids_skip_moved_and_unknown_accounts(service) -> None:
    from ig_orchestrator.gui.library.account_status_dialog import movable_ids

    run = service.create_run(service.folder_id)
    answers = {"alice": HttpResult(404), "bob": HttpResult(404), "carol": HttpResult(200, '"profile_id":"1"')}
    run_checks(service, run.id, interval_seconds=0, timeout_seconds=3, stop=threading.Event(),
               fetcher=_fetcher(answers, []), sleep=lambda _s: None)
    service.conn.execute("UPDATE catalog_accounts SET rel_path = '01.ACTIVE\\alice' WHERE username = 'alice'")
    results = service.results(run.id)
    names = {r.account_id: r.username for r in results}
    assert [names[i] for i in movable_ids(results, only_status="UNAVAILABLE")] == ["bob"]  # alice already moved
    assert sorted(names[i] for i in movable_ids(results)) == ["bob", "carol"]


def test_settings_for_the_interval_exist_with_bounds() -> None:
    spec = next(s for s in RUN_SETTING_SPECS if s.key == "run.accountcheck.interval_seconds")
    assert spec.parse("30") == 30
    with pytest.raises(ValueError):
        spec.parse("1")
