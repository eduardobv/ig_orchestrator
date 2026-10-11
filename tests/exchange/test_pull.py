from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from ig_orchestrator.db import InstanceRepository, connect, init_gui_database
from ig_orchestrator.db.instances_repository import Instance
from ig_orchestrator.exchange import (
    ExchangeUnavailableError,
    PullPolicy,
    execute_pull,
    plan_pull,
    scan_exchange,
)
from ig_orchestrator.exchange.compare import compare_with_batch, probe_path


def _write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture()
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    exchange = tmp_path / "exchange"
    work = tmp_path / "work"
    exchange.mkdir()
    work.mkdir()
    return exchange, work


def _age(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    for item in [path, *path.rglob("*")]:
        os.utime(item, (stamp, stamp))


def test_scan_reports_stability_and_empty(dirs) -> None:
    exchange, _ = dirs
    _write(exchange / "old_user" / "1.jpg", b"aa")
    _age(exchange / "old_user", 600)
    _write(exchange / "busy_user" / "2.jpg", b"bbb")
    (exchange / "empty_user").mkdir()
    _write(exchange / "old_user" / "3.mp4.part", b"ignored")
    (exchange / "stray.txt").write_text("not a folder")

    folders = {f.name: f for f in scan_exchange(exchange, stable_seconds=30)}

    assert set(folders) == {"busy_user", "empty_user", "old_user"}
    assert folders["old_user"].is_stable and folders["old_user"].file_count == 1
    assert folders["old_user"].total_bytes == 2
    assert not folders["busy_user"].is_stable
    assert folders["empty_user"].is_empty


def test_scan_unavailable(tmp_path: Path) -> None:
    with pytest.raises(ExchangeUnavailableError):
        scan_exchange(tmp_path / "nope", stable_seconds=1)


def test_move_pulls_all_files_and_removes_source(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "u1" / "a.jpg", b"1")
    _write(exchange / "u1" / "story" / "b.mp4", b"22")
    folders = scan_exchange(exchange, stable_seconds=0)

    result = execute_pull(plan_pull(folders, work))

    assert result.ok
    assert (work / "u1" / "a.jpg").read_bytes() == b"1"
    assert (work / "u1" / "story" / "b.mp4").read_bytes() == b"22"
    assert not (exchange / "u1").exists()
    assert not list(work.rglob("*.part"))


def test_keep_source_copies(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "u1" / "a.jpg", b"1")

    result = execute_pull(plan_pull(scan_exchange(exchange, stable_seconds=0), work, keep_source=True))

    assert result.ok
    assert (exchange / "u1" / "a.jpg").exists() and (work / "u1" / "a.jpg").exists()


def test_merge_skips_identical_and_suffixes_different(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "u1" / "same.jpg", b"AAAA")
    _write(exchange / "u1" / "diff.jpg", b"BBBBBB")
    _write(exchange / "u1" / "new.jpg", b"C")
    _write(work / "u1" / "same.jpg", b"ZZZZ")  # same size -> skipped
    _write(work / "u1" / "diff.jpg", b"Q")  # other size -> suffixed

    result = execute_pull(plan_pull(scan_exchange(exchange, stable_seconds=0), work))

    folder = result.folders[0]
    assert (folder.copied, folder.skipped_identical, folder.renamed) == (2, 1, 1)
    assert (work / "u1" / "same.jpg").read_bytes() == b"ZZZZ"
    assert (work / "u1" / "diff.jpg").read_bytes() == b"Q"
    assert (work / "u1" / "diff_1.jpg").read_bytes() == b"BBBBBB"
    assert (work / "u1" / "new.jpg").exists()
    assert not (exchange / "u1").exists()


def test_abort_policy_blocks_existing(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "u1" / "a.jpg")
    (work / "u1").mkdir()

    plan = plan_pull(scan_exchange(exchange, stable_seconds=0), work, PullPolicy.ABORT)
    result = execute_pull(plan)

    assert result.folders[0].blocked_reason
    assert (exchange / "u1" / "a.jpg").exists()


def test_destination_case_variant_is_reused(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "User1" / "a.jpg")
    (work / "user1").mkdir()

    plan = plan_pull(scan_exchange(exchange, stable_seconds=0), work)

    assert plan.folders[0].destination.name == "user1"


def test_cancel_keeps_source_and_leaves_no_part_files(dirs) -> None:
    exchange, work = dirs
    for i in range(5):
        _write(exchange / "u1" / f"{i}.jpg", b"x")
    cancel = threading.Event()

    def stop_after_two(_folder: str, done: int, _total: int) -> None:
        if done == 2:
            cancel.set()

    result = execute_pull(
        plan_pull(scan_exchange(exchange, stable_seconds=0), work),
        progress=stop_after_two,
        cancel_event=cancel,
    )

    assert result.cancelled
    assert len(list((exchange / "u1").glob("*.jpg"))) == 3
    assert len(list((work / "u1").glob("*.jpg"))) == 2
    assert not list(work.rglob("*.part"))


def test_orphan_part_is_cleaned_and_resumed(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "u1" / "a.jpg", b"123")
    _write(work / "u1" / "a.jpg.part", b"1")

    result = execute_pull(plan_pull(scan_exchange(exchange, stable_seconds=0), work))

    assert result.ok
    assert (work / "u1" / "a.jpg").read_bytes() == b"123"
    assert not list(work.rglob("*.part"))


def test_source_file_vanishes_is_reported(dirs) -> None:
    exchange, work = dirs
    _write(exchange / "u1" / "a.jpg")
    _write(exchange / "u1" / "b.jpg")
    plan = plan_pull(scan_exchange(exchange, stable_seconds=0), work)
    plan.folders[0].files[0].source.unlink()

    result = execute_pull(plan)

    assert result.folders[0].errors
    assert not result.ok
    assert (exchange / "u1").exists()


def test_probe_path(tmp_path: Path) -> None:
    ok = probe_path(tmp_path)
    assert ok.ok and ok.writable and ok.free_bytes
    assert not probe_path(tmp_path / "missing").ok
    assert not list(tmp_path.glob(".probe_*"))


def test_instances_repository_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    with connect(db) as connection:
        repo = InstanceRepository(connection)
        pc1 = repo.save(Instance(None, "pc1", "MAIN", is_local=True, working_path=r"C:\w"))
        inst1 = repo.save(
            Instance(None, "inst1", "WORKER", exchange_path=r"\\HOST\share\tmp", is_local=True)
        )
        assert repo.get_local().id == inst1  # only one local at a time
        assert repo.get(pc1).is_local is False
        assert repo.get(inst1).pull_source == r"\\HOST\share\tmp"
        with pytest.raises(ValueError):
            repo.save(Instance(None, "pc1", "MAIN"))
        with pytest.raises(ValueError):
            repo.save(Instance(None, " ", "MAIN"))
        repo.delete(pc1)
        assert [i.name for i in repo.list()] == ["inst1"]


def test_compare_with_batch(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    with connect(db) as connection:
        now = "2026-01-01T00:00:00"
        connection.execute(
            "INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
            " SELECT 'b1', 1, id, '2026-01-01', ?, ? FROM batch_statuses LIMIT 1",
            (now, now),
        )
        batch_id = connection.execute("SELECT id FROM batches").fetchone()[0]
        for index, name in enumerate(("Alpha", "beta", "gamma")):
            connection.execute(
                "INSERT INTO catalog_accounts (username, status_id, created_at, updated_at)"
                " VALUES (?, 1, ?, ?)",
                (name, now, now),
            )
            connection.execute(
                "INSERT INTO batch_accounts (batch_id, catalog_account_id, status_id, sort_order,"
                " created_at, updated_at) SELECT ?, last_insert_rowid(), id, ?, ?, ? "
                "FROM batch_account_statuses LIMIT 1",
                (batch_id, index, now, now),
            )
        result = compare_with_batch(connection, batch_id, ["alpha", "BETA", "other"])

    assert result.received == ["Alpha", "beta"]
    assert result.missing == ["gamma"]
    assert result.extra == ["other"]
