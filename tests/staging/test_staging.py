from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.scanner import ACCOUNT, LibraryScanner
from ig_orchestrator.renaming import NewAccountSpec, RenameJob, RenameService
from ig_orchestrator.renaming.settings import staging_after_rename
from ig_orchestrator.staging import StagingService
from ig_orchestrator.staging.service import merge_verified

NOW = datetime(2026, 10, 10, 12, 30, 45)


def consult_name(index: int) -> str:
    return f"2025-{1 + index:02d}-10 10.00.00 {3_500_000_000_000_000_000 + index * 10_000_000_000_000}_5000.jpg"


def raw(index: int, delta: int = 0) -> str:
    return f"{3_500_000_000_000_000_000 + index * 10_000_000_000_000 + delta}.jpg"


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K Stogram"
    alice = lib / "00.MODELS" / "alice"
    alice.mkdir(parents=True)
    for i in range(4):
        (alice / consult_name(i)).write_bytes(b"x")
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    staging = tmp_path / "staging"
    conn.execute("INSERT INTO app_settings (key, value, value_type, updated_at) VALUES ('staging.root', ?, 'PATH', 'x')", (str(staging),))
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("00.MODELS")
    account_id = conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at, rel_path)"
        " VALUES ('alice', '5000', ?, 1, 'x', 'x', '00.MODELS\\alice')", (fs.folder_id_for_rel("00.MODELS"),)
    ).lastrowid
    conn.commit()
    LibraryScanner(conn, root=str(lib)).scan(ACCOUNT, account_id=int(account_id))
    downloads = tmp_path / "down"
    (downloads / "alice").mkdir(parents=True)
    for name in (raw(1, 1_000_000_000), raw(6)):
        (downloads / "alice" / name).write_bytes(b"d")
    yield conn, lib, staging, downloads, int(account_id), tmp_path
    conn.close()


def stage(conn, downloads: Path, seed: int = 1, specs: tuple = ()):
    service = RenameService(conn)
    return service, service.run(service.preview(RenameJob(str(downloads), "2026-10-10", specs, destination="staging"), seed=seed, now=NOW))


def test_rename_to_staging_keeps_library_untouched_and_records_it(env) -> None:
    conn, lib, staging, downloads, account_id, _ = env
    before = sorted(p.name for p in (lib / "00.MODELS" / "alice").iterdir())

    _service, result = stage(conn, downloads)

    out = result.accounts[0]
    assert out.status == "STAGED" and out.staged and result.ok and not out.moved
    assert sorted(p.name for p in (lib / "00.MODELS" / "alice").iterdir()) == before
    assert len(list((staging / "00.MODELS" / "alice").iterdir())) == 2 and not (downloads / "alice").exists()
    row = conn.execute("SELECT staging_rel, target_rel, files, status FROM staged_accounts WHERE catalog_account_id = ?", (account_id,)).fetchone()
    assert tuple(row) == ("00.MODELS\\alice", "00.MODELS\\alice", 2, "STAGED")
    assert conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0] == 4 + 2  # write-through


def test_dump_moves_everything_and_updates_the_catalog(env) -> None:
    conn, lib, staging, downloads, account_id, _ = env
    stage(conn, downloads)
    service = StagingService(conn)
    assert service.summary()[0:2] == (1, 2)
    item = service.plan()[0]
    assert item.kind == "FUSIONAR" and not item.conflicts

    result = service.dump()

    assert result.outcomes[0].status == "DUMPED" and not result.problems and "1 de 1" in result.summary()
    assert len(list((lib / "00.MODELS" / "alice").iterdir())) == 6
    assert not staging.exists() or not any(staging.rglob("*"))  # staging emptied (and empty parents removed)
    row = conn.execute("SELECT posts_count FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()
    assert row[0] == 6
    assert conn.execute("SELECT status FROM staged_accounts").fetchone()[0] == "DUMPED"
    assert conn.execute("SELECT status, accounts, files FROM dump_runs").fetchone()[:] == ("OK", 1, 2)
    assert conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0] == 6  # no duplicates
    assert service.forget_dumped() == 1 and service.summary()[0] == 0


def test_dump_conflict_is_not_overwritten(env) -> None:
    conn, lib, staging, downloads, _account_id, _ = env
    stage(conn, downloads)
    staged_file = next((staging / "00.MODELS" / "alice").iterdir())
    (lib / "00.MODELS" / "alice" / staged_file.name).write_bytes(b"other")  # same name appears in the library
    service = StagingService(conn)

    assert service.plan()[0].kind == "CONFLICTO"
    result = service.dump()

    assert result.outcomes[0].status == "CONFLICT" and staged_file.exists()
    assert (lib / "00.MODELS" / "alice" / staged_file.name).read_bytes() == b"other"
    assert conn.execute("SELECT status FROM staged_accounts").fetchone()[0] == "CONFLICT"


def test_dump_requires_the_library_and_can_be_cancelled(env) -> None:
    conn, lib, staging, downloads, _account_id, tmp = env
    stage(conn, downloads)
    service = StagingService(conn)
    cancel = threading.Event()
    cancel.set()

    assert service.dump(cancel_event=cancel).cancelled and len(list((staging / "00.MODELS" / "alice").iterdir())) == 2
    lib.rename(tmp / "off")
    with pytest.raises(ValueError, match="no esta disponible"):
        service.dump()


def test_interrupted_dump_resumes_without_duplicates(env) -> None:
    conn, lib, staging, downloads, _account_id, _ = env
    stage(conn, downloads)
    first, second = sorted((staging / "00.MODELS" / "alice").iterdir())
    first.replace(lib / "00.MODELS" / "alice" / first.name)  # the cut happened after one file was moved
    conn.execute("UPDATE staged_accounts SET status = 'DUMPING'")
    conn.commit()
    service = StagingService(conn)

    assert service.plan()[0].kind == "FUSIONAR" and service.plan()[0].files == 1
    result = service.dump()

    assert result.outcomes[0].status == "DUMPED"
    names = sorted(p.name for p in (lib / "00.MODELS" / "alice").iterdir())
    assert len(names) == 6 and first.name in names and second.name in names


def test_new_account_in_staging_gets_its_path_only_after_the_dump(env) -> None:
    conn, lib, staging, downloads, _account_id, _ = env
    (downloads / "newgirl").mkdir()
    for i, delta in enumerate((0, 1_000_000_000)):
        (downloads / "newgirl" / raw(2 + i, delta)).write_bytes(b"d")
    spec = NewAccountSpec("newgirl", "777", "2025-12-14", str(lib / "00.MODELS"))
    _service, result = stage(conn, downloads, specs=(spec,))
    new = next(a for a in result.accounts if a.username == "newgirl")
    assert new.status == "STAGED"
    assert conn.execute("SELECT rel_path FROM catalog_accounts WHERE username = 'newgirl'").fetchone()[0] is None

    dumped = StagingService(conn).dump()

    assert {o.username: o.status for o in dumped.outcomes} == {"alice": "DUMPED", "newgirl": "DUMPED"}
    row = conn.execute("SELECT rel_path, posts_count FROM catalog_accounts WHERE username = 'newgirl'").fetchone()
    assert tuple(row) == ("00.MODELS\\newgirl", 2) and (lib / "00.MODELS" / "newgirl").is_dir()


def test_dump_follows_a_move_of_the_account_in_the_catalog(env) -> None:
    conn, lib, _staging, downloads, account_id, _ = env
    stage(conn, downloads)
    (lib / "01.OTHER").mkdir()
    (lib / "00.MODELS" / "alice").rename(lib / "01.OTHER" / "alice")
    conn.execute("UPDATE catalog_accounts SET rel_path = '01.OTHER\\alice' WHERE id = ?", (account_id,))
    conn.commit()

    result = StagingService(conn).dump()

    assert result.outcomes[0].status == "DUMPED" and len(list((lib / "01.OTHER" / "alice").iterdir())) == 6
    assert not (lib / "00.MODELS" / "alice").exists()


def test_settings_and_file_move_helpers(env, tmp_path: Path) -> None:
    conn, *_ = env
    assert staging_after_rename(conn) == "ASK"
    src = tmp_path / "s"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "a.jpg").write_bytes(b"1")
    assert merge_verified(str(src), str(tmp_path / "d")) == 1
    assert (tmp_path / "d" / "sub" / "a.jpg").read_bytes() == b"1" and not src.exists()
    with pytest.raises(ValueError):
        conn.execute("DELETE FROM app_settings WHERE key = 'staging.root'")
        StagingService(conn).staging_root()


def test_status_bar_text_summarises_what_waits_in_the_staging_area(env) -> None:
    from ig_orchestrator.gui.library.staging_panel import staging_status_text

    conn, _lib, _staging, downloads, _account_id, _ = env
    assert staging_status_text(conn) == ""
    stage(conn, downloads)

    text = staging_status_text(conn)

    assert text.startswith("Almac") and "1 cuenta" in text and "pendientes" in text
