from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K"
    for rel in ("10.TEMP", "00.FAV\\Ana-Model"):
        (lib / rel).mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    for rel in ("10.TEMP", "00.FAV\\Ana-Model"):
        fs.ensure_folder_rows(rel)
    yield conn, fs, lib
    conn.close()


def folder_id(fs: FsOperationService, rel: str) -> int:
    found = fs.folder_id_for_rel(rel)
    assert found is not None
    return found


def test_empty_folder_is_deleted_from_disk_and_catalog_and_can_be_undone(env) -> None:
    conn, fs, lib = env
    (lib / "10.TEMP" / "susana").mkdir()
    fid = fs.ensure_folder_rows("10.TEMP\\susana")

    plan = fs.plan_delete_empty_folder(fid)

    assert plan.can_execute and [s.src_rel for s in plan.steps] == ["10.TEMP\\susana"]
    group = fs.execute(plan)
    assert not (lib / "10.TEMP" / "susana").exists()
    assert conn.execute("SELECT 1 FROM catalog_folders WHERE rel_path = '10.TEMP\\susana'").fetchone() is None

    fs.undo(group)
    assert (lib / "10.TEMP" / "susana").is_dir() and fs.folder_id_for_rel("10.TEMP\\susana") is not None


def test_nested_empty_folders_are_removed_deepest_first(env) -> None:
    _conn, fs, lib = env
    (lib / "10.TEMP" / "a" / "b" / "c").mkdir(parents=True)
    fid = fs.ensure_folder_rows("10.TEMP\\a")
    fs.ensure_folder_rows("10.TEMP\\a\\b\\c")

    plan = fs.plan_delete_empty_folder(fid)

    assert [s.src_rel for s in plan.steps] == ["10.TEMP\\a\\b\\c", "10.TEMP\\a\\b", "10.TEMP\\a"]
    group = fs.execute(plan)
    assert not (lib / "10.TEMP" / "a").exists()
    fs.undo(group)
    assert (lib / "10.TEMP" / "a" / "b" / "c").is_dir()


def test_folder_with_files_is_blocked(env) -> None:
    _conn, fs, lib = env
    (lib / "10.TEMP" / "x").mkdir()
    (lib / "10.TEMP" / "x" / "photo.jpg").write_bytes(b"1")
    fid = fs.ensure_folder_rows("10.TEMP\\x")

    plan = fs.plan_delete_empty_folder(fid)

    assert not plan.can_execute and plan.blocking[0].code == "NOT_EMPTY" and "photo.jpg" in plan.blocking[0].message
    with pytest.raises(FsOpsError):
        fs.execute(plan)
    assert (lib / "10.TEMP" / "x" / "photo.jpg").exists()


def test_folder_with_an_account_is_blocked_even_if_the_account_folder_is_empty(env) -> None:
    conn, fs, lib = env
    (lib / "00.FAV" / "Ana-Model" / "ana1").mkdir()
    conn.execute(
        "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path) VALUES"
        " ('ana1', ?, 1, 'x', 'x', '00.FAV\\Ana-Model\\ana1')", (folder_id(fs, "00.FAV\\Ana-Model"),))
    conn.commit()

    plan = fs.plan_delete_empty_folder(folder_id(fs, "00.FAV\\Ana-Model"))

    assert not plan.can_execute and plan.blocking[0].code == "HAS_ACCOUNTS" and "@ana1" in plan.blocking[0].message


def test_library_root_and_offline_are_refused(env) -> None:
    _conn, fs, lib = env
    root_id = fs.conn.execute("SELECT id FROM catalog_folders WHERE parent_id IS NULL").fetchone()
    if root_id is not None:
        assert fs.plan_delete_empty_folder(int(root_id[0])).blocking[0].code == "IS_ROOT"
    (lib / "10.TEMP" / "z").mkdir()
    fid = fs.ensure_folder_rows("10.TEMP\\z")
    lib.rename(lib.parent / "off")
    assert fs.plan_delete_empty_folder(fid).blocking[0].code == "OFFLINE"
