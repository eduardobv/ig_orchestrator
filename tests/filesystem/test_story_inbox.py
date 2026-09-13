from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from ig_orchestrator.filesystem.story_inbox import (
    StoryInboxError,
    StoryInboxStatus,
    organize_story_inbox,
    summarize_results,
    username_from_story_filename,
)


def test_username_from_story_filename_uses_prefix_before_hyphen() -> None:
    name = (
        "best.slips-20260817_151729-777297818_18122891269765569_"
        "4639839616027046619_n.jpeg"
    )
    assert username_from_story_filename(name) == "best.slips"
    assert username_from_story_filename("no_hyphen.jpeg") is None
    assert username_from_story_filename("-starts-with-hyphen.jpg") is None


def _write_accounts_db(path: Path, rows: list[tuple[str, str]]) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE accounts_dir (username TEXT NOT NULL, path TEXT)"
    )
    connection.executemany(
        "INSERT INTO accounts_dir (username, path) VALUES (?, ?)", rows
    )
    connection.commit()
    connection.close()


def test_organize_story_inbox_moves_matching_media(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    account_root = tmp_path / "library" / "Marie-Dee" / "best.slips"
    account_root.mkdir(parents=True)
    source = inbox / (
        "best.slips-20260817_151729-777297818_18122891269765569_"
        "4639839616027046619_n.jpeg"
    )
    source.write_bytes(b"jpeg")
    db_path = tmp_path / "accounts.sqlite"
    _write_accounts_db(db_path, [("best.slips", str(account_root))])

    results = organize_story_inbox(inbox=inbox, accounts_db=db_path)

    dest = account_root / "story" / source.name
    assert len(results) == 1
    assert results[0].status is StoryInboxStatus.MOVED
    assert results[0].username == "best.slips"
    assert dest.is_file()
    assert not source.exists()
    assert summarize_results(results) == (1, 0)


def test_organize_story_inbox_reports_missing_username_and_path(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "orphan-20260817.jpg").write_bytes(b"x")
    (inbox / "nohyphen.jpg").write_bytes(b"x")
    (inbox / "readme.txt").write_text("skip")
    missing_root = tmp_path / "does-not-exist" / "user"
    db_path = tmp_path / "accounts.sqlite"
    _write_accounts_db(
        db_path,
        [
            ("orphan", str(missing_root)),
        ],
    )

    results = organize_story_inbox(inbox=inbox, accounts_db=db_path)
    statuses = {item.source.name: item.status for item in results}

    assert "readme.txt" not in statuses
    assert statuses["nohyphen.jpg"] is StoryInboxStatus.NO_USERNAME_IN_NAME
    assert statuses["orphan-20260817.jpg"] is StoryInboxStatus.ACCOUNT_PATH_MISSING
    assert summarize_results(results) == (0, 2)


def test_organize_story_inbox_username_not_in_db(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "unknown.user-20260817.jpg").write_bytes(b"x")
    db_path = tmp_path / "accounts.sqlite"
    _write_accounts_db(db_path, [("someone.else", str(tmp_path))])

    results = organize_story_inbox(inbox=inbox, accounts_db=db_path)

    assert results[0].status is StoryInboxStatus.USERNAME_NOT_IN_DB
    assert (inbox / "unknown.user-20260817.jpg").is_file()


def test_organize_story_inbox_does_not_overwrite(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    account_root = tmp_path / "account"
    story = account_root / "story"
    story.mkdir(parents=True)
    name = "alpha-20260817.jpg"
    (inbox / name).write_bytes(b"new")
    (story / name).write_bytes(b"old")
    db_path = tmp_path / "accounts.sqlite"
    _write_accounts_db(db_path, [("alpha", str(account_root))])

    results = organize_story_inbox(inbox=inbox, accounts_db=db_path)

    assert results[0].status is StoryInboxStatus.DESTINATION_EXISTS
    assert (inbox / name).read_bytes() == b"new"
    assert (story / name).read_bytes() == b"old"


def test_organize_story_inbox_requires_paths(tmp_path: Path) -> None:
    with pytest.raises(StoryInboxError, match="Stories folder"):
        organize_story_inbox(inbox=tmp_path / "missing", accounts_db=tmp_path / "x.sqlite")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    with pytest.raises(StoryInboxError, match="Accounts database"):
        organize_story_inbox(inbox=inbox, accounts_db=tmp_path / "missing.sqlite")


def test_organize_story_inbox_requires_accounts_dir_table(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "user-1.jpg").write_bytes(b"x")
    db_path = tmp_path / "empty.sqlite"
    sqlite3.connect(db_path).close()

    with pytest.raises(StoryInboxError, match="accounts_dir"):
        organize_story_inbox(inbox=inbox, accounts_db=db_path)
