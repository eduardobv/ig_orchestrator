from __future__ import annotations

from pathlib import Path
import sqlite3

from ig_orchestrator.filesystem.story_inbox import (
    StoryInboxStatus,
    build_report,
    force_move_conflicts,
    organize_story_inbox,
)


def _accounts_db(path: Path, rows: list[tuple[str, str]]) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE accounts_dir (username TEXT NOT NULL, path TEXT)")
    connection.executemany("INSERT INTO accounts_dir VALUES (?, ?)", rows)
    connection.commit()
    connection.close()
    return path


def _setup(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    ok = tmp_path / "ok"
    dup = tmp_path / "dup"
    ok.mkdir()
    dup.mkdir()
    (dup / "story").mkdir()
    (dup / "story" / "dup-1.jpg").write_bytes(b"old")
    (inbox / "ok-1.jpg").write_bytes(b"a")
    (inbox / "dup-1.jpg").write_bytes(b"new")
    (inbox / "ghost-1.jpg").write_bytes(b"x")
    db = _accounts_db(
        tmp_path / "a.db",
        [("ok", str(ok)), ("dup", str(dup)), ("gone", str(tmp_path / "missing"))],
    )
    (inbox / "gone-1.jpg").write_bytes(b"y")
    return inbox, db, dup


def test_report_lists_only_problems_and_leftovers(tmp_path: Path) -> None:
    inbox, db, _dup = _setup(tmp_path)
    results = organize_story_inbox(inbox=inbox, accounts_db=db)
    report = build_report(inbox, results)
    assert report.moved == 1
    assert {p.status for p in report.problems} == {
        StoryInboxStatus.DESTINATION_EXISTS,
        StoryInboxStatus.USERNAME_NOT_IN_DB,
        StoryInboxStatus.ACCOUNT_PATH_MISSING,
    }
    assert sorted(p.name for p in report.leftovers) == ["dup-1.jpg", "ghost-1.jpg", "gone-1.jpg"]
    assert len(report.conflicts) == 1
    assert not report.is_clean


def test_force_move_overwrites_duplicate(tmp_path: Path) -> None:
    inbox, db, dup = _setup(tmp_path)
    report = build_report(inbox, organize_story_inbox(inbox=inbox, accounts_db=db))
    forced = force_move_conflicts(list(report.conflicts), accounts_db=db)
    assert [f.status for f in forced] == [StoryInboxStatus.OVERWRITTEN]
    assert (dup / "story" / "dup-1.jpg").read_bytes() == b"new"
    assert not (inbox / "dup-1.jpg").exists()


def test_clean_report_when_everything_moved(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    acc = tmp_path / "acc"
    acc.mkdir()
    (inbox / "acc-1.jpg").write_bytes(b"a")
    db = _accounts_db(tmp_path / "a.db", [("acc", str(acc))])
    report = build_report(inbox, organize_story_inbox(inbox=inbox, accounts_db=db))
    assert report.is_clean and report.moved == 1
