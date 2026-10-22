from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from ig_orchestrator.db import Instance, InstanceRepository, connect, init_gui_database
from ig_orchestrator.exchange import manifest as manifest_module
from ig_orchestrator.exchange import publish as publish_module
from ig_orchestrator.exchange.inbox_scan import scan_exchange
from ig_orchestrator.exchange.manifest import (
    ManifestError,
    read_package,
    scan_packages,
    validate_manifest,
)
from ig_orchestrator.exchange.publish import (
    local_exchange_root,
    publish_batches,
    unpublished_batches,
)
from ig_orchestrator.exchange.result_import import import_package

NOW = "2026-10-10T10:00:00"


def code_id(conn, table: str, code: str) -> int:
    return conn.execute(f"SELECT id FROM {table} WHERE code = ?", (code,)).fetchone()[0]


def make_db(path: Path):
    init_gui_database(path)
    return connect(path)


def add_batch(conn, name: str, status: str, accounts: dict[str, list[tuple]], *, new: set[str] = frozenset()) -> int:
    """accounts: username -> [(url, type, status, error_code, retries)]"""

    batch_id = conn.execute(
        "INSERT INTO batches (name, schema_version, status_id, start_date, created_at, updated_at)"
        " VALUES (?, '1.0', ?, '2026-10-10', ?, ?)",
        (name, code_id(conn, "batch_statuses", status), NOW, NOW),
    ).lastrowid
    for order, (username, urls) in enumerate(accounts.items(), start=1):
        row = conn.execute("SELECT id FROM catalog_accounts WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        catalog_id = row[0] if row else conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, status_id, created_at, updated_at)"
            " VALUES (?, ?, 1, ?, ?)", (username, f"id_{username}", NOW, NOW)).lastrowid
        is_new = int(username in new)
        ba = conn.execute(
            "INSERT INTO batch_accounts (batch_id, catalog_account_id, download_stories, is_new_account,"
            " rename_owner_id, rename_start_init_date, rename_destination_path, status_id, sort_order,"
            " created_at, updated_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, catalog_id, is_new, f"id_{username}" if is_new else None,
             "2026-01-01" if is_new else None, "G:\\4K Stogram\\00.MODELS-A" if is_new else None,
             code_id(conn, "batch_account_statuses", "COMPLETED"), order, NOW, NOW),
        ).lastrowid
        for url, ptype, status, error, retries in urls:
            conn.execute(
                "INSERT INTO batch_urls (batch_account_id, url, publication_type_id, source_id, status_id, retries,"
                " last_error_id, last_error_text, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ba, url, code_id(conn, "publication_types", ptype), code_id(conn, "url_sources", "INPUT_URL"),
                 code_id(conn, "batch_url_statuses", status), retries,
                 code_id(conn, "bot_errors", error) if error else None, f"err {error}" if error else None, NOW, NOW),
            )
    conn.commit()
    return batch_id


def write_files(root: Path, layout: dict[str, dict[str, bytes]]) -> None:
    for username, files in layout.items():
        for rel, data in files.items():
            target = root / username / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


@pytest.fixture()
def worker(tmp_path: Path):
    conn = make_db(tmp_path / "worker.sqlite")
    working = tmp_path / "worker_work"
    exchange = tmp_path / "shared"
    exchange.mkdir()
    batch_id = add_batch(
        conn, "descargas_1", "AWAITING_RENAME",
        {
            "alice": [("https://www.instagram.com/p/A1/", "POST", "COMPLETED", None, 0),
                      ("https://www.instagram.com/stories/alice/", "STORY", "FAILED_FINAL", "STORIES_NOT_FOUND", 2)],
            "newgirl": [("https://www.instagram.com/reel/N1/", "REEL", "COMPLETED", None, 1)],
        },
        new={"newgirl"},
    )
    write_files(working, {
        "alice": {"a1.jpg": b"1" * 10, "story/s1.mp4": b"2" * 20},
        "newgirl": {"reels/n1.mp4": b"3" * 30},
    })
    yield conn, working, exchange, batch_id
    conn.close()


@pytest.fixture()
def main(tmp_path: Path):
    conn = make_db(tmp_path / "main.sqlite")
    now = NOW
    conn.execute("INSERT INTO catalog_accounts (username, instagram_user_id, status_id, created_at, updated_at)"
                 " VALUES ('alice', 'id_alice', 1, ?, ?)", (now, now))
    conn.commit()
    working = tmp_path / "main_work"
    working.mkdir()
    yield conn, working
    conn.close()


def publish(worker, mode="MOVE", **kwargs):
    conn, working, exchange, batch_id = worker
    return publish_batches(conn, [batch_id], working, exchange, instance="inst1", mode=mode, **kwargs)


def test_publish_builds_a_complete_atomic_package(worker) -> None:
    conn, working, exchange, batch_id = worker

    result = publish(worker)

    assert result.ok and result.accounts == 2 and result.files == 3 and result.bytes == 60
    assert result.path.parent == exchange and not list(exchange.glob("*.partial"))
    package = read_package(result.path)
    assert package.problem == "" and package.source_instance == "inst1" and package.batch_names == ["descargas_1"]
    assert (result.path / "data/alice/story/s1.mp4").read_bytes() == b"2" * 20
    account = next(a for a in package.manifest["batches"][0]["accounts"] if a["username"] == "alice")
    assert account["files"] == {"count": 2, "bytes": 30}
    assert [(u["type"], u["status"], u["error_code"]) for u in account["urls"]] == [
        ("POST", "COMPLETED", None), ("STORY", "FAILED_FINAL", "STORIES_NOT_FOUND")]
    newgirl = next(a for a in package.manifest["batches"][0]["accounts"] if a["username"] == "newgirl")
    assert newgirl["is_new_account"] and newgirl["rename"]["destination_path"].endswith("00.MODELS-A")
    row = conn.execute("SELECT status, files FROM exchange_publications").fetchone()
    assert (row["status"], row["files"]) == ("PUBLISHED", 3)
    assert unpublished_batches(conn) == []


def test_move_removes_sources_and_copy_keeps_them(worker, tmp_path: Path) -> None:
    conn, working, exchange, batch_id = worker
    publish(worker, mode="COPY")
    assert (working / "alice/a1.jpg").exists()
    conn.execute("DELETE FROM exchange_publications")
    conn.commit()

    publish(worker, mode="MOVE")

    assert not (working / "alice").exists() and not (working / "newgirl").exists()


def test_missing_account_folder_is_reported_not_fatal(worker) -> None:
    conn, working, exchange, batch_id = worker
    import shutil

    shutil.rmtree(working / "newgirl")

    result = publish(worker, mode="COPY")

    assert result.ok and result.missing_accounts == ["newgirl"]
    package = read_package(result.path)
    assert next(a for a in package.manifest["batches"][0]["accounts"] if a["username"] == "newgirl")["folder"] is None


def test_offline_exchange_records_pending_and_blocks_nothing(worker, tmp_path: Path) -> None:
    conn, working, exchange, batch_id = worker

    result = publish_batches(conn, [batch_id], working, tmp_path / "gone", instance="inst1")

    assert not result.ok and "no esta disponible" in result.error
    assert conn.execute("SELECT status FROM exchange_publications").fetchone()[0] == "PENDING"
    assert (working / "alice/a1.jpg").exists()
    assert unpublished_batches(conn) != []  # can be retried


def test_cut_during_copy_never_leaves_a_valid_package_and_keeps_sources(worker, monkeypatch) -> None:
    conn, working, exchange, batch_id = worker
    real = publish_module._copy_verified
    calls = {"n": 0}

    def flaky(source, destination, size):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("network down")
        real(source, destination, size)

    monkeypatch.setattr(publish_module, "_copy_verified", flaky)

    result = publish(worker)

    assert not result.ok and "network down" in result.error
    partials = list(exchange.glob("*.partial"))
    assert len(partials) == 1 and not (partials[0] / "manifest.json").exists()
    assert (working / "alice/a1.jpg").exists() and (working / "newgirl/reels/n1.mp4").exists()
    packages = scan_packages(exchange)
    assert len(packages) == 1 and packages[0].problem
    assert scan_exchange(exchange, stable_seconds=0) == []  # not offered as a loose account folder
    assert conn.execute("SELECT status FROM exchange_publications").fetchone()[0] == "FAILED"


def test_cancel_removes_the_partial_package(worker) -> None:
    cancel = threading.Event()
    cancel.set()

    result = publish(worker, cancel_event=cancel)

    assert result.cancelled and not result.ok
    assert list(worker[2].iterdir()) == []


def test_validate_manifest_rules() -> None:
    good = {"format": "ig_orchestrator.batch_result", "format_version": "1", "package_id": "x",
            "min_reader_version": "3.6.0", "batches": []}
    assert validate_manifest(good, app_version="3.6.0")
    with pytest.raises(ManifestError):
        validate_manifest({**good, "format": "other"})
    with pytest.raises(ManifestError):
        validate_manifest({**good, "format_version": "2"})
    with pytest.raises(ManifestError, match="requiere"):
        validate_manifest({**good, "min_reader_version": "9.0.0"}, app_version="3.6.0")
    with pytest.raises(ManifestError):
        validate_manifest({**good, "batches": None})
    assert manifest_module.parse_version("3.10.1") > manifest_module.parse_version("3.9.9")


def test_import_creates_batch_with_real_states_and_pulls_files(worker, main) -> None:
    published = publish(worker)
    conn, working = main

    result = import_package(conn, read_package(published.path), working)

    assert result.ok and result.batches_created == 1 and result.accounts == 2 and result.urls == 3
    assert (working / "alice/story/s1.mp4").exists() and (working / "newgirl/reels/n1.mp4").exists()
    rows = {
        (r["username"], r["url"][-6:]): (r["status"], r["last_error_type"], r["retries"])
        for r in conn.execute(
            "SELECT a.username, u.url, u.status, u.last_error_type, u.retries FROM url_jobs u"
            " JOIN batch_accounts ba ON ba.id = u.account_id JOIN catalog_accounts a ON a.id = ba.catalog_account_id")
    }
    assert rows[("alice", "alice/")] == ("FAILED_FINAL", "STORIES_NOT_FOUND", 2)
    assert rows[("alice", "/p/A1/")][0] == "COMPLETED"
    assert not conn.execute("SELECT 1 FROM url_jobs WHERE last_error LIKE '%another instance%'").fetchone()
    batch = conn.execute("SELECT b.id, b.name, bs.code FROM batches b JOIN batch_statuses bs ON bs.id = b.status_id").fetchone()
    assert (batch["name"], batch["code"]) == ("descargas_1", "AWAITING_RENAME")
    new = conn.execute("SELECT * FROM batch_accounts WHERE is_new_account = 1").fetchone()
    assert (new["rename_owner_id"], new["rename_start_init_date"]) == ("id_newgirl", "2026-01-01")
    assert new["rename_destination_path"].endswith("00.MODELS-A")
    assert conn.execute("SELECT summary FROM batch_runs").fetchone()[0].startswith("Imported from inst1 (package ")
    assert conn.execute("SELECT COUNT(*) FROM exchange_imports").fetchone()[0] == 1
    assert (published.path / "imported.json").exists()
    assert not (published.path / "data/alice/a1.jpg").exists()  # consumed


def test_import_is_idempotent(worker, main) -> None:
    published = publish(worker, mode="COPY")
    conn, working = main
    first = import_package(conn, read_package(published.path), working, keep_source=True)

    second = import_package(conn, read_package(published.path), working, keep_source=True)

    assert first.ok and second.ok and second.skipped_duplicate
    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM batch_urls").fetchone()[0] == 3


def test_import_attaches_to_existing_draft_batch(worker, main) -> None:
    published = publish(worker)
    conn, working = main
    add_batch(conn, "descargas_1", "DRAFT", {"alice": [("https://www.instagram.com/p/A1/", "POST", "PENDING", None, 0)]})

    result = import_package(conn, read_package(published.path), working)

    assert result.ok and result.batches_attached == 1 and result.batches_created == 0
    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
    status = conn.execute("SELECT status FROM url_jobs WHERE url LIKE '%/p/A1/'").fetchone()[0]
    assert status == "COMPLETED"
    assert conn.execute("SELECT COUNT(*) FROM batch_urls WHERE url LIKE '%/p/A1/'").fetchone()[0] == 1  # updated, not duplicated


def test_import_name_clash_with_finished_batch_creates_suffixed_batch(worker, main) -> None:
    published = publish(worker)
    conn, working = main
    add_batch(conn, "descargas_1", "COMPLETED", {"alice": []})

    result = import_package(conn, read_package(published.path), working)

    names = sorted(r[0] for r in conn.execute("SELECT name FROM batches"))
    assert result.ok and names == ["descargas_1", "descargas_1_inst1"]
    assert any("ya existia" in w for w in result.warnings)


def test_import_resolves_account_by_instagram_id_when_username_changed(worker, main) -> None:
    published = publish(worker)
    conn, working = main
    conn.execute("UPDATE catalog_accounts SET username = 'alice_renamed' WHERE username = 'alice'")
    conn.commit()

    result = import_package(conn, read_package(published.path), working)

    assert result.ok and any("alice_renamed" in w for w in result.warnings)
    assert conn.execute("SELECT COUNT(*) FROM catalog_accounts WHERE username = 'alice'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM catalog_accounts").fetchone()[0] == 2  # + newgirl


def test_corrupt_package_is_rejected_without_touching_anything(worker, main) -> None:
    published = publish(worker)
    conn, working = main
    (published.path / "data/alice/a1.jpg").write_bytes(b"tampered")

    result = import_package(conn, read_package(published.path), working)

    assert not result.ok and "danado" in result.error
    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 0
    assert not list(working.iterdir())


def test_incompatible_version_is_reported(worker, main) -> None:
    published = publish(worker)
    manifest_path = published.path / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["min_reader_version"] = "99.0.0"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    conn, working = main

    package = read_package(published.path)
    result = import_package(conn, package, working)

    assert "requiere" in package.problem and not result.ok


def test_local_exchange_root_comes_from_the_local_instance(worker) -> None:
    conn, _working, _exchange, _batch = worker
    assert local_exchange_root(conn) is None
    InstanceRepository(conn).save(
        Instance(None, "inst1", "WORKER", is_local=True, exchange_local_path=r"C:\Eduardo\ig_orchestrator\tmp")
    )
    assert local_exchange_root(conn) == Path(r"C:\Eduardo\ig_orchestrator\tmp")
