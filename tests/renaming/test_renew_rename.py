from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.renaming import NewAccountSpec, RenameJob, RenameService

NOW = datetime(2026, 10, 10, 12, 30, 45)
BASE = 3_500_000_000_000_000_000


def raw(index: int, ext: str = "jpg") -> str:
    return f"{BASE + index * 10_000_000_000_000}.{ext}"


def names(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def make_env(tmp_path: Path, owner: str | None = "5000"):
    lib = tmp_path / "4K Stogram"
    alice = lib / "00.MODELS" / "alice"
    (alice / "reels").mkdir(parents=True)
    # library: three files named only by media id, one other name that must be ignored, one with the final format
    for i in (1, 2, 3):
        (alice / raw(i)).write_bytes(b"x")
    (alice / "reels" / raw(4, "mp4")).write_bytes(b"x")
    (alice / "holiday photo.jpg").write_bytes(b"x")
    downloads = tmp_path / "downloads"
    (downloads / "alice").mkdir(parents=True)
    for i in (5, 6):
        (downloads / "alice" / raw(i)).write_bytes(b"d")
    (downloads / "alice" / raw(2)).write_bytes(b"d")  # same id as a library file: duplicate
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("00.MODELS")
    conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at,"
        " rel_path) VALUES ('alice', ?, ?, 1, 'x', 'x', '00.MODELS\\alice')",
        (owner, fs.folder_id_for_rel("00.MODELS")),
    )
    conn.commit()
    return RenameService(conn), conn, lib, downloads


@pytest.fixture()
def env(tmp_path: Path):
    service, conn, lib, downloads = make_env(tmp_path)
    yield service, conn, lib, downloads
    conn.close()


def renew_job(downloads: Path, owner: str = "", **kwargs) -> RenameJob:
    spec = NewAccountSpec("alice", owner, "2025-01-01", "", renew=True)
    return RenameJob(str(downloads), "2026-10-10", (spec,), **kwargs)


def test_renew_joins_library_and_downloads_and_ignores_other_names(env) -> None:
    service, conn, lib, downloads = env
    account = lib / "00.MODELS" / "alice"

    preview = service.preview(renew_job(downloads, no_duplicated=False), seed=1, now=NOW)

    plan = preview.accounts[0]
    assert plan.status == "RENEW"
    assert names(account) == sorted([raw(1), raw(2), raw(3), "holiday photo.jpg", f"reels\\{raw(4, 'mp4')}"])  # untouched
    result = service.run(preview)
    outcome = result.accounts[0]
    assert (outcome.status, outcome.renamed, outcome.duplicated, outcome.moved) == ("RENEW", 6, 1, True)
    assert outcome.renamed_in_library == 4  # 3 in the root + 1 in reels
    files = names(account)
    assert "holiday photo.jpg" in files  # other names are ignored
    assert len([f for f in files if f.endswith(("_manual.jpg", "_manual.mp4"))]) == 6
    assert not any(re.match(r"^\d{10,}\.", Path(f).name) for f in files)  # no media-id-only name is left
    assert any("_duplicated" in f for f in files)  # kept: no_duplicated=False
    assert not (downloads / "alice").exists()  # the downloaded folder was moved into the library


def test_renew_dates_start_at_first_post_date_and_follow_the_id_order(env) -> None:
    service, conn, lib, downloads = env
    preview = service.preview(renew_job(downloads), seed=1, now=NOW)
    plan = preview.accounts[0]
    root = [a for a in plan.actions if a.kind == "RENAME" and "reels" not in a.old]
    root.sort(key=lambda a: Path(a.old).name)
    dates = [a.date for a in root]
    assert dates == sorted(dates, reverse=False)
    assert dates[0].startswith("2025-01-01")


def test_renew_registers_first_post_date_and_keeps_path_and_owner(env) -> None:
    service, conn, lib, downloads = env
    service.run(service.preview(renew_job(downloads), seed=1, now=NOW))
    row = conn.execute(
        "SELECT start_init_date, instagram_user_id, rel_path FROM catalog_accounts WHERE username = 'alice'"
    ).fetchone()
    assert (row["start_init_date"], row["instagram_user_id"], row["rel_path"]) == ("2025-01-01", "5000", "00.MODELS\\alice")


def test_renew_uses_catalog_owner_in_names(env) -> None:
    service, conn, lib, downloads = env
    service.run(service.preview(renew_job(downloads, owner="9999"), seed=1, now=NOW))
    files = names(lib / "00.MODELS" / "alice")
    assert all("_5000_manual" in f for f in files if f.endswith("_manual.jpg") or f.endswith("_manual.mp4"))


def test_renew_is_skipped_when_the_account_has_no_folder(tmp_path: Path) -> None:
    service, conn, lib, downloads = make_env(tmp_path)
    conn.execute("UPDATE catalog_accounts SET rel_path = NULL")
    conn.commit()
    preview = service.preview(renew_job(downloads), seed=1, now=NOW)
    assert preview.accounts[0].status == "SKIPPED" and "Renew" in preview.accounts[0].reason
    conn.close()


def test_renew_is_skipped_without_owner_id_in_the_catalog(tmp_path: Path) -> None:
    service, conn, lib, downloads = make_env(tmp_path, owner=None)
    preview = service.preview(renew_job(downloads), seed=1, now=NOW)
    assert preview.accounts[0].status == "SKIPPED" and "Owner" in preview.accounts[0].reason
    conn.close()


def test_already_named_library_files_are_not_touched(env) -> None:
    service, conn, lib, downloads = env
    account = lib / "00.MODELS" / "alice"
    named = f"2025-03-03 10.00.00 {BASE + 9 * 10_000_000_000_000}_5000_manual.jpg"
    (account / named).write_bytes(b"x")
    preview = service.preview(renew_job(downloads), seed=1, now=NOW)
    assert any("ya tiene 1 ficheros renombrados" in w for w in preview.accounts[0].tree.warnings)
    service.run(preview)
    assert named in names(account)
