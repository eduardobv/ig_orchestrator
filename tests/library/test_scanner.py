from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library import scanner as scanner_module
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.rules import LibraryRules
from ig_orchestrator.library.scanner import (
    ACCOUNT,
    ALL,
    CATEGORY,
    LibraryScanner,
    ScanError,
    accept_finding,
    ignore_finding,
    list_findings,
)

NOW = "2026-01-01T00:00:00"


def img(day: str, media_id: int, owner: int, ext: str = "jpg", tail: str = "") -> str:
    return f"{day} 10.00.00 {media_id}_{owner}{tail}.{ext}"


def put(lib: Path, rel: str, name: str, data: bytes = b"x") -> None:
    target = lib / rel.replace("\\", "/") / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def bump(path: Path, seconds: float = 100.0) -> None:
    """Make the folder look modified (mtime granularity on some file systems is coarse)."""

    stamp = time.time() + seconds
    os.utime(path, (stamp, stamp))


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    put(lib, "00.FAVORITES\\Group\\alice", img("2026-03-01", 111, 5000))
    put(lib, "00.FAVORITES\\Group\\alice", img("2026-03-02", 112, 5000, tail="_manual"))
    put(lib, "00.FAVORITES\\Group\\alice\\story", img("2026-04-01", 211, 5000, "mp4"))
    put(lib, "00.FAVORITES\\Group\\alice\\reels", img("2026-02-01", 311, 5000, "mp4"))
    put(lib, "00.FAVORITES\\Group\\alice\\highlights", img("2026-01-01", 411, 5000))
    put(lib, "00.FAVORITES\\Group\\alice\\highlights", "notes.txt")
    put(lib, "00.FAVORITES\\Group\\bob", img("2026-05-01", 511, 6000))
    put(lib, "02.PRIVATE\\carol", img("2026-06-01", 611, 7000))
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    ids: dict[str, int] = {}
    for name, rel in (("alice", "00.FAVORITES\\Group\\alice"), ("bob", "00.FAVORITES\\Group\\bob"), ("carol", "02.PRIVATE\\carol")):
        ids[name] = conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at,"
            " rel_path, posts_count, last_media_at) VALUES (?, ?, ?, 1, ?, ?, ?, 99, '2000-01-01 00:00:00')",
            (name, {"alice": "5000", "bob": "6000", "carol": "7000"}[name], fs.ensure_folder_rows(rel.rsplit("\\", 1)[0]), NOW, NOW, rel),
        ).lastrowid
    conn.commit()
    yield LibraryScanner(conn), conn, lib, ids
    conn.close()


def row(conn, account_id: int):
    return conn.execute("SELECT * FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()


def test_first_scan_trusts_the_import_and_only_records_mtimes(env) -> None:
    scanner, conn, _lib, ids = env

    report = scanner.scan(ALL)

    assert report.accounts_checked == 3 and report.baselined == 3
    assert report.files_seen == 0 and report.accounts_changed == 0
    alice = row(conn, ids["alice"])
    assert alice["posts_count"] == 99  # imported value kept
    assert alice["dir_mtime_root"] is not None and alice["scan_state"] == "OK" and alice["disk_state"] == "PRESENT"


def test_second_scan_without_changes_reads_no_account_folder(env) -> None:
    scanner, conn, _lib, _ids = env
    scanner.scan(ALL)

    report = scanner.scan(ALL)

    assert report.files_seen == 0 and report.accounts_changed == 0 and report.baselined == 0
    assert not report.findings and report.errors == 0
    # only the category/group folders were listed (no account folder)
    assert report.dirs_listed <= 5


def test_only_the_changed_account_is_read_again(env) -> None:
    scanner, conn, lib, ids = env
    scanner.scan(ALL)
    reels = lib / "00.FAVORITES/Group/alice/reels"
    put(lib, "00.FAVORITES\\Group\\alice\\reels", img("2026-07-01", 312, 5000, "mp4"))
    bump(reels)

    report = scanner.scan(ALL)

    assert report.accounts_changed == 1 and report.files_seen == 2  # only alice/reels was listed
    alice = row(conn, ids["alice"])
    assert alice["reels_count"] == 2 and alice["scan_state"] == "CHANGED"
    assert row(conn, ids["bob"])["scan_state"] == "OK"
    kinds = {r[0]: r[1] for r in conn.execute("SELECT kind, COUNT(*) FROM media_index WHERE account_id = ? GROUP BY kind", (ids["alice"],))}
    assert kinds == {1: 2}  # the index of that (account, kind) was rebuilt, the others untouched


def test_deep_scan_matches_the_sc1_algorithm(env) -> None:
    scanner, conn, _lib, ids = env

    report = scanner.scan(ALL, deep=True)

    alice = row(conn, ids["alice"])
    assert (alice["posts_count"], alice["reels_count"], alice["story_count"], alice["highlights_count"]) == (2, 1, 1, 1)
    assert alice["last_media_at"] == "2026-04-01 10:00:00"  # newest parsed timestamp, notes.txt ignored
    assert alice["instagram_user_id"] == "5000"
    assert report.scope == "DEEP" and report.baselined == 0
    index = conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (ids["alice"],)).fetchone()[0]
    assert index == 5
    suffixes = {r[0] for r in conn.execute("SELECT suffix FROM media_index WHERE account_id = ?", (ids["alice"],))}
    assert suffixes == {"", "_manual"}


def test_owner_is_filled_when_empty_and_reported_when_different(env) -> None:
    scanner, conn, lib, ids = env
    conn.execute("UPDATE catalog_accounts SET instagram_user_id = NULL WHERE id = ?", (ids["alice"],))
    conn.execute("UPDATE catalog_accounts SET instagram_user_id = '1' WHERE id = ?", (ids["bob"],))
    conn.commit()

    report = scanner.scan(ALL)

    assert row(conn, ids["alice"])["instagram_user_id"] == "5000"
    assert [(f.kind, f.account_id) for f in report.findings if f.kind == "OWNER_CHANGED"] == []  # bob was baselined
    deep = scanner.scan(ALL, deep=True)
    changed = [f for f in deep.findings if f.kind == "OWNER_CHANGED"]
    assert len(changed) == 1 and changed[0].account_id == ids["bob"]
    assert row(conn, ids["bob"])["instagram_user_id"] == "1"  # never overwritten silently
    assert accept_finding(conn, list_findings(conn)[0]["id"]).startswith("Id de Instagram actualizado")
    assert row(conn, ids["bob"])["instagram_user_id"] == "6000"


def test_new_folder_is_a_finding_and_accepting_creates_an_archived_account(env) -> None:
    scanner, conn, lib, _ids = env
    put(lib, "00.FAVORITES\\Group\\dave", img("2026-08-01", 811, 8000))

    report = scanner.scan(ALL)

    assert [(f.kind, f.rel_path) for f in report.findings] == [("NEW_FOLDER", "00.FAVORITES\\Group\\dave")]
    assert conn.execute("SELECT COUNT(*) FROM catalog_accounts WHERE username = 'dave'").fetchone()[0] == 0  # not applied alone
    finding = list_findings(conn)[0]
    accept_finding(conn, finding["id"])
    dave = conn.execute("SELECT a.*, s.code AS st FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id"
                        " WHERE username = 'dave'").fetchone()
    assert dave["st"] == "ARCHIVED" and dave["rel_path"] == "00.FAVORITES\\Group\\dave"
    assert list_findings(conn) == []
    scanner.scan(ALL, deep=False)  # the new account gets read on the next scan (no more findings)
    assert not scanner.scan(ALL).findings


def test_folder_moved_in_explorer_is_proposed_not_applied(env) -> None:
    scanner, conn, lib, ids = env
    scanner.scan(ALL)
    shutil.move(str(lib / "00.FAVORITES/Group/alice"), str(lib / "02.PRIVATE/alice"))

    report = scanner.scan(ALL)

    kinds = sorted((f.kind, f.rel_path) for f in report.findings)
    assert kinds == [("MOVED_FOLDER", "02.PRIVATE\\alice")]  # the old path is not reported twice
    assert row(conn, ids["alice"])["rel_path"] == "00.FAVORITES\\Group\\alice"
    assert row(conn, ids["alice"])["disk_state"] == "MISSING"
    accept_finding(conn, list_findings(conn)[0]["id"])
    alice = row(conn, ids["alice"])
    assert (alice["rel_path"], alice["disk_state"]) == ("02.PRIVATE\\alice", "PRESENT")
    after = scanner.scan(ALL)
    assert after.accounts_missing == 0 and not after.findings


def test_missing_folder_is_flagged_but_never_deleted(env) -> None:
    scanner, conn, lib, ids = env
    shutil.rmtree(lib / "02.PRIVATE/carol")

    report = scanner.scan(ALL)

    assert report.accounts_missing == 1 and report.findings[0].kind == "MISSING_FOLDER"
    carol = row(conn, ids["carol"])
    assert carol["disk_state"] == "MISSING" and carol["scan_state"] == "MISSING"
    ignore_finding(conn, report.findings[0].account_id and list_findings(conn)[0]["id"])
    assert list_findings(conn) == []


def test_read_errors_prevent_marking_accounts_missing(env, monkeypatch) -> None:
    scanner, conn, lib, ids = env
    shutil.rmtree(lib / "02.PRIVATE/carol")
    real = scanner_module._read_dir

    def flaky(path, report):
        if path.endswith("00.FAVORITES"):
            report.errors += 1  # simulate an unreadable folder
        return real(path, report)

    monkeypatch.setattr(scanner_module, "_read_dir", flaky)

    report = scanner.scan(ALL)

    assert report.errors >= 1 and report.accounts_missing == 0
    assert row(conn, ids["carol"])["disk_state"] != "MISSING"


def test_account_and_category_scopes(env) -> None:
    scanner, conn, lib, ids = env
    scanner.scan(ALL)
    put(lib, "02.PRIVATE\\carol", img("2026-09-01", 612, 7000))
    bump(lib / "02.PRIVATE/carol")
    put(lib, "00.FAVORITES\\Group\\bob", img("2026-09-02", 512, 6000))
    bump(lib / "00.FAVORITES/Group/bob")

    one = scanner.scan(ACCOUNT, account_id=ids["carol"])
    assert (one.accounts_checked, one.accounts_changed) == (1, 1) and row(conn, ids["bob"])["scan_state"] == "OK"

    category = scanner.scan(CATEGORY, rel_scope="00.FAVORITES")
    assert category.accounts_checked == 2 and category.accounts_changed == 1  # bob changed, alice did not


def test_offline_library_and_concurrent_scan_are_refused(env, tmp_path: Path) -> None:
    scanner, conn, lib, _ids = env
    offline = LibraryScanner(conn, root=str(tmp_path / "gone"))
    with pytest.raises(ScanError, match="no esta disponible"):
        offline.scan(ALL)
    assert scanner_module._SCAN_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ScanError, match="en curso"):
            scanner.scan(ALL)
    finally:
        scanner_module._SCAN_LOCK.release()


def test_cancel_keeps_what_was_done(env) -> None:
    scanner, conn, _lib, _ids = env
    cancel = threading.Event()
    cancel.set()

    report = scanner.scan(ALL, cancel_event=cancel)

    assert report.cancelled and report.accounts_checked == 0
    assert conn.execute("SELECT finished_at FROM scan_runs WHERE id = ?", (report.run_id,)).fetchone()[0]


def test_runs_and_findings_are_recorded(env) -> None:
    scanner, conn, lib, _ids = env
    put(lib, "00.FAVORITES\\Group\\erin", img("2026-08-01", 911, 9000))

    report = scanner.scan(ALL)

    run = conn.execute("SELECT * FROM scan_runs WHERE id = ?", (report.run_id,)).fetchone()
    assert run["scope"] == "ALL" and run["accounts_new"] == 1 and run["seconds"] >= 0
    assert conn.execute("SELECT COUNT(*) FROM scan_findings WHERE scan_run_id = ?", (report.run_id,)).fetchone()[0] == 1


def test_rules_are_configurable_from_app_settings(env) -> None:
    _scanner, conn, _lib, _ids = env
    assert LibraryRules.load(conn).max_depth == 3 and LibraryRules.load(conn).is_multimedia("A.JPG")
    conn.execute("INSERT INTO app_settings (key, value, value_type, updated_at) VALUES ('library.max_depth', '2', 'TEXT', 'x')")
    conn.execute("INSERT INTO app_settings (key, value, value_type, updated_at) VALUES ('library.media_extensions', '.gif', 'TEXT', 'x')")
    conn.commit()

    rules = LibraryRules.load(conn)

    assert rules.max_depth == 2 and rules.is_multimedia("x.gif") and not rules.is_multimedia("x.jpg")
