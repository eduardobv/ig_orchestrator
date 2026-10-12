from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library import fsops as fsops_module
from ig_orchestrator.library.compat_lite import mirror_to_lite
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError
from ig_orchestrator.library.fsops_plan import validate_name


@pytest.fixture()
def env(tmp_path: Path):
    """A tiny library on disk + matching bdapp rows."""

    lib = tmp_path / "4K Stogram"
    for rel in ("00.FAVORITES/Group/alice", "00.FAVORITES/Group/bob", "04.INACTIVE", "00.MODELS-A/carol"):
        (lib / rel).mkdir(parents=True)
    (lib / "00.FAVORITES/Group/alice/story").mkdir()
    (lib / "00.FAVORITES/Group/alice/story/a.jpg").write_bytes(b"x")

    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    root = str(lib)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (root,))
    now = "2026-01-01T00:00:00"
    folders: dict[str, int] = {}

    def folder(rel: str) -> int:
        if rel in folders:
            return folders[rel]
        parent = folder(rel.rsplit("\\", 1)[0]) if "\\" in rel else (folder("") if rel else None)
        depth = len([p for p in rel.split("\\") if p])
        cursor = conn.execute(
            "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at,"
            " rel_path, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (parent, rel.rsplit("\\", 1)[-1] or "root", root + ("\\" + rel if rel else ""), depth, now, now,
             rel, "CATEGORY" if depth == 1 else "GROUP"),
        )
        folders[rel] = int(cursor.lastrowid)
        return folders[rel]

    for rel in ("", "00.FAVORITES", "00.FAVORITES\\Group", "04.INACTIVE", "00.MODELS-A"):
        folder(rel)
    accounts: dict[str, int] = {}
    for name, rel, parent in (
        ("alice", "00.FAVORITES\\Group\\alice", "00.FAVORITES\\Group"),
        ("bob", "00.FAVORITES\\Group\\bob", "00.FAVORITES\\Group"),
        ("carol", "00.MODELS-A\\carol", "00.MODELS-A"),
    ):
        cursor = conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path,"
            " legacy_lite_id) VALUES (?, ?, 1, ?, ?, ?, ?)",
            (name, folders[parent], now, now, rel, len(accounts) + 1),
        )
        accounts[name] = int(cursor.lastrowid)
    conn.commit()
    service = FsOperationService(conn)
    yield service, conn, lib, folders, accounts
    conn.close()


def rel_of(conn, username: str) -> str:
    return conn.execute("SELECT rel_path FROM catalog_accounts WHERE username = ?", (username,)).fetchone()[0]


def test_validate_name() -> None:
    assert validate_name("Maria-Perez") is None
    assert validate_name("") and validate_name(" x") and validate_name("x.") and validate_name("a/b")
    assert validate_name("CON") and validate_name("nul.txt") and validate_name('a"b')


def test_mkdir_creates_folder_on_disk_and_in_catalog(env) -> None:
    service, conn, lib, folders, _ = env

    group = service.execute(service.plan_mkdir(folders["00.FAVORITES"], "Maria-Perez"))

    assert (lib / "00.FAVORITES" / "Maria-Perez").is_dir()
    row = conn.execute("SELECT * FROM catalog_folders WHERE rel_path = ?", ("00.FAVORITES\\Maria-Perez",)).fetchone()
    assert row["parent_id"] == folders["00.FAVORITES"] and row["depth"] == 2
    assert row["full_path"] == str(lib) + "\\00.FAVORITES\\Maria-Perez"
    assert conn.execute("SELECT status FROM fs_operations WHERE op_group = ?", (group,)).fetchone()[0] == "COMMITTED"


def test_mkdir_conflicts(env) -> None:
    service, _, lib, folders, _ = env
    assert service.plan_mkdir(folders["00.FAVORITES"], "Group").blocking[0].code == "DEST_EXISTS"
    assert service.plan_mkdir(folders["00.FAVORITES"], "a?b").blocking[0].code == "INVALID_NAME"


def test_move_account_updates_disk_and_db(env) -> None:
    service, conn, lib, folders, accounts = env

    plan = service.plan_move_account(accounts["alice"], folders["04.INACTIVE"])
    assert plan.can_execute and plan.affected_accounts == 1
    service.execute(plan)

    assert not (lib / "00.FAVORITES/Group/alice").exists()
    assert (lib / "04.INACTIVE/alice/story/a.jpg").exists()
    row = conn.execute("SELECT rel_path, folder_id FROM catalog_accounts WHERE id = ?", (accounts["alice"],)).fetchone()
    assert (row["rel_path"], row["folder_id"]) == ("04.INACTIVE\\alice", folders["04.INACTIVE"])


def test_move_account_onto_existing_is_a_conflict_and_changes_nothing(env) -> None:
    service, conn, lib, folders, accounts = env
    (lib / "04.INACTIVE" / "alice").mkdir()

    plan = service.plan_move_account(accounts["alice"], folders["04.INACTIVE"])

    assert not plan.can_execute and plan.blocking[0].code == "DEST_EXISTS"
    with pytest.raises(FsOpsError):
        service.execute(plan)
    assert (lib / "00.FAVORITES/Group/alice/story/a.jpg").exists()
    assert rel_of(conn, "alice") == "00.FAVORITES\\Group\\alice"


def test_rename_folder_updates_descendants(env) -> None:
    service, conn, lib, folders, accounts = env

    service.execute(service.plan_rename_folder(folders["00.FAVORITES\\Group"], "Renamed"))

    assert (lib / "00.FAVORITES/Renamed/alice").is_dir()
    assert rel_of(conn, "alice") == "00.FAVORITES\\Renamed\\alice"
    assert rel_of(conn, "bob") == "00.FAVORITES\\Renamed\\bob"
    row = conn.execute("SELECT * FROM catalog_folders WHERE id = ?", (folders["00.FAVORITES\\Group"],)).fetchone()
    assert (row["name"], row["rel_path"]) == ("Renamed", "00.FAVORITES\\Renamed")
    assert row["full_path"] == str(lib) + "\\00.FAVORITES\\Renamed"
    assert conn.execute("SELECT id FROM catalog_accounts WHERE username = 'alice'").fetchone()[0] == accounts["alice"]


def test_rename_case_only(env) -> None:
    service, conn, lib, folders, _ = env

    service.execute(service.plan_rename_folder(folders["00.FAVORITES\\Group"], "GROUP"))

    assert "GROUP" in os.listdir(lib / "00.FAVORITES")
    assert rel_of(conn, "alice") == "00.FAVORITES\\GROUP\\alice"


def test_move_folder_moves_whole_subtree(env) -> None:
    service, conn, lib, folders, _ = env

    service.execute(service.plan_move_folder(folders["00.FAVORITES\\Group"], folders["04.INACTIVE"]))

    assert (lib / "04.INACTIVE/Group/bob").is_dir()
    assert rel_of(conn, "bob") == "04.INACTIVE\\Group\\bob"
    parent = conn.execute("SELECT parent_id FROM catalog_folders WHERE id = ?", (folders["00.FAVORITES\\Group"],)).fetchone()[0]
    assert parent == folders["04.INACTIVE"]


def test_cannot_move_folder_into_itself_or_rename_root(env) -> None:
    service, _, _, folders, _ = env
    assert service.plan_move_folder(folders["00.FAVORITES"], folders["00.FAVORITES\\Group"]).blocking[0].code == "INTO_ITSELF"
    assert service.plan_rename_folder(folders[""], "x").blocking[0].code == "IS_ROOT"


def test_no_change_and_busy_account(env) -> None:
    service, conn, _, folders, accounts = env
    assert service.plan_move_account(accounts["alice"], folders["00.FAVORITES\\Group"]).blocking[0].code == "NO_CHANGE"
    now = "2026-01-01T00:00:00"
    conn.execute("INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
                 " SELECT 'b', 1, id, '2026-01-01', ?, ? FROM batch_statuses WHERE code = 'PROCESSING'", (now, now))
    batch_id = conn.execute("SELECT id FROM batches").fetchone()[0]
    conn.execute("INSERT INTO batch_accounts (batch_id, catalog_account_id, status_id, sort_order, created_at, updated_at)"
                 " SELECT ?, ?, id, 0, ?, ? FROM batch_account_statuses WHERE code = 'PENDING'",
                 (batch_id, accounts["alice"], now, now))
    conn.commit()

    plan = service.plan_move_account(accounts["alice"], folders["04.INACTIVE"])

    assert any(c.code == "ACCOUNT_IN_ACTIVE_BATCH" for c in plan.blocking)


def test_offline_library_blocks_everything(env) -> None:
    service, conn, lib, folders, accounts = env
    offline = FsOperationService(conn, root=str(lib) + "_gone")

    plan = offline.plan_move_account(accounts["alice"], folders["04.INACTIVE"])

    assert not offline.is_online() and plan.blocking[0].code == "OFFLINE"


def test_undo_restores_disk_and_db(env) -> None:
    service, conn, lib, folders, accounts = env
    group = service.execute(service.plan_move_account(accounts["alice"], folders["04.INACTIVE"]))

    assert service.can_undo(group)[0]
    service.undo(group)

    assert (lib / "00.FAVORITES/Group/alice/story/a.jpg").exists()
    assert not (lib / "04.INACTIVE/alice").exists()
    row = conn.execute("SELECT rel_path, folder_id FROM catalog_accounts WHERE id = ?", (accounts["alice"],)).fetchone()
    assert (row["rel_path"], row["folder_id"]) == ("00.FAVORITES\\Group\\alice", folders["00.FAVORITES\\Group"])
    assert not service.can_undo(group)[0]  # already undone


def test_undo_mkdir_removes_empty_folder_and_refuses_when_not_empty(env) -> None:
    service, conn, lib, folders, _ = env
    group = service.execute(service.plan_mkdir(folders["00.FAVORITES"], "Temp"))
    (lib / "00.FAVORITES" / "Temp" / "f.txt").write_text("x")
    assert not service.can_undo(group)[0]
    (lib / "00.FAVORITES" / "Temp" / "f.txt").unlink()

    service.undo(group)

    assert not (lib / "00.FAVORITES" / "Temp").exists()
    assert conn.execute("SELECT COUNT(*) FROM catalog_folders WHERE rel_path = '00.FAVORITES\\Temp'").fetchone()[0] == 0


def test_recover_completes_db_after_crash_between_disk_and_commit(env, monkeypatch) -> None:
    service, conn, lib, folders, accounts = env
    plan = service.plan_move_account(accounts["alice"], folders["04.INACTIVE"])

    def boom(*_args, **_kwargs):
        raise RuntimeError("process killed")

    monkeypatch.setattr(service, "_apply_db", boom)
    with pytest.raises(RuntimeError):
        service.execute(plan)
    monkeypatch.undo()
    assert (lib / "04.INACTIVE/alice").exists()
    assert rel_of(conn, "alice") == "00.FAVORITES\\Group\\alice"  # DB still old
    assert conn.execute("SELECT status FROM fs_operations").fetchone()[0] == "DISK_DONE"

    messages = FsOperationService(conn).recover()

    assert len(messages) == 1 and "Completada" in messages[0]
    assert rel_of(conn, "alice") == "04.INACTIVE\\alice"
    assert conn.execute("SELECT status FROM fs_operations").fetchone()[0] == "COMMITTED"


def test_recover_marks_unexecuted_planned_as_failed(env) -> None:
    service, conn, lib, folders, accounts = env
    service._insert_op("g", 1, service.plan_move_account(accounts["alice"], folders["04.INACTIVE"]).steps[0])

    messages = service.recover()

    assert "Descartada" in messages[0]
    assert conn.execute("SELECT status FROM fs_operations").fetchone()[0] == "FAILED"
    assert (lib / "00.FAVORITES/Group/alice").exists()


def test_second_operation_in_progress_is_rejected(env) -> None:
    service, _, _, folders, _ = env
    plan = service.plan_mkdir(folders["00.FAVORITES"], "X")
    assert fsops_module._LOCK.acquire(blocking=False)
    try:
        with pytest.raises(FsOpsError, match="otra operacion"):
            service.execute(plan)
    finally:
        fsops_module._LOCK.release()


def test_history_groups_operations(env) -> None:
    service, _, _, folders, accounts = env
    service.execute(service.plan_mkdir(folders["00.FAVORITES"], "H1"))
    service.execute(service.plan_move_account(accounts["alice"], folders["04.INACTIVE"]))

    rows = service.history()

    assert len(rows) == 2 and rows[0]["op_types"] == "MOVE_DIR"


def test_mirror_to_lite_updates_only_changed_rows(env, tmp_path: Path) -> None:
    service, conn, lib, folders, accounts = env
    lite = tmp_path / "accounts_lite.sqlite"
    root = str(lib)
    with sqlite3.connect(lite) as db:
        db.execute("CREATE TABLE accounts_dir (id INTEGER PRIMARY KEY, username TEXT, path TEXT)")
        db.executemany("INSERT INTO accounts_dir VALUES (?,?,?)", [
            (1, "alice", root + "\\00.FAVORITES\\Group\\alice"),
            (2, "bob", root + "\\00.FAVORITES\\Group\\bob"),
            (3, "carol", root + "\\00.MODELS-A\\carol"),
        ])
    service.execute(service.plan_move_account(accounts["alice"], folders["04.INACTIVE"]))

    changed = mirror_to_lite(conn, lite, root)

    assert changed == 1
    with sqlite3.connect(lite) as db:
        paths = dict(db.execute("SELECT username, path FROM accounts_dir"))
    assert paths["alice"] == root + "\\04.INACTIVE\\alice"
    assert paths["bob"].endswith("Group\\bob")
    assert mirror_to_lite(conn, lite, root) == 0  # idempotent
