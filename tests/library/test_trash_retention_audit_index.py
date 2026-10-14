from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.audit import run_audit
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.trash import CONFIRM_WORD, TrashService, configured_retention_days


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K"
    (lib / "00.A").mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    fs.ensure_folder_rows("00.A")

    def account(name: str, files: int = 1) -> int:
        folder = lib / "00.A" / name
        folder.mkdir()
        for i in range(files):
            (folder / f"2025-01-0{i + 1} 10.00.00 {100 + i}_900.jpg").write_bytes(b"12345")
        return int(conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at,"
            " rel_path, disk_state, posts_count) VALUES (?, '900', ?, 1, 'x', 'x', ?, 'PRESENT', ?)",
            (name, fs.folder_id_for_rel("00.A"), f"00.A\\{name}", files)).lastrowid)

    yield conn, lib, account
    conn.close()


def insert_row(conn, table: str, **given) -> int:
    """Insert a row filling every NOT NULL column that has no default (enough for foreign-key checks)."""

    values = dict(given)
    for _cid, column, kind, notnull, default, pk in conn.execute(f"PRAGMA table_info({table})").fetchall():
        if column in values or pk or not notnull or default is not None:
            continue
        values[column] = 1 if "INT" in str(kind).upper() else "x"
    cursor = conn.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
    return int(cursor.lastrowid)


def set_setting(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO app_settings (key, value, value_type, updated_at) VALUES (?, ?, 'TEXT', 'x')"
                 " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def test_retention_setting_sets_the_expiry_and_expired_items_are_listed(env) -> None:
    conn, _lib, account = env
    assert configured_retention_days(conn) is None
    set_setting(conn, "trash.retention_days", "30")
    assert configured_retention_days(conn) == 30
    trash = TrashService(conn)
    aid = account("ana")

    trash.quarantine(aid)

    item = trash.list_items()[0]
    assert item.expires_at and item.expires_at[:4] >= str(datetime.now().year)
    assert trash.expired() == []
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    conn.execute("UPDATE trash_items SET expires_at = ?", (past,))
    conn.commit()
    assert [i.username for i in trash.expired()] == ["ana"]
    set_setting(conn, "trash.retention_days", "abc")
    assert configured_retention_days(conn) is None


def test_purge_expired_then_remove_the_accounts_from_the_catalog(env) -> None:
    conn, lib, account = env
    trash = TrashService(conn)
    a, b = account("ana"), account("bea")
    conn.execute("INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?, 0, 1, 1, 900, 0, '')", (a,))
    trash.quarantine(a)
    trash.quarantine(b)

    trash.purge([i.id for i in trash.list_items() if i.username == "ana"], CONFIRM_WORD)
    removed, kept = trash.remove_from_catalog([a])

    assert (removed, kept) == (1, [])
    assert conn.execute("SELECT 1 FROM catalog_accounts WHERE id = ?", (a,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM media_index WHERE account_id = ?", (a,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM catalog_accounts WHERE id = ?", (b,)).fetchone() is not None  # untouched
    assert [i.username for i in trash.list_items()] == ["bea"]
    assert trash.remove_from_catalog([b]) == (0, ["bea"])  # still in the trash: kept


def test_account_used_by_a_batch_is_kept(env) -> None:
    conn, _lib, account = env
    trash = TrashService(conn)
    aid = account("ana")
    trash.quarantine(aid)
    trash.purge(None, CONFIRM_WORD)
    batch_id = insert_row(conn, "batches", name="lote")
    insert_row(conn, "batch_accounts", batch_id=batch_id, catalog_account_id=aid)
    conn.commit()

    removed, kept = trash.remove_from_catalog([aid])

    assert removed == 0 and kept == ["ana"]
    assert conn.execute("SELECT 1 FROM catalog_accounts WHERE id = ?", (aid,)).fetchone() is not None


def test_audit_reports_missing_and_stale_index(env) -> None:
    conn, _lib, account = env
    missing = account("missing", files=2)  # counters say 2 files, the index is empty
    stale = account("stale", files=3)
    for i in range(2):
        conn.execute("INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?, 0, ?, 1, 900, 0, '')", (stale, i))
    ok = account("fine", files=1)
    conn.execute("INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?, 0, 9, 1, 900, 0, '')", (ok,))
    conn.commit()

    report = run_audit(conn, None, check_disk=False)

    by_code = {(f.code, f.username): f for f in report.findings}
    assert ("INDEX_MISSING", "missing") in by_code and "2 ficheros" in by_code[("INDEX_MISSING", "missing")].detail
    assert ("INDEX_STALE", "stale") in by_code and "posts 3 vs indice 2" in by_code[("INDEX_STALE", "stale")].detail
    assert not [k for k in by_code if k[1] == "fine"]
    assert missing and ok
