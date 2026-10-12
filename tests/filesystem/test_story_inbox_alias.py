from __future__ import annotations

import sqlite3
from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.filesystem.story_inbox import StoryInboxStatus, organize_story_inbox, summarize_results
from ig_orchestrator.library.account_rename import AccountRenameService
from ig_orchestrator.library.fsops import FsOperationService

NOW = "2026-01-01T00:00:00"


def build(tmp_path: Path):
    lib = tmp_path / "lib"
    (lib / "00.MODELS" / "oldname").mkdir(parents=True)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    for rel in ("", "00.MODELS"):
        fs.ensure_folder_rows(rel)
    account = conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at, rel_path)"
        " VALUES ('oldname', '5', ?, 1, ?, ?, '00.MODELS\\oldname')", (fs.folder_id_for_rel("00.MODELS"), NOW, NOW)
    ).lastrowid
    conn.commit()
    return conn, lib, inbox, account


def test_story_with_old_username_goes_to_the_renamed_account(tmp_path: Path) -> None:
    conn, lib, inbox, account = build(tmp_path)
    service = AccountRenameService(conn)
    service.execute(service.plan_rename(account, "brandnew"))
    (inbox / "oldname-20260101-1.jpeg").write_bytes(b"x")

    results = organize_story_inbox(inbox=inbox, app_connection=conn)

    assert [r.status for r in results] == [StoryInboxStatus.MOVED_VIA_ALIAS]
    assert "ahora es @brandnew" in results[0].detail
    assert (lib / "00.MODELS" / "brandnew" / "story" / "oldname-20260101-1.jpeg").exists()
    assert summarize_results(results) == (1, 0)


def test_ambiguous_old_name_is_not_guessed(tmp_path: Path) -> None:
    conn, lib, inbox, account = build(tmp_path)
    service = AccountRenameService(conn)
    service.execute(service.plan_rename(account, "brandnew"))
    # another person later used the old name and then changed it too
    (lib / "00.MODELS" / "other").mkdir()
    other = conn.execute(
        "INSERT INTO catalog_accounts (username, status_id, created_at, updated_at, rel_path)"
        " VALUES ('other', 1, ?, ?, '00.MODELS\\other')", (NOW, NOW)
    ).lastrowid
    conn.execute("INSERT INTO account_usernames (catalog_account_id, username, valid_to, reason, created_at)"
                 " VALUES (?, 'oldname', '2026-02-01', 'RENAMED', ?)", (other, NOW))
    conn.commit()
    (inbox / "oldname-20260101-2.jpeg").write_bytes(b"x")

    results = organize_story_inbox(inbox=inbox, app_connection=conn)

    assert [r.status for r in results] == [StoryInboxStatus.USERNAME_NOT_IN_DB]
    assert (inbox / "oldname-20260101-2.jpeg").exists()


def test_current_username_still_moves_normally(tmp_path: Path) -> None:
    conn, lib, inbox, _account = build(tmp_path)
    (inbox / "oldname-20260101-3.jpeg").write_bytes(b"x")

    results = organize_story_inbox(inbox=inbox, app_connection=conn)

    assert [r.status for r in results] == [StoryInboxStatus.MOVED]
    _ = sqlite3
