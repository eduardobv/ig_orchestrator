from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.scanner import ACCOUNT, LibraryScanner
from ig_orchestrator.renaming import NewAccountSpec, RenameJob, RenameService
from ig_orchestrator.renaming.consult import IndexConsultProvider, has_index, index_status, kind_for_rel, write_through
from ig_orchestrator.renaming.planner import DiskConsultProvider

NOW = datetime(2026, 10, 10, 12, 30, 45)


def consult_name(index: int, ext: str = "jpg", suffix: str = "") -> str:
    media_id = 3_500_000_000_000_000_000 + index * 10_000_000_000_000
    return f"2025-{1 + index:02d}-10 10.00.00 {media_id}_5000{suffix}.{ext}"


def raw(index: int, delta: int = 0, ext: str = "jpg") -> str:
    return f"{3_500_000_000_000_000_000 + index * 10_000_000_000_000 + delta}.{ext}"


def fill_library(alice: Path) -> None:
    (alice / "story").mkdir(parents=True, exist_ok=True)
    (alice / "reels").mkdir(exist_ok=True)
    for i in range(6):
        (alice / consult_name(i, suffix="_manual" if i == 4 else "")).write_bytes(b"x")
    (alice / consult_name(2, suffix=" (1)")).write_bytes(b"x")
    for i in (1, 3):
        (alice / "story" / consult_name(i, "mp4")).write_bytes(b"x")
    (alice / "reels" / consult_name(0, "mp4")).write_bytes(b"x")


def fill_downloads(folder: Path) -> None:
    (folder / "story").mkdir(parents=True)
    for name in (raw(2, 1_000_000_000), raw(7, 0), raw(3, 0), raw(5, 2_000_000_000)):
        (folder / name).write_bytes(b"d")
    (folder / "story" / raw(2, 500_000_000, "mp4")).write_bytes(b"d")
    (folder / "story" / raw(3, 0, "mp4")).write_bytes(b"d")  # duplicate of a story id


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    alice = lib / "00.MODELS" / "alice"
    fill_library(alice)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("00.MODELS")
    account_id = conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at, rel_path)"
        " VALUES ('alice', '5000', ?, 1, 'x', 'x', '00.MODELS\\alice')", (fs.folder_id_for_rel("00.MODELS"),)
    ).lastrowid
    conn.commit()
    LibraryScanner(conn, root=str(lib)).scan(ACCOUNT, account_id=account_id)
    yield conn, lib, int(account_id), tmp_path
    conn.close()


def view(items):
    return [(i.filename, i.date, i.num_id, i.user_id, i.ext, i.rest) for i in items]


def test_index_provider_is_equivalent_to_the_disk_provider(env) -> None:
    conn, lib, account_id, _ = env
    disk = DiskConsultProvider(str(lib / "00.MODELS" / "alice"))
    index = IndexConsultProvider(conn, account_id)

    for rel in ("", "story", "reels"):
        assert sorted(view(index.items(rel)), key=lambda r: (r[2], r[0])) == sorted(view(disk.items(rel)), key=lambda r: (r[2], r[0])), rel
    assert index.items("highlights") is None and index.items("whatever") is None
    assert kind_for_rel("Story") == 2 and kind_for_rel("") == 0 and has_index(conn, account_id)
    assert index_status(conn, account_id).startswith("10 ficheros")


@pytest.mark.parametrize("seed", [1, 4, 77])
def test_rename_with_index_equals_rename_from_disk(env, seed: int) -> None:
    conn, lib, account_id, tmp = env
    results = {}
    snapshot = conn.execute("SELECT account_id, kind, media_id, taken_at, owner_id, ext, suffix FROM media_index").fetchall()
    for mode in ("disk", "index"):
        conn.execute("DELETE FROM media_index")  # a run writes its renamed files through: start both from the same index
        conn.executemany("INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?,?,?,?,?,?,?)", snapshot)
        conn.commit()
        down = tmp / f"down_{mode}"
        fill_downloads(down / "alice")
        service = RenameService(conn)
        preview = service.preview(RenameJob(str(down), "2026-10-10", move_renamed=False, no_duplicated=False, reference=mode),
                                  seed=seed, now=NOW)
        assert preview.accounts[0].reference == mode.upper()
        results[mode] = sorted(p.relative_to(down).as_posix() for p in down.rglob("*") if p.is_file()) if service.run(preview) else []
    assert results["disk"] == results["index"] and results["disk"]


def test_offline_library_renames_in_place_and_marks_pending(env) -> None:
    conn, lib, account_id, tmp = env
    down = tmp / "down"
    fill_downloads(down / "alice")
    offline = tmp / "library_disconnected"
    shutil.move(str(lib), str(offline))  # "G:" unplugged

    service = RenameService(conn)
    preview = service.preview(RenameJob(str(down), "2026-10-10"), seed=3, now=NOW)
    plan = preview.accounts[0]
    assert plan.reference == "INDEX" and plan.pending_move and plan.renamed == 4
    result = service.run(preview)

    outcome = result.accounts[0]
    assert outcome.status == "RENAMED_PENDING_MOVE" and outcome.pending and not outcome.moved and result.ok
    renamed = sorted(p.name for p in (down / "alice").rglob("*") if p.is_file())
    assert any("_5000_manual" in n for n in renamed) and sum("_duplicated" in n for n in renamed) == 0  # dups deleted
    # write-through: the renamed files are already in the index
    count = conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0]
    assert count == 10 + 4
    assert [r["username"] for r in service.pending_moves()] == ["alice"]
    with pytest.raises(ValueError, match="no esta disponible"):
        service.move_pending()

    shutil.move(str(offline), str(lib))  # plugged again
    moved = service.move_pending()

    assert moved[0].moved and moved[0].status == "RENAMED"
    assert not service.pending_moves() and not (down / "alice").exists()
    final = sorted(p.name for p in (lib / "00.MODELS" / "alice").rglob("*") if p.is_file())
    assert all(name in final for name in renamed)
    assert conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0] == count  # no duplicates
    assert conn.execute("SELECT status, moved FROM rename_run_accounts").fetchone()[:] == ("RENAMED", 1)


def test_offline_account_without_index_is_skipped_with_no_index(env) -> None:
    conn, lib, account_id, tmp = env
    conn.execute("DELETE FROM media_index WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM media_index_state WHERE account_id = ?", (account_id,))
    conn.commit()
    down = tmp / "down"
    fill_downloads(down / "alice")
    shutil.move(str(lib), str(tmp / "off"))

    preview = RenameService(conn).preview(RenameJob(str(down), "2026-10-10"), seed=1, now=NOW)

    assert preview.accounts[0].status == "SKIPPED" and preview.accounts[0].reason.startswith("NO_INDEX")


def test_new_account_offline_is_registered_after_the_pending_move(env) -> None:
    conn, lib, _account_id, tmp = env
    down = tmp / "down"
    (down / "newgirl").mkdir(parents=True)
    for i, delta in enumerate((0, 1_000_000_000)):
        (down / "newgirl" / raw(2 + i, delta)).write_bytes(b"d")
    spec = NewAccountSpec("newgirl", "777", "2025-12-14", str(lib / "00.MODELS"))
    shutil.move(str(lib), str(tmp / "off"))
    service = RenameService(conn)

    result = service.run(service.preview(RenameJob(str(down), "2026-10-10", (spec,)), seed=2, now=NOW))

    assert result.accounts[0].status == "RENAMED_PENDING_MOVE"
    assert conn.execute("SELECT rel_path FROM catalog_accounts WHERE username = 'newgirl'").fetchone()[0] is None

    shutil.move(str(tmp / "off"), str(lib))
    service.move_pending()

    row = conn.execute("SELECT rel_path, instagram_user_id, posts_count FROM catalog_accounts WHERE username = 'newgirl'").fetchone()
    assert tuple(row) == ("00.MODELS\\newgirl", "777", 2)
    assert (lib / "00.MODELS" / "newgirl").is_dir() and not (down / "newgirl").exists()


def test_write_through_ignores_unknown_folders_and_unparsable_names(env) -> None:
    conn, _lib, account_id, _ = env
    before = conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0]

    added = write_through(conn, account_id, [("weird", consult_name(9)), ("", "no-date.jpg"), ("reels", consult_name(8, "mp4"))])

    assert added == 1
    assert conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0] == before + 1


def test_verify_index_lists_external_changes(env) -> None:
    from ig_orchestrator.renaming.consult import verify_index

    conn, lib, account_id, _ = env
    alice = lib / "00.MODELS" / "alice"
    assert verify_index(conn, account_id, str(alice)) == {"added": [], "removed": []}

    (alice / consult_name(9)).write_bytes(b"x")  # added outside the app
    (alice / consult_name(0)).unlink()  # deleted outside the app
    diff = verify_index(conn, account_id, str(alice))

    assert diff["added"] == [f"(raiz)/{consult_name(9)}"] and len(diff["removed"]) == 1
    LibraryScanner(conn, root=str(lib)).scan(ACCOUNT, account_id=account_id, deep=True)  # "accept the disk"
    assert verify_index(conn, account_id, str(alice)) == {"added": [], "removed": []}
