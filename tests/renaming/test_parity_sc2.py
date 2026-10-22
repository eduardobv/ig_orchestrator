"""The integrated renamer must give the same result as ``sc2`` (ManualRenameFiles) for the same seed and clock."""

from __future__ import annotations

import importlib
import logging
import os
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

from ig_orchestrator.renaming.planner import DiskConsultProvider, NewUser, RealOps, process_folder_tree
from ig_orchestrator.renaming.timeline import TimelineContext

SC2_DIR = Path(r"D:\Archivos\Scripts\IG\ManualRenameFiles")
NOW = datetime(2026, 10, 10, 12, 30, 45)
SC2_MODULES = ("config", "file_utils", "timeline_builder", "folder_processor", "account_database", "compare_dirs", "my_logging", "main")

pytestmark = pytest.mark.skipif(not (SC2_DIR / "folder_processor.py").is_file(), reason="sc2 is not installed here")


@pytest.fixture()
def sc2():
    for name in SC2_MODULES:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(SC2_DIR))
    try:
        modules = {name: importlib.import_module(name) for name in ("config", "timeline_builder", "folder_processor")}
        modules["timeline_builder"].get_current_date = lambda: NOW
        modules["folder_processor"].get_current_date = lambda: NOW
        yield modules
    finally:
        sys.path.remove(str(SC2_DIR))
        for name in SC2_MODULES:
            sys.modules.pop(name, None)


def consult_name(index: int, ext: str = "jpg", owner: str = "5000", rest: str = "") -> str:
    month = 1 + index % 12
    year = 2024 + index // 12
    media_id = 3_500_000_000_000_000_000 + index * 10_000_000_000_000
    return f"{year}-{month:02d}-10 10.00.00 {media_id}_{owner}{rest}.{ext}"


def manual_name(offset_index: int, delta: int, ext: str = "jpg") -> str:
    return f"{3_500_000_000_000_000_000 + offset_index * 10_000_000_000_000 + delta}.{ext}"


def build_library(root: Path) -> Path:
    consult = root / "library" / "00.MODELS" / "alice"
    (consult / "story").mkdir(parents=True)
    (consult / "reels").mkdir()
    for i in range(0, 10):
        (consult / consult_name(i)).write_bytes(b"x")
    for i in range(2, 7):
        (consult / "story" / consult_name(i, "mp4", rest="_manual")).write_bytes(b"x")
    for i in range(0, 3):
        (consult / "reels" / consult_name(i, "mp4", owner="6000")).write_bytes(b"x")
    return consult


def build_manual(root: Path) -> Path:
    manual = root / "manual" / "alice"
    (manual / "story").mkdir(parents=True)
    (manual / "reels").mkdir()
    (manual / "newsub").mkdir()
    root_files = [
        manual_name(0, -5_000_000_000), manual_name(0, -4_000_000_000),            # below the first consult
        manual_name(3, 1_000_000_000), manual_name(3, 2_000_000_000), manual_name(3, 3_000_000_000),  # between
        manual_name(5, 5_000_000_000),                                            # between (another block)
        manual_name(9, 1_000_000_000), manual_name(9, 2_000_000_000),            # above the last consult
        manual_name(14, 0), manual_name(20, 0), manual_name(20, 7_000_000_000, "mp4"),  # far above
        manual_name(4, 0),                                                         # duplicate of a consult id
        manual_name(7, 0),                                                         # duplicate again
    ]
    for name in root_files:
        (manual / name).write_bytes(b"m")
    for name in (manual_name(3, 500_000_000, "mp4"), manual_name(8, 0, "mp4"), manual_name(2, 0, "mp4")):
        (manual / "story" / name).write_bytes(b"m")  # last one is a duplicate of a story id
    for name in (manual_name(1, 3_000_000_000, "mp4"), manual_name(11, 0, "mp4")):
        (manual / "reels" / name).write_bytes(b"m")
    (manual / "newsub" / manual_name(2, 1_000_000_000)).write_bytes(b"m")  # sub-folder without a library twin
    (manual / "ignored.txt").write_text("not media")
    return manual


def listing(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def run_sc2(sc2, manual: Path, consult: Path, seed: int, *, new_user: tuple[str, str] | None = None) -> None:
    flag_new = new_user is not None
    sc2["config"].set_runtime_config({
        "mode": "newRename",
        "newRename": {},
        "renameProcess": {
            "manualFolder": str(manual), "consultFolders": [], "startNowDate": NOW.date().isoformat(),
            "flagNew": flag_new, "noDuplicated": False, "moveRenamed": False,
            "newUser": {"startInitDate": new_user[1] if new_user else None, "userId": new_user[0] if new_user else None},
        },
        "compareProcess": {"enabled": False, "replace": False},
    })
    logger = logging.getLogger(f"sc2-parity-{seed}")
    logger.handlers = [logging.NullHandler()]
    random.seed(seed)
    sc2["folder_processor"].process_folder_tree(str(manual), str(consult), logger)


def run_mine(manual: Path, consult: Path, seed: int, *, new_user: tuple[str, str] | None = None):
    if new_user:
        ctx = TimelineContext(random.Random(seed), NOW, forced_user_id=new_user[0], flag_new=True)
        user = NewUser(datetime.strptime(new_user[1], "%Y-%m-%d"), new_user[0])
    else:
        ctx, user = TimelineContext(random.Random(seed), NOW), None
    return process_folder_tree(str(manual), DiskConsultProvider(str(consult)), RealOps(), ctx, user)


@pytest.mark.parametrize("seed", [1, 2, 3, 7, 42, 2026])
def test_existing_account_matches_sc2(sc2, tmp_path: Path, seed: int) -> None:
    consult = build_library(tmp_path)
    original = build_manual(tmp_path)
    mine = tmp_path / "manual_mine" / "alice"
    shutil.copytree(original, mine)

    run_sc2(sc2, original, consult, seed)
    result = run_mine(mine, consult, seed)

    assert listing(mine) == listing(original)
    assert any(a.kind == "RENAME" for a in result.actions) and any(a.kind == "DUPLICATE" for a in result.actions)
    assert "ignored.txt" in listing(mine)
    # the sub-folder without a library twin is left untouched, as sc2 does
    assert [n for n in listing(mine) if n.startswith("newsub/")] == [f"newsub/{manual_name(2, 1_000_000_000)}"]


@pytest.mark.parametrize("seed", [1, 5, 99])
def test_new_account_matches_sc2(sc2, tmp_path: Path, seed: int) -> None:
    original = build_manual(tmp_path)
    mine = tmp_path / "manual_mine" / "alice"
    shutil.copytree(original, mine)
    missing_library = tmp_path / "library" / "00.MODELS" / "alice"  # does not exist: new account

    run_sc2(sc2, original, missing_library, seed, new_user=("777", "2025-12-14"))
    run_mine(mine, missing_library, seed, new_user=("777", "2025-12-14"))

    assert listing(mine) == listing(original)
    assert all("_777_manual" in Path(n).name for n in listing(mine) if n[0].isdigit() or "/" in n and n.split("/")[-1][0].isdigit())


def test_parity_helpers_are_deterministic(tmp_path: Path) -> None:
    consult = build_library(tmp_path)
    a = tmp_path / "a" / "alice"
    b = tmp_path / "b" / "alice"
    for target in (a, b):
        shutil.copytree(build_manual(tmp_path / target.parent.name), target)

    run_mine(a, consult, 11)
    run_mine(b, consult, 11)

    assert listing(a) == listing(b) and os.path.isdir(a)
