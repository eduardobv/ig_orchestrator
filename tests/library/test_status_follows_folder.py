from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.fsops import FsOperationService


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K"
    for rel in ("00.FAV\\Ana-Model", "00.FAV\\Ana-Model-Deleted", "00.FAV\\Ana-Model-Inactive", "09.DELETED"):
        (lib / rel).mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    for rel in ("00.FAV\\Ana-Model", "00.FAV\\Ana-Model-Deleted", "00.FAV\\Ana-Model-Inactive", "09.DELETED"):
        fs.ensure_folder_rows(rel)

    def account(name: str, parent: str, status: int = 1) -> int:
        (lib / parent / name).mkdir()
        return int(conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path) VALUES (?, ?, ?, 'x', 'x', ?)",
            (name, fs.folder_id_for_rel(parent), status, f"{parent}\\{name}")).lastrowid)

    yield conn, fs, lifecycle_of(conn), account, lib
    conn.close()


def lifecycle_of(conn):
    return AccountLifecycleService(conn)


def status(conn, account_id: int) -> str:
    return conn.execute("SELECT s.code FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id WHERE a.id = ?", (account_id,)).fetchone()[0]


def move(fs, lifecycle, account_id: int, dest: str):
    plan = fs.plan_move_account(account_id, fs.folder_id_for_rel(dest))
    preview = lifecycle.preview_status_changes(plan)
    group = fs.execute(plan)
    messages = lifecycle.sync_with_location(lifecycle.affected_accounts(group), group)
    return group, preview, messages


def test_moving_into_a_deleted_folder_marks_the_account_deleted(env) -> None:
    conn, fs, lifecycle, account, _lib = env
    aid = account("ana1", "00.FAV\\Ana-Model", status=2)  # inactive

    _group, preview, messages = move(fs, lifecycle, aid, "00.FAV\\Ana-Model-Deleted")

    assert preview == [(aid, "ana1", "DELETE")] and "marcada como eliminada" in messages[0]
    row = conn.execute("SELECT status_id, previous_rel_path, deleted_at FROM catalog_accounts WHERE id = ?", (aid,)).fetchone()
    assert status(conn, aid) == "DELETED" and row["previous_rel_path"] == "00.FAV\\Ana-Model\\ana1" and row["deleted_at"]


def test_moving_out_of_a_deleted_folder_reactivates_to_the_previous_status(env) -> None:
    conn, fs, lifecycle, account, _lib = env
    aid = account("ana2", "00.FAV\\Ana-Model", status=2)
    move(fs, lifecycle, aid, "00.FAV\\Ana-Model-Deleted")

    _g, preview, messages = move(fs, lifecycle, aid, "00.FAV\\Ana-Model")

    assert preview == [(aid, "ana2", "ACTIVATE")] and "reactivada" in messages[0]
    assert status(conn, aid) == "INACTIVE"  # the status it had before, not a blind ENABLED
    assert conn.execute("SELECT deleted_at FROM catalog_accounts WHERE id = ?", (aid,)).fetchone()[0] is None


def test_moving_between_normal_folders_changes_nothing(env) -> None:
    conn, fs, lifecycle, account, _lib = env
    aid = account("ana3", "00.FAV\\Ana-Model")

    _g, preview, messages = move(fs, lifecycle, aid, "00.FAV\\Ana-Model-Inactive")

    assert preview == [] and messages == [] and status(conn, aid) == "ENABLED"


def test_the_configured_deleted_folder_counts_and_already_deleted_is_kept(env) -> None:
    conn, fs, lifecycle, account, _lib = env
    aid = account("ana4", "00.FAV\\Ana-Model")
    move(fs, lifecycle, aid, "09.DELETED")
    assert status(conn, aid) == "DELETED"
    other = account("ana5", "00.FAV\\Ana-Model-Deleted", status=6)

    _g, preview, messages = move(fs, lifecycle, other, "09.DELETED")

    assert preview == [] and messages == [] and status(conn, other) == "DELETED"


def test_undoing_the_move_restores_the_status(env) -> None:
    conn, fs, lifecycle, account, _lib = env
    aid = account("ana6", "00.FAV\\Ana-Model", status=2)
    group, _p, _m = move(fs, lifecycle, aid, "00.FAV\\Ana-Model-Deleted")

    undo_group = fs.undo(group)
    lifecycle.restore_after_undo(group)
    lifecycle.sync_with_location(lifecycle.affected_accounts(undo_group), undo_group)

    assert status(conn, aid) == "INACTIVE"
    # and undoing the "reactivation" puts it back as deleted
    group2, _p, _m = move(fs, lifecycle, aid, "00.FAV\\Ana-Model-Deleted")
    group3, _p, _m = move(fs, lifecycle, aid, "00.FAV\\Ana-Model")
    assert status(conn, aid) == "INACTIVE"
    undo3 = fs.undo(group3)
    lifecycle.restore_after_undo(group3)
    lifecycle.sync_with_location(lifecycle.affected_accounts(undo3), undo3)
    assert status(conn, aid) == "DELETED" and group2


def test_moving_a_whole_group_folder_into_a_deleted_folder(env) -> None:
    conn, fs, lifecycle, account, lib = env
    (lib / "00.FAV" / "Ana-Model-Inactive" / "box").mkdir()
    fs.ensure_folder_rows("00.FAV\\Ana-Model-Inactive\\box")
    a1 = account("ana7", "00.FAV\\Ana-Model")
    plan = fs.plan_move_folder(fs.folder_id_for_rel("00.FAV\\Ana-Model-Inactive\\box"), fs.folder_id_for_rel("00.FAV\\Ana-Model-Deleted"))
    assert lifecycle.preview_status_changes(plan) == []  # empty folder: no accounts involved
    assert status(conn, a1) == "ENABLED"
