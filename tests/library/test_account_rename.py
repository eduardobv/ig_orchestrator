from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library import merge as merge_module
from ig_orchestrator.library.account_rename import MERGE, SIMPLE, STATUS_ONLY, AccountRenameService
from ig_orchestrator.library.fsops import FsOperationService, FsOpsError

NOW = "2026-01-01T00:00:00"


def media(day: str, media_id: int, owner: int = 1, ext: str = "jpg") -> str:
    return f"{day} 10.00.00 {media_id}_{owner}.{ext}"


def put(lib: Path, rel: str, name: str, data: bytes) -> None:
    target = lib / rel.replace("\\", "/") / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    for rel in ("00.FAVORITES/Group/oldname", "00.FAVORITES/Group/newname", "00.MODELS/other"):
        (lib / rel).mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    for rel in ("", "00.FAVORITES", "00.FAVORITES\\Group", "00.MODELS"):
        fs.ensure_folder_rows(rel)
    acc: dict[str, int] = {}
    for name, rel, parent, owner, posts in (
        ("oldname", "00.FAVORITES\\Group\\oldname", "00.FAVORITES\\Group", "777", 10),
        ("newname", "00.FAVORITES\\Group\\newname", "00.FAVORITES\\Group", "777", 3),
        ("other", "00.MODELS\\other", "00.MODELS", "999", 1),
    ):
        acc[name] = conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at,"
            " rel_path, posts_count, last_media_at) VALUES (?, ?, ?, 1, ?, ?, ?, ?, '2026-01-01')",
            (name, owner, fs.folder_id_for_rel(parent), NOW, NOW, rel, posts),
        ).lastrowid
    conn.commit()
    yield AccountRenameService(conn), conn, lib, acc
    conn.close()


def add_batch(conn, name: str, status: str, account_id: int, urls: list[str]) -> int:
    batch = conn.execute(
        "INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
        " SELECT ?, '1.0', id, '2026-01-01', ?, ? FROM batch_statuses WHERE code = ?", (name, NOW, NOW, status)
    ).lastrowid
    ba = conn.execute(
        "INSERT INTO batch_accounts (batch_id, catalog_account_id, status_id, sort_order, created_at, updated_at)"
        " SELECT ?, ?, id, 0, ?, ? FROM batch_account_statuses WHERE code = 'PENDING'", (batch, account_id, NOW, NOW)
    ).lastrowid
    for url in urls:
        conn.execute(
            "INSERT INTO batch_urls (batch_account_id, url, publication_type_id, source_id, status_id, created_at, updated_at)"
            " SELECT ?, ?, (SELECT id FROM publication_types LIMIT 1), (SELECT id FROM url_sources LIMIT 1),"
            " (SELECT id FROM batch_url_statuses WHERE code='PENDING'), ?, ?", (ba, url, NOW, NOW))
    conn.commit()
    return ba


def aliases(conn, account_id: int) -> list[tuple[str, str | None, str]]:
    return [
        (r["username"], r["valid_to"], r["reason"])
        for r in conn.execute(
            "SELECT username, valid_to, reason FROM account_usernames WHERE catalog_account_id = ? ORDER BY id",
            (account_id,),
        )
    ]


# ------------------------------------------------------------------- merge.py
def test_merge_engine_classifies_every_file(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    put(tmp_path, "src", media("2026-01-01", 1), b"aa")           # identical in dst
    put(tmp_path, "dst", media("2026-01-01", 1), b"aa")
    put(tmp_path, "src", media("2026-01-02", 2), b"bbbb")         # same name, other size
    put(tmp_path, "dst", media("2026-01-02", 2), b"b")
    put(tmp_path, "src", media("2026-01-03", 3), b"c")            # same media id, other date -> duplicate
    put(tmp_path, "dst", media("2026-02-03", 3), b"c")
    put(tmp_path, "src", media("2026-01-04", 4), b"d")            # plain move
    put(tmp_path, "src/story", media("2026-01-05", 5), b"e")      # keeps its sub-folder

    plan = merge_module.plan_merge(src, dst)
    assert [plan.count(k) for k in ("MOVED", "IDENTICAL", "DUPLICATE", "SUFFIXED")] == [2, 1, 1, 1]
    report = merge_module.execute_merge(src, dst)

    assert not src.exists()
    assert (dst / "story" / media("2026-01-05", 5)).exists()
    assert (dst / "_duplicates" / media("2026-01-03", 3)).exists()
    assert (dst / media("2026-01-02", 2).replace(".jpg", "_1.jpg")).read_bytes() == b"bbbb"
    assert (dst / media("2026-01-02", 2)).read_bytes() == b"b"  # nothing was overwritten
    assert report.total == 5


def test_merge_engine_undo_restores_everything(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    put(tmp_path, "src", media("2026-01-01", 1), b"aa")
    put(tmp_path, "dst", media("2026-01-01", 1), b"aa")
    put(tmp_path, "src", media("2026-01-04", 4), b"d")
    report = merge_module.execute_merge(src, dst)

    ok, _ = merge_module.can_undo(report, src, dst)
    assert ok
    merge_module.undo_merge(report, src, dst)

    assert (src / media("2026-01-01", 1)).read_bytes() == b"aa"  # identical copy recreated from the survivor
    assert (src / media("2026-01-04", 4)).exists() and not (dst / media("2026-01-04", 4)).exists()
    (dst / media("2026-01-04", 4)).write_bytes(b"x")
    assert not merge_module.can_undo(report, src, dst)[0]  # something already moved again


# ---------------------------------------------------------------- simple rename
def test_simple_rename_keeps_the_primary_key_and_records_aliases(env) -> None:
    svc, conn, lib, acc = env
    put(lib, "00.FAVORITES\\Group\\oldname", media("2026-01-01", 1), b"x")
    ba = add_batch(conn, "draft", "DRAFT", acc["oldname"], ["https://www.instagram.com/stories/oldname/", "https://www.instagram.com/p/AAA/"])

    plan = svc.plan_rename(acc["oldname"], "brandnew")
    assert plan.scenario == SIMPLE and plan.can_execute and plan.rewrite_urls == 1
    group = svc.execute(plan)

    assert (lib / "00.FAVORITES/Group/brandnew" / media("2026-01-01", 1)).exists()
    assert not (lib / "00.FAVORITES/Group/oldname").exists()
    row = conn.execute("SELECT id, username, rel_path FROM catalog_accounts WHERE id = ?", (acc["oldname"],)).fetchone()
    assert (row["username"], row["rel_path"]) == ("brandnew", "00.FAVORITES\\Group\\brandnew")
    history = aliases(conn, acc["oldname"])
    assert history[0][0] == "oldname" and history[0][1] is not None  # closed today
    assert history[-1][0] == "brandnew" and history[-1][1] is None and history[-1][2] == "RENAMED"
    urls = [r[0] for r in conn.execute("SELECT url FROM batch_urls WHERE batch_account_id = ?", (ba,))]
    assert "https://www.instagram.com/stories/brandnew/" in urls and "https://www.instagram.com/p/AAA/" in urls
    assert svc.resolve_alias("oldname") == [(acc["oldname"], "brandnew")]
    assert group


def test_simple_rename_undo_restores_name_aliases_and_urls(env) -> None:
    svc, conn, lib, acc = env
    ba = add_batch(conn, "draft", "DRAFT", acc["oldname"], ["https://www.instagram.com/stories/oldname/"])
    group = svc.execute(svc.plan_rename(acc["oldname"], "brandnew"))

    assert svc.undo_blocker(group) == ""
    FsOperationService(conn).undo(group)
    svc.restore_after_undo(group)

    assert (lib / "00.FAVORITES/Group/oldname").is_dir() and not (lib / "00.FAVORITES/Group/brandnew").exists()
    assert conn.execute("SELECT username, rel_path FROM catalog_accounts WHERE id = ?", (acc["oldname"],)).fetchone()[0] == "oldname"
    assert aliases(conn, acc["oldname"]) == [("oldname", None, "INITIAL")]
    assert conn.execute("SELECT url FROM batch_urls WHERE batch_account_id = ?", (ba,)).fetchone()[0].endswith("/stories/oldname/")


def test_case_only_rename(env) -> None:
    svc, conn, lib, acc = env

    svc.execute(svc.plan_rename(acc["other"], "Other"))

    assert "Other" in [p.name for p in (lib / "00.MODELS").iterdir()]
    assert conn.execute("SELECT username FROM catalog_accounts WHERE id = ?", (acc["other"],)).fetchone()[0] == "Other"


def test_rename_validation_and_status_only(env) -> None:
    svc, conn, lib, acc = env

    assert svc.plan_rename(acc["other"], "bad name!").plan.blocking[0].code == "INVALID_USERNAME"
    assert svc.plan_rename(acc["other"], "other").plan.blocking[0].code == "NO_CHANGE"
    import shutil

    shutil.rmtree(lib / "00.MODELS/other")
    plan = svc.plan_rename(acc["other"], "other2")
    assert plan.scenario == STATUS_ONLY and plan.can_execute and not plan.plan.steps
    svc.execute(plan)
    assert conn.execute("SELECT username FROM catalog_accounts WHERE id = ?", (acc["other"],)).fetchone()[0] == "other2"


# ------------------------------------------------------------------------ merge
def test_merge_keeps_the_account_with_more_content_and_loses_nothing(env) -> None:
    svc, conn, lib, acc = env
    put(lib, "00.FAVORITES\\Group\\oldname", media("2026-01-01", 1), b"aa")
    put(lib, "00.FAVORITES\\Group\\newname", media("2026-01-01", 1), b"aa")      # identical
    put(lib, "00.FAVORITES\\Group\\oldname", media("2026-01-02", 2), b"22")
    put(lib, "00.FAVORITES\\Group\\newname", media("2026-02-02", 2), b"22")      # same media id
    put(lib, "00.FAVORITES\\Group\\oldname\\story", media("2026-01-03", 3), b"33")
    before = 3 + 2

    plan = svc.plan_rename(acc["oldname"], "newname")
    assert plan.scenario == MERGE and plan.can_execute
    assert plan.survivor_id == acc["oldname"] and plan.removed_id == acc["newname"]  # oldname has more content
    # survivor = oldname (keeps its folder), the other folder is merged into it and then it is renamed
    assert [s.op_type.value for s in plan.plan.steps] == ["MERGE_DIR", "RENAME_DIR"]
    svc.execute(plan)

    final = lib / "00.FAVORITES/Group/newname"
    files = sorted(p.relative_to(final).as_posix() for p in final.rglob("*") if p.is_file())
    assert len(files) == 4  # 5 files - 1 identical removed
    assert any(f.startswith("_duplicates/") for f in files)
    assert not (lib / "00.FAVORITES/Group/oldname").exists()
    assert conn.execute("SELECT COUNT(*) FROM catalog_accounts WHERE username = 'newname'").fetchone()[0] == 1
    row = conn.execute("SELECT * FROM catalog_accounts WHERE id = ?", (acc["oldname"],)).fetchone()
    assert (row["username"], row["posts_count"]) == ("newname", 13)
    assert conn.execute("SELECT COUNT(*) FROM catalog_accounts WHERE id = ?", (acc["newname"],)).fetchone()[0] == 0
    assert before - 1 == len(files)


def test_merge_repoints_batches_and_merges_rows_of_the_same_batch(env) -> None:
    svc, conn, lib, acc = env
    put(lib, "00.FAVORITES\\Group\\oldname", media("2026-01-01", 1), b"aa")
    ba_removed = add_batch(conn, "only_new", "COMPLETED", acc["newname"], ["https://www.instagram.com/p/NEW/"])
    shared_old = add_batch(conn, "shared", "COMPLETED", acc["oldname"], ["https://www.instagram.com/p/A/"])
    conn.execute("INSERT INTO batch_accounts (batch_id, catalog_account_id, status_id, sort_order, created_at, updated_at)"
                 " SELECT batch_id, ?, status_id, 1, ?, ? FROM batch_accounts WHERE id = ?",
                 (acc["newname"], NOW, NOW, shared_old))
    twin = conn.execute("SELECT id FROM batch_accounts WHERE catalog_account_id = ? AND batch_id = (SELECT batch_id FROM batch_accounts WHERE id = ?)",
                        (acc["newname"], shared_old)).fetchone()[0]
    conn.execute("INSERT INTO batch_urls (batch_account_id, url, publication_type_id, source_id, status_id, created_at, updated_at)"
                 " SELECT ?, 'https://www.instagram.com/p/B/', (SELECT id FROM publication_types LIMIT 1),"
                 " (SELECT id FROM url_sources LIMIT 1), (SELECT id FROM batch_url_statuses WHERE code='PENDING'), ?, ?",
                 (twin, NOW, NOW))
    conn.commit()

    plan = svc.plan_rename(acc["oldname"], "newname", survivor="old")
    svc.execute(plan)

    owners = {r["catalog_account_id"] for r in conn.execute("SELECT catalog_account_id FROM batch_accounts")}
    assert owners == {acc["oldname"]}
    assert conn.execute("SELECT catalog_account_id FROM batch_accounts WHERE id = ?", (ba_removed,)).fetchone()[0] == acc["oldname"]
    urls = {r[0] for r in conn.execute("SELECT url FROM batch_urls bu JOIN batch_accounts ba ON ba.id = bu.batch_account_id WHERE ba.batch_id = (SELECT batch_id FROM batch_accounts WHERE id = ?)", (shared_old,))}
    assert urls == {"https://www.instagram.com/p/A/", "https://www.instagram.com/p/B/"}
    assert conn.execute("SELECT COUNT(*) FROM batch_accounts WHERE batch_id = (SELECT batch_id FROM batch_accounts WHERE id = ?)", (shared_old,)).fetchone()[0] == 1
    group = conn.execute("SELECT op_group FROM account_lifecycle WHERE kind = 'MERGE'").fetchone()[0]
    assert "mismo lote" in svc.undo_blocker(group)


def test_auto_survivor_prefers_the_location_that_is_still_in_use(env) -> None:
    svc, conn, lib, acc = env
    # the renamed account (more content) sits in an archived location; the existing one is in a live group
    (lib / "09.DELETED" / "oldname").mkdir(parents=True)
    put(lib, "09.DELETED\\oldname", media("2026-01-01", 1), b"11")
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("09.DELETED")
    conn.execute("UPDATE catalog_accounts SET rel_path = '09.DELETED\\oldname', folder_id = ? WHERE id = ?",
                 (fs.folder_id_for_rel("09.DELETED"), acc["oldname"]))
    conn.commit()

    plan = svc.plan_rename(acc["oldname"], "newname")

    assert plan.survivor_id == acc["newname"] and plan.removed_id == acc["oldname"]
    svc.execute(plan)
    assert (lib / "00.FAVORITES/Group/newname" / media("2026-01-01", 1)).exists()
    assert not (lib / "09.DELETED/oldname").exists()


def test_merge_survivor_can_be_the_existing_account(env) -> None:
    svc, conn, lib, acc = env
    put(lib, "00.FAVORITES\\Group\\oldname", media("2026-01-01", 1), b"11")

    plan = svc.plan_rename(acc["oldname"], "newname", survivor="new")
    assert plan.survivor_id == acc["newname"] and plan.removed_id == acc["oldname"]
    assert [s.op_type.value for s in plan.plan.steps] == ["MERGE_DIR"]  # already named 'newname'
    svc.execute(plan)

    assert (lib / "00.FAVORITES/Group/newname" / media("2026-01-01", 1)).exists()
    assert conn.execute("SELECT COUNT(*) FROM catalog_accounts WHERE id = ?", (acc["oldname"],)).fetchone()[0] == 0
    # the old name stays resolvable, now pointing at the surviving account
    assert svc.resolve_alias("oldname") == [(acc["newname"], "newname")]


def test_merge_with_different_instagram_ids_is_blocked(env) -> None:
    svc, conn, _lib, acc = env
    conn.execute("UPDATE catalog_accounts SET instagram_user_id = '123' WHERE id = ?", (acc["newname"],))
    conn.commit()

    plan = svc.plan_rename(acc["oldname"], "newname")

    assert not plan.can_execute and plan.plan.blocking[0].code == "OWNER_MISMATCH"
    with pytest.raises(FsOpsError):
        svc.execute(plan)


def test_merge_with_unverifiable_ids_needs_confirmation(env) -> None:
    svc, conn, _lib, acc = env
    conn.execute("UPDATE catalog_accounts SET instagram_user_id = NULL WHERE id IN (?, ?)", (acc["oldname"], acc["newname"]))
    conn.commit()

    unconfirmed = svc.plan_rename(acc["oldname"], "newname")
    confirmed = svc.plan_rename(acc["oldname"], "newname", confirm_unverified=True)

    assert unconfirmed.needs_confirmation and unconfirmed.plan.blocking[0].code == "UNVERIFIED_ID"
    assert confirmed.can_execute


def test_merge_into_orphan_folder_without_account(env) -> None:
    svc, conn, lib, acc = env
    (lib / "00.MODELS/spare").mkdir()
    put(lib, "00.MODELS\\spare", media("2026-01-09", 9), b"9")

    unconfirmed = svc.plan_rename(acc["other"], "spare")
    assert unconfirmed.plan.blocking[0].code == "UNVERIFIED_ID"  # an orphan folder has no id to compare
    plan = svc.plan_rename(acc["other"], "spare", confirm_unverified=True)
    assert plan.scenario == MERGE and plan.orphan_folder and plan.removed_id is None
    svc.execute(plan)

    assert (lib / "00.MODELS/spare" / media("2026-01-09", 9)).exists()
    assert conn.execute("SELECT username, rel_path FROM catalog_accounts WHERE id = ?", (acc["other"],)).fetchone()[0] == "spare"


def test_merge_undo_restores_files_and_removed_account(env) -> None:
    svc, conn, lib, acc = env
    put(lib, "00.FAVORITES\\Group\\oldname", media("2026-01-01", 1), b"11")
    put(lib, "00.FAVORITES\\Group\\newname", media("2026-01-02", 2), b"22")
    ba = add_batch(conn, "only_new", "COMPLETED", acc["newname"], ["https://www.instagram.com/p/NEW/"])
    group = svc.execute(svc.plan_rename(acc["oldname"], "newname", survivor="old"))

    assert svc.undo_blocker(group) == "" and FsOperationService(conn).can_undo(group)[0]
    FsOperationService(conn).undo(group)
    svc.restore_after_undo(group)

    assert (lib / "00.FAVORITES/Group/oldname" / media("2026-01-01", 1)).exists()
    assert (lib / "00.FAVORITES/Group/newname" / media("2026-01-02", 2)).exists()
    rows = {r["username"]: r["id"] for r in conn.execute("SELECT id, username FROM catalog_accounts")}
    assert rows["oldname"] == acc["oldname"] and rows["newname"] == acc["newname"]  # same primary keys
    assert conn.execute("SELECT catalog_account_id FROM batch_accounts WHERE id = ?", (ba,)).fetchone()[0] == acc["newname"]
    assert conn.execute("SELECT posts_count FROM catalog_accounts WHERE id = ?", (acc["oldname"],)).fetchone()[0] == 10
    assert aliases(conn, acc["newname"])[0][0] == "newname"


def test_account_in_active_batch_blocks_rename(env) -> None:
    svc, conn, _lib, acc = env
    add_batch(conn, "running", "PROCESSING", acc["oldname"], [])

    plan = svc.plan_rename(acc["oldname"], "brandnew")

    assert not plan.can_execute and plan.plan.blocking[0].code == "ACCOUNT_IN_ACTIVE_BATCH"
