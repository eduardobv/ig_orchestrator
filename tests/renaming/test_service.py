from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.renaming import NewAccountSpec, RenameJob, RenameService
from ig_orchestrator.renaming.service import resolve_account_folder

NOW = datetime(2026, 10, 10, 12, 30, 45)
NOWSTR = "2026-10-10"


def consult_name(index: int, ext: str = "jpg", owner: str = "5000") -> str:
    media_id = 3_500_000_000_000_000_000 + index * 10_000_000_000_000
    return f"2025-{1 + index:02d}-10 10.00.00 {media_id}_{owner}.{ext}"


def raw(index: int, delta: int = 0, ext: str = "jpg") -> str:
    return f"{3_500_000_000_000_000_000 + index * 10_000_000_000_000 + delta}.{ext}"


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    alice = lib / "00.MODELS" / "alice"
    alice.mkdir(parents=True)
    for i in range(5):
        (alice / consult_name(i)).write_bytes(b"x")
    downloads = tmp_path / "downloads"
    (downloads / "alice").mkdir(parents=True)
    for name in (raw(2, 1_000_000_000), raw(6, 0), raw(3, 0)):  # between, above, duplicate of consult #3
        (downloads / "alice" / name).write_bytes(b"d")
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("00.MODELS")
    conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at,"
        " rel_path) VALUES ('alice', '5000', ?, 1, 'x', 'x', '00.MODELS\\alice')", (fs.folder_id_for_rel("00.MODELS"),)
    )
    conn.commit()
    yield RenameService(conn), conn, lib, downloads
    conn.close()


def job(downloads: Path, **kwargs) -> RenameJob:
    return RenameJob(str(downloads), NOWSTR, **kwargs)


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.rglob("*") if p.is_file())


def test_preview_changes_nothing_and_run_gives_exactly_the_previewed_names(env) -> None:
    service, conn, lib, downloads = env
    before = names(downloads)

    preview = service.preview(job(downloads, move_renamed=False, no_duplicated=False), seed=7, now=NOW)

    assert names(downloads) == before  # nothing touched
    plan = preview.accounts[0]
    assert plan.renamed == 2 and plan.duplicated == 1
    expected = sorted(Path(a.new).name for a in plan.actions)
    result = service.run(preview)
    assert result.ok
    assert names(downloads / "alice") == expected


def test_full_run_renames_deletes_duplicates_moves_and_refreshes_counters(env) -> None:
    service, conn, lib, downloads = env
    preview = service.preview(job(downloads), seed=3, now=NOW)

    result = service.run(preview)

    outcome = result.accounts[0]
    assert (outcome.status, outcome.renamed, outcome.duplicated, outcome.deleted_duplicates, outcome.moved) == ("RENAMED", 2, 1, 1, True)
    assert not (downloads / "alice").exists()  # moved into the library
    files = names(lib / "00.MODELS" / "alice")
    assert len(files) == 5 + 2 and not any("_duplicated" in f for f in files)
    assert sum(1 for f in files if f.endswith("_5000_manual.jpg")) == 2
    row = conn.execute("SELECT posts_count, scan_state FROM catalog_accounts WHERE username = 'alice'").fetchone()
    assert row["posts_count"] == 7  # write-through: counters refreshed after the move
    run = conn.execute("SELECT engine, status, source_folder FROM rename_runs").fetchone()
    assert (run["engine"], run["status"]) == ("integrated", "OK")
    saved = conn.execute("SELECT username, status, renamed, moved FROM rename_run_accounts").fetchone()
    assert tuple(saved) == ("alice", "RENAMED", 2, 1)


def test_duplicates_are_kept_when_not_asked_to_delete_them(env) -> None:
    service, _conn, lib, downloads = env

    result = service.run(service.preview(job(downloads, no_duplicated=True, move_renamed=False), seed=1, now=NOW))
    assert result.accounts[0].deleted_duplicates == 1

    (downloads / "alice" / raw(1, 0)).write_bytes(b"d")  # duplicate of consult #1
    result = service.run(service.preview(job(downloads, no_duplicated=False, move_renamed=False), seed=1, now=NOW))
    assert result.accounts[0].deleted_duplicates == 0 and any("_duplicated" in n for n in names(downloads))


def test_unregistered_and_undeclared_accounts_are_skipped_with_a_reason(env) -> None:
    service, _conn, _lib, downloads = env
    (downloads / "stranger").mkdir()
    (downloads / "stranger" / raw(1)).write_bytes(b"d")

    result = service.run(service.preview(job(downloads, move_renamed=False), seed=1, now=NOW))

    by_name = {a.username: a for a in result.accounts}
    assert by_name["stranger"].status == "SKIPPED" and "no se declaro" in by_name["stranger"].detail
    assert (downloads / "stranger" / raw(1)).exists()
    assert not result.ok and [a.username for a in result.problems] == ["stranger"]


def test_new_account_is_registered_once_in_bdapp_and_in_lite(env, tmp_path: Path) -> None:
    service, conn, lib, downloads = env
    lite = tmp_path / "accounts_lite.sqlite"
    with sqlite3.connect(lite) as db:
        db.execute("CREATE TABLE accounts_dir (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ownerId TEXT, path TEXT UNIQUE,"
                   " last_modified TEXT, created_at TEXT, modified_at TEXT)")
    conn.execute("INSERT INTO app_settings (key, value, value_type, updated_at) VALUES ('stories.accounts_db_path', ?, 'PATH', 'x')", (str(lite),))
    conn.commit()
    (downloads / "newgirl" / "story").mkdir(parents=True)
    for i, delta in enumerate((0, 1_000_000_000, 2_000_000_000)):
        (downloads / "newgirl" / raw(2 + i, delta)).write_bytes(b"d")
    (downloads / "newgirl" / "story" / raw(5, 0, "mp4")).write_bytes(b"d")
    spec = NewAccountSpec("newgirl", "777", "2025-12-14", str(lib / "00.MODELS"))
    only_new = RenameJob(str(downloads), NOWSTR, (spec,), True, True)
    (downloads / "alice").rename(tmp_path / "set_aside")  # keep the example focused on the new account

    preview = service.preview(only_new, seed=5, now=NOW)
    assert preview.accounts[0].status == "NEW" and preview.accounts[0].renamed == 4
    result = service.run(preview)

    assert result.accounts[0].status == "NEW" and result.accounts[0].moved
    final = lib / "00.MODELS" / "newgirl"
    assert final.is_dir() and all(f.endswith("_777_manual.jpg") or f.endswith("_777_manual.mp4") for f in names(final))
    row = conn.execute("SELECT * FROM catalog_accounts WHERE username = 'newgirl'").fetchone()
    assert (row["instagram_user_id"], row["rel_path"], row["start_init_date"]) == ("777", "00.MODELS\\newgirl", "2025-12-14")
    assert row["folder_id"] is not None and row["posts_count"] == 3 and row["story_count"] == 1
    assert row["legacy_lite_id"] is not None
    with sqlite3.connect(lite) as db:
        assert db.execute("SELECT username, ownerId, path FROM accounts_dir").fetchall() == [("newgirl", "777", str(final))]
    # a second declaration of the same account is refused: it is registered now
    (downloads / "newgirl").mkdir()
    again = service.preview(only_new, seed=5, now=NOW)
    assert again.accounts[0].status == "SKIPPED" and "ya esta registrada" in again.accounts[0].reason


def test_new_account_declared_but_missing_in_the_folder_is_reported(env) -> None:
    service, _conn, lib, downloads = env
    spec = NewAccountSpec("ghost", "1", "2025-01-01", str(lib))

    preview = service.preview(RenameJob(str(downloads), NOWSTR, (spec,)), seed=1, now=NOW)

    ghost = next(a for a in preview.accounts if a.username == "ghost")
    assert ghost.status == "SKIPPED" and "no esta como carpeta" in ghost.reason


def test_name_clash_in_the_destination_aborts_the_move_and_keeps_the_folder(env) -> None:
    service, _conn, lib, downloads = env
    clash = lib / "00.MODELS" / "alice"
    (downloads / "alice" / "story").mkdir()
    (downloads / "alice" / "story" / "x.jpg").write_bytes(b"d")
    (clash / "story").mkdir()
    (clash / "story" / "x.jpg").write_bytes(b"other")

    preview = service.preview(job(downloads), seed=1, now=NOW)
    assert preview.accounts[0].move.status == "FAILED"
    result = service.run(preview)

    assert result.accounts[0].status == "MOVE_CONFLICT" and not result.accounts[0].moved
    assert (downloads / "alice").is_dir()  # renamed files stay in the download folder
    assert (clash / "story" / "x.jpg").read_bytes() == b"other"


def test_merge_into_existing_library_folder_keeps_both(env) -> None:
    service, _conn, lib, downloads = env
    result = service.run(service.preview(job(downloads), seed=2, now=NOW))
    assert result.ok and result.accounts[0].moved
    assert len(names(lib / "00.MODELS" / "alice")) == 7


def test_cancel_stops_before_the_next_account(env) -> None:
    service, _conn, _lib, downloads = env
    (downloads / "zeta").mkdir()
    cancel = threading.Event()
    cancel.set()

    result = service.run(service.preview(job(downloads, move_renamed=False), seed=1, now=NOW), cancel_event=cancel)

    assert result.cancelled and result.accounts == []
    assert (downloads / "alice" / raw(6, 0)).exists()


def test_missing_source_and_bad_date(env, tmp_path: Path) -> None:
    service, _conn, _lib, downloads = env
    with pytest.raises(ValueError, match="no existe"):
        service.preview(RenameJob(str(tmp_path / "nope"), NOWSTR))
    with pytest.raises(ValueError):
        service.preview(RenameJob(str(downloads), "10/10/2026"))


def test_resolve_account_folder_accepts_folder_or_parent() -> None:
    assert resolve_account_folder(r"G:\4K\00.M\alice", "alice") == r"G:\4K\00.M\alice"
    assert resolve_account_folder(r"G:\4K\00.M", "alice") == r"G:\4K\00.M\alice"
