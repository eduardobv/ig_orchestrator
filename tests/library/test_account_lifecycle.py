from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.account_lifecycle import AccountLifecycleService
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    for rel in ("00.FAVORITES/Group/alice", "00.FAVORITES/Group/bob", "09.DELETED/old", "00.MODELS/carol"):
        (lib / rel).mkdir(parents=True)
    (lib / "00.FAVORITES/Group/alice/a.jpg").write_bytes(b"x")
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    root = str(lib)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (root,))
    now = "2026-01-01T00:00:00"
    ids: dict[str, int] = {}

    def folder(rel: str) -> int:
        if rel in ids:
            return ids[rel]
        parent = folder(rel.rsplit("\\", 1)[0]) if "\\" in rel else (folder("") if rel else None)
        depth = len([p for p in rel.split("\\") if p])
        ids[rel] = conn.execute(
            "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at, rel_path, kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'GROUP')",
            (parent, rel.rsplit("\\", 1)[-1] or "root", root + ("\\" + rel if rel else ""), depth, now, now, rel),
        ).lastrowid
        return ids[rel]

    for rel in ("", "00.FAVORITES", "00.FAVORITES\\Group", "09.DELETED", "00.MODELS"):
        folder(rel)
    acc: dict[str, int] = {}
    for name, rel, parent, fav, owner in (
        ("alice", "00.FAVORITES\\Group\\alice", "00.FAVORITES\\Group", 1, "11"),
        ("bob", "00.FAVORITES\\Group\\bob", "00.FAVORITES\\Group", 0, "22"),
        ("carol", "00.MODELS\\carol", "00.MODELS", 0, "22"),  # same owner as bob
        ("old", "09.DELETED\\old", "09.DELETED", 0, "33"),
    ):
        acc[name] = conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, is_favorite,"
            " created_at, updated_at, rel_path) VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
            (name, owner, ids[parent], fav, now, now, rel),
        ).lastrowid
    conn.commit()
    yield AccountLifecycleService(conn), conn, lib, acc
    conn.close()


def status(conn, name: str) -> str:
    return conn.execute(
        "SELECT s.code FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id"
        " WHERE a.username = ?",
        (name,),
    ).fetchone()[0]


def test_mark_deleted_moves_folder_and_sets_status(env) -> None:
    svc, conn, lib, acc = env

    plan = svc.plan_mark_deleted([acc["alice"]])
    assert plan.can_execute and any(c.code == "WAS_FAVORITE" for c in plan.plan.conflicts)
    group = svc.execute_mark_deleted(plan)

    assert (lib / "09.DELETED/alice/a.jpg").exists() and not (lib / "00.FAVORITES/Group/alice").exists()
    row = conn.execute("SELECT * FROM catalog_accounts WHERE username = 'alice'").fetchone()
    assert row["rel_path"] == "09.DELETED\\alice" and row["previous_rel_path"] == "00.FAVORITES\\Group\\alice"
    assert row["is_favorite"] == 0 and row["deleted_at"] and status(conn, "alice") == "DELETED"
    assert group


def test_undo_restores_status_favorite_and_folder(env) -> None:
    svc, conn, lib, acc = env
    group = svc.execute_mark_deleted(svc.plan_mark_deleted([acc["alice"]]))

    FsOperationService(conn).undo(group)
    assert svc.restore_after_undo(group) == 1

    assert (lib / "00.FAVORITES/Group/alice/a.jpg").exists()
    row = conn.execute("SELECT * FROM catalog_accounts WHERE username = 'alice'").fetchone()
    assert status(conn, "alice") == "ENABLED" and row["is_favorite"] == 1
    assert row["rel_path"] == "00.FAVORITES\\Group\\alice" and row["deleted_at"] is None


def test_restore_moves_back_with_previous_status(env) -> None:
    svc, conn, lib, acc = env
    conn.execute(
        "UPDATE catalog_accounts SET status_id = (SELECT id FROM catalog_account_statuses WHERE code = 'INACTIVE')"
        " WHERE username = 'bob'"
    )
    conn.commit()
    svc.execute_mark_deleted(svc.plan_mark_deleted([acc["bob"]]))

    restore = svc.plan_restore(acc["bob"])
    assert restore.can_execute
    svc.execute_restore(restore)

    assert (lib / "00.FAVORITES/Group/bob").is_dir() and not (lib / "09.DELETED/bob").exists()
    assert status(conn, "bob") == "INACTIVE"
    assert conn.execute("SELECT previous_rel_path FROM catalog_accounts WHERE username = 'bob'").fetchone()[0] is None


def test_conflict_when_destination_exists_and_suffix_option(env) -> None:
    svc, _conn, lib, acc = env
    (lib / "09.DELETED/bob").mkdir()

    blocked = svc.plan_mark_deleted([acc["bob"]])
    assert not blocked.can_execute and blocked.plan.blocking[0].code == "DEST_EXISTS"

    svc.execute_mark_deleted(svc.plan_mark_deleted([acc["bob"]], suffix_on_conflict=True))
    assert (lib / "09.DELETED/bob_2").is_dir()


def test_owner_shared_warning_is_not_blocking(env) -> None:
    svc, _conn, _lib, acc = env

    plan = svc.plan_mark_deleted([acc["bob"]])

    warning = [c for c in plan.plan.conflicts if c.code == "OWNER_SHARED"]
    assert warning and not warning[0].blocking and "carol" in warning[0].message and plan.can_execute


def test_multi_selection_single_plan(env) -> None:
    svc, conn, _lib, acc = env

    plan = svc.plan_mark_deleted([acc["alice"], acc["bob"]])
    assert len(plan.plan.steps) == 2 and plan.plan.affected_accounts == 2
    svc.execute_mark_deleted(plan)

    assert status(conn, "alice") == status(conn, "bob") == "DELETED"


def test_missing_folder_changes_only_status(env) -> None:
    svc, conn, lib, acc = env
    shutil.rmtree(lib / "00.MODELS/carol")

    plan = svc.plan_mark_deleted([acc["carol"]])
    assert plan.can_execute and not plan.plan.steps and any(c.code == "NO_FOLDER" for c in plan.plan.conflicts)
    assert svc.execute_mark_deleted(plan) is None

    assert status(conn, "carol") == "DELETED"
    assert conn.execute("SELECT rel_path FROM catalog_accounts WHERE username = 'carol'").fetchone()[0] == "00.MODELS\\carol"


def test_active_batch_blocks(env) -> None:
    svc, conn, _lib, acc = env
    now = "2026-01-01T00:00:00"
    conn.execute(
        "INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
        " SELECT 'b', 1, id, '2026-01-01', ?, ? FROM batch_statuses WHERE code = 'PROCESSING'",
        (now, now),
    )
    batch = conn.execute("SELECT id FROM batches").fetchone()[0]
    conn.execute(
        "INSERT INTO batch_accounts (batch_id, catalog_account_id, status_id, sort_order, created_at, updated_at)"
        " SELECT ?, ?, id, 0, ?, ? FROM batch_account_statuses WHERE code = 'PENDING'",
        (batch, acc["alice"], now, now),
    )
    conn.commit()

    plan = svc.plan_mark_deleted([acc["alice"]])

    assert not plan.can_execute and plan.plan.blocking[0].code == "ACCOUNT_IN_ACTIVE_BATCH"
    with pytest.raises(FsOpsError):
        svc.execute_mark_deleted(plan)


def test_keep_group_creates_group_folder(env) -> None:
    svc, conn, lib, acc = env
    conn.execute(
        "INSERT INTO app_settings (key, value, value_type, updated_at) VALUES ('library.deleted_keep_group', '1', 'BOOLEAN', 'x')"
    )
    conn.commit()

    plan = svc.plan_mark_deleted([acc["alice"], acc["bob"]])
    svc.execute_mark_deleted(plan)

    assert (lib / "09.DELETED/Group/alice/a.jpg").exists() and (lib / "09.DELETED/Group/bob").is_dir()
    assert [s.op_type.value for s in plan.plan.steps].count("MKDIR") == 1


def test_label_existing_deleted_folder_without_moving(env) -> None:
    svc, conn, lib, acc = env

    found = svc.find_unlabeled_deleted()
    assert [r["username"] for r in found] == ["old"]
    assert svc.label_deleted([int(r["id"]) for r in found]) == 1

    assert status(conn, "old") == "DELETED" and (lib / "09.DELETED/old").is_dir()
    assert svc.find_unlabeled_deleted() == []
    assert svc.plan_restore(acc["old"]).can_execute  # no previous folder: status-only restore


def test_suggestions_need_two_batches_and_ignore_other_instance(env) -> None:
    svc, conn, _lib, acc = env
    now = "2026-01-01T00:00:00"
    status_failed = conn.execute("SELECT id FROM batch_url_statuses WHERE code = 'FAILED_FINAL'").fetchone()[0]
    ptype = conn.execute("SELECT id FROM publication_types LIMIT 1").fetchone()[0]
    source = conn.execute("SELECT id FROM url_sources LIMIT 1").fetchone()[0]
    err = conn.execute("SELECT id FROM bot_errors WHERE code = 'STORIES_NOT_FOUND'").fetchone()[0]

    def fail(name: str, batch_name: str, text: str) -> None:
        conn.execute(
            "INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
            " SELECT ?, 1, id, '2026-01-01', ?, ? FROM batch_statuses WHERE code = 'COMPLETED'",
            (batch_name, now, now),
        )
        batch = conn.execute("SELECT id FROM batches WHERE name = ?", (batch_name,)).fetchone()[0]
        ba = conn.execute(
            "INSERT INTO batch_accounts (batch_id, catalog_account_id, status_id, sort_order, created_at, updated_at)"
            " SELECT ?, ?, id, 0, ?, ? FROM batch_account_statuses WHERE code = 'FAILED'",
            (batch, acc[name], now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO batch_urls (batch_account_id, url, publication_type_id, source_id, status_id,"
            " last_error_id, last_error_text, created_at, updated_at) VALUES (?, 'u', ?, ?, ?, ?, ?, ?, ?)",
            (ba, ptype, source, status_failed, err, text, now, now),
        )

    fail("alice", "b1", "Stories for alice not found")
    fail("alice", "b2", "Stories for alice not found")
    fail("bob", "b3", "Stories for bob not found")
    fail("bob", "b4", "Executed on another instance")
    conn.commit()

    assert [(name, n) for _id, name, n in svc.suggest_deleted()] == [("alice", 2)]

