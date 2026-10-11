from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library import render_csv, render_markdown, run_audit
from ig_orchestrator.library.audit import classify_owner_group


def _make_lite(path: Path, rows: list[tuple[str, str, str, str | None, str]], table: str = "accounts_dir") -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""CREATE TABLE {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, ownerId TEXT,
                path TEXT NOT NULL, last_modified TEXT, created_at TEXT NOT NULL DEFAULT '',
                modified_at TEXT NOT NULL DEFAULT '', UNIQUE(path))"""
        )
        conn.executemany(
            f"INSERT INTO {table} (username, ownerId, path, last_modified, modified_at) VALUES (?,?,?,?,?)",
            rows,
        )


@pytest.fixture()
def library(tmp_path: Path) -> Path:
    root = tmp_path / "4K Stogram"
    for rel in (
        "00.FAVORITES/alice",
        "00.FAVORITES/alice2",
        "09.DELETED/old_bob",
        "00.MODELS/bob",
        "00.MODELS/Carol",
        "00.MODELS/dave",
    ):
        (root / rel).mkdir(parents=True)
    return root


def _app_db(tmp_path: Path, accounts: list[tuple[str, str | None, str, str]]):
    db_path = tmp_path / "gui.sqlite"
    init_gui_database(db_path)
    connection = connect(db_path)
    now = "2026-01-01T00:00:00"
    for username, owner, folder, status in accounts:
        folder_id = connection.execute(
            "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at)"
            " VALUES (NULL, ?, ?, 0, ?, ?)",
            (Path(folder).name, folder, now, now),
        ).lastrowid
        connection.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id,"
            " created_at, updated_at) SELECT ?, ?, ?, id, ?, ? FROM catalog_account_statuses WHERE code = ?",
            (username, owner, folder_id, now, now, status),
        )
    connection.commit()
    return connection


def _codes(report) -> set[str]:
    return set(report.summary())


def test_classify_owner_group() -> None:
    assert classify_owner_group([r"G:\x\00.A\u1", r"G:\x\00.A\u2"]) == "SAME_CATEGORY"
    assert classify_owner_group([r"G:\x\00.A\u1", r"G:\x\09.DELETED\u1"]) == "DELETED_PAIR"
    assert classify_owner_group([r"G:\x\09.DELETED\u1", r"G:\x\09.DELETED\u2"]) == "ALL_DELETED"
    assert classify_owner_group([r"G:\x\00.A\u1", r"G:\x\00.B\u2"]) == "CROSS_CATEGORY"


def test_audit_detects_each_code(tmp_path: Path, library: Path) -> None:
    lite = tmp_path / "accounts_lite.sqlite"
    _make_lite(
        lite,
        [
            ("alice", "1", str(library / "00.FAVORITES/alice"), None, "2026-01-01 10:00:00"),
            ("alice2", "1", str(library / "00.FAVORITES/alice2"), None, "2026-01-01T10:00:00"),
            ("bob", "2", str(library / "00.MODELS/bob"), None, "2026-01-01 10:00:00"),
            ("old_bob", "2", str(library / "09.DELETED/old_bob"), None, "2026-01-01 10:00:00"),
            ("carol", "3", str(library / "00.MODELS/Carol"), None, "2026-01-01 10:00:00"),
            ("ghost", "4", str(library / "00.MODELS/ghost"), None, "2026-01-01 10:00:00"),
            ("dave", "5", str(library / "00.MODELS/dave"), None, "2026-01-01 10:00:00"),
        ],
    )
    complete = tmp_path / "accounts_complete.sqlite"
    _make_lite(
        complete,
        [("alice", "1", str(library / "00.FAVORITES/alice"), None, "2026-01-01 10:00:00")],
        table="accounts",
    )
    connection = _app_db(
        tmp_path,
        [
            ("alice", "1", str(library / "00.FAVORITES/alice"), "ENABLED"),
            ("dave", "999", str(library / "00.MODELS/dave"), "ENABLED"),
            ("bob", "2", str(library / "00.MODELS/elsewhere"), "ENABLED"),
            ("zed", "7", str(library / "00.MODELS/zed"), "DISABLED"),
        ],
    )

    report = run_audit(connection, lite, complete)

    assert _codes(report) == {
        "PATH_MISSING",
        "OWNER_DUP",
        "OWNER_MISMATCH",
        "FOLDER_MISMATCH",
        "ONLY_IN_APP",
        "ONLY_IN_LITE",
        "COMPLETE_STALE",
        "LAST_MODIFIED_MIXED",
        "NAME_CASE",
    }
    assert {f.paths[0] for f in report.by_code("PATH_MISSING") if "ghost" in f.paths[0]}
    dups = {f.owner_id: f.detail for f in report.by_code("OWNER_DUP")}
    assert dups == {"1": "SAME_CATEGORY", "2": "DELETED_PAIR"}
    assert report.by_code("OWNER_MISMATCH")[0].username == "dave"
    assert report.by_code("ONLY_IN_APP")[0].username == "zed"
    assert report.disk_checked


def test_person_folder_parent_counts_as_match(tmp_path: Path, library: Path) -> None:
    lite = tmp_path / "accounts_lite.sqlite"
    _make_lite(lite, [("alice", "1", str(library / "00.FAVORITES/alice"), None, "x")])
    connection = _app_db(tmp_path, [("alice", "1", str(library / "00.FAVORITES"), "ENABLED")])

    report = run_audit(connection, lite)

    assert "FOLDER_MISMATCH" not in _codes(report)


def test_disk_offline_skips_disk_checks(tmp_path: Path) -> None:
    lite = tmp_path / "accounts_lite.sqlite"
    _make_lite(lite, [("a", "1", r"Z:\nope\root\a", None, "x"), ("b", "2", r"Z:\nope\root\b", None, "x")])

    report = run_audit(None, lite)

    assert _codes(report) == {"DISK_OFFLINE"}
    assert not report.disk_checked


def test_missing_complete_adds_note(tmp_path: Path, library: Path) -> None:
    lite = tmp_path / "accounts_lite.sqlite"
    _make_lite(lite, [("alice", "1", str(library / "00.FAVORITES/alice"), None, "x")])

    report = run_audit(None, lite, tmp_path / "nope.sqlite")

    assert any("accounts_complete" in note for note in report.notes)


def test_audit_does_not_modify_databases(tmp_path: Path, library: Path) -> None:
    lite = tmp_path / "accounts_lite.sqlite"
    _make_lite(lite, [("alice", "1", str(library / "00.FAVORITES/alice"), None, "x")])
    before = (lite.stat().st_mtime_ns, lite.read_bytes())

    run_audit(None, lite)

    assert (lite.stat().st_mtime_ns, lite.read_bytes()) == before
    assert not list(tmp_path.glob("accounts_lite.sqlite-*"))


def test_renderers(tmp_path: Path, library: Path) -> None:
    lite = tmp_path / "accounts_lite.sqlite"
    _make_lite(
        lite,
        [("alice", "1", str(library / "00.FAVORITES/alice"), None, "x"),
         ("alice2", "1", str(library / "00.FAVORITES/alice2"), None, "x")],
    )
    report = run_audit(None, lite)

    md = render_markdown(report)
    csv_text = render_csv(report)

    assert "| `OWNER_DUP` | 1 |" in md
    assert csv_text.startswith("\ufeffcode,severity,username")
    assert "OWNER_DUP" in csv_text
