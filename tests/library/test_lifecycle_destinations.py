from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.fsops import FsOperationService


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    for rel in ("00.FAVORITES/Group/alice", "00.FAVORITES/Group/bob", "09.DELETED", "00.MODELS/carol"):
        (lib / rel).mkdir(parents=True)
    (lib / "00.FAVORITES/Group/alice/a.jpg").write_bytes(b"x")
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    for rel in ("", "00.FAVORITES", "00.FAVORITES\\Group", "09.DELETED", "00.MODELS"):
        fs.ensure_folder_rows(rel)
    # the root row is registered by ensure_folder_rows only if it exists; make sure it does
    acc: dict[str, int] = {}
    for name, rel, parent in (
        ("alice", "00.FAVORITES\\Group\\alice", "00.FAVORITES\\Group"),
        ("bob", "00.FAVORITES\\Group\\bob", "00.FAVORITES\\Group"),
        ("carol", "00.MODELS\\carol", "00.MODELS"),
    ):
        acc[name] = conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path)"
            " VALUES (?, ?, 1, 'x', 'x', ?)",
            (name, fs.folder_id_for_rel(parent), rel),
        ).lastrowid
    conn.commit()
    yield AccountLifecycleService(conn), conn, lib, acc
    conn.close()


def make_folder(conn, lib: Path, rel: str) -> None:
    (lib / rel.replace("\\", "/")).mkdir(parents=True, exist_ok=True)
    FsOperationService(conn).ensure_folder_rows(rel)
    conn.commit()


def status(conn, name: str) -> str:
    return conn.execute(
        "SELECT s.code FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id"
        " WHERE a.username = ?",
        (name,),
    ).fetchone()[0]


def test_suggests_models_own_deleted_sibling_folder(env) -> None:
    svc, conn, lib, acc = env
    make_folder(conn, lib, "00.FAVORITES\\Group-Deleted")

    assert svc.suggest_destination(acc["alice"]) == ("00.FAVORITES\\Group-Deleted", "sibling_deleted")
    svc.execute_mark_deleted(svc.plan_mark_deleted([acc["alice"]]))

    assert (lib / "00.FAVORITES/Group-Deleted/alice/a.jpg").exists()
    row = conn.execute("SELECT rel_path, folder_id FROM catalog_accounts WHERE username = 'alice'").fetchone()
    folder = conn.execute("SELECT rel_path FROM catalog_folders WHERE id = ?", (row["folder_id"],)).fetchone()[0]
    assert row["rel_path"] == "00.FAVORITES\\Group-Deleted\\alice" and folder == "00.FAVORITES\\Group-Deleted"


def test_falls_back_to_deleted_folder_without_sibling_or_group(env) -> None:
    svc, _conn, _lib, acc = env

    assert svc.suggest_destination(acc["alice"]) == ("09.DELETED", "deleted_folder")
    assert svc.suggest_destination(acc["carol"]) == ("09.DELETED", "deleted_folder")  # directly under a category


def test_account_already_in_a_deleted_group_only_changes_status(env) -> None:
    svc, conn, lib, _acc = env
    make_folder(conn, lib, "00.FAVORITES\\Group-Deleted\\zed")
    folder_id = FsOperationService(conn).folder_id_for_rel("00.FAVORITES\\Group-Deleted")
    zed = conn.execute(
        "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path)"
        " VALUES ('zed', ?, 1, 'x', 'x', '00.FAVORITES\\Group-Deleted\\zed')",
        (folder_id,),
    ).lastrowid
    conn.commit()

    plan = svc.plan_mark_deleted([zed])

    assert plan.can_execute and not plan.plan.steps and plan.actions[0].dst_rel is None


def test_custom_destination_creates_missing_folders(env) -> None:
    svc, conn, lib, acc = env

    plan = svc.plan_mark_deleted([acc["alice"]], dest_overrides={acc["alice"]: "00.FAVORITES\\NewDel\\Sub"})
    assert [s.op_type.value for s in plan.plan.steps] == ["MKDIR", "MKDIR", "MOVE_DIR"]
    assert plan.destinations[acc["alice"]] == ("00.FAVORITES\\NewDel\\Sub", "custom")
    svc.execute_mark_deleted(plan)

    assert (lib / "00.FAVORITES/NewDel/Sub/alice/a.jpg").exists()
    created = conn.execute(
        "SELECT COUNT(*) FROM catalog_folders WHERE rel_path IN ('00.FAVORITES\\NewDel', '00.FAVORITES\\NewDel\\Sub')"
    ).fetchone()[0]
    assert created == 2 and status(conn, "alice") == "DELETED"


def test_custom_destination_existing_on_disk_but_unknown_to_catalog_is_registered(env) -> None:
    svc, conn, lib, acc = env
    (lib / "04.INACTIVE").mkdir()  # exists on disk only

    svc.execute_mark_deleted(svc.plan_mark_deleted([acc["bob"]], dest_overrides={acc["bob"]: "04.INACTIVE"}))

    row = conn.execute("SELECT rel_path, folder_id FROM catalog_accounts WHERE username = 'bob'").fetchone()
    assert row["rel_path"] == "04.INACTIVE\\bob" and row["folder_id"] is not None


def test_custom_destination_validation(env) -> None:
    svc, _conn, _lib, acc = env

    bad_name = svc.plan_mark_deleted([acc["alice"]], dest_overrides={acc["alice"]: "09.DELETED\\a?b"})
    inside = svc.plan_mark_deleted([acc["alice"]], dest_overrides={acc["alice"]: "00.FAVORITES\\Group\\alice\\x"})
    same = svc.plan_mark_deleted([acc["alice"]], dest_overrides={acc["alice"]: "00.FAVORITES\\Group"})
    root = svc.plan_mark_deleted([acc["alice"]], dest_overrides={acc["alice"]: ""})

    assert not bad_name.can_execute and bad_name.plan.blocking[0].code == "BAD_DESTINATION"
    assert not inside.can_execute and inside.plan.blocking[0].code == "BAD_DESTINATION"
    assert not same.can_execute and same.plan.blocking[0].code == "NO_CHANGE"
    assert not root.can_execute


def test_different_destination_per_account(env) -> None:
    svc, conn, lib, acc = env
    make_folder(conn, lib, "00.FAVORITES\\Group-Deleted")

    plan = svc.plan_mark_deleted([acc["alice"], acc["bob"]], dest_overrides={acc["bob"]: "09.DELETED"})
    svc.execute_mark_deleted(plan)

    assert (lib / "00.FAVORITES/Group-Deleted/alice").is_dir() and (lib / "09.DELETED/bob").is_dir()
