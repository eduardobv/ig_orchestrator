from __future__ import annotations

import json
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.gui.catalog.service import AccountCatalogService
from ig_orchestrator.gui.catalog.tree import build_catalog_tree
from ig_orchestrator.models import AccountHistoryStatus

ROOT = r"G:\4K Stogram"


@pytest.fixture()
def env(tmp_path: Path):
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    now = "2026-01-01T00:00:00"
    folder = conn.execute(
        "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at)"
        " VALUES (NULL, 'Adrianna-Eves-Deleted', ?, 2, ?, ?)",
        (ROOT + r"\00.FAVORITES\Adrianna-Eves-Deleted", now, now),
    ).lastrowid

    def add(name: str, status: str, owner: str | None, folder_id: int | None) -> None:
        conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at)"
            " SELECT ?, ?, ?, id, ?, ? FROM catalog_account_statuses WHERE code = ?",
            (name, owner, folder_id, now, now, status),
        )

    add("alive", "ENABLED", "1", folder)
    add("adrieves19", "DELETED", "5596276486", folder)
    conn.commit()
    batch_json = tmp_path / "batch.json"
    batch_json.write_text(
        json.dumps({"accounts": [{"username": "adrieves19"}, {"username": "vinskawy"}, {"username": "alive"}]}),
        encoding="utf-8",
    )
    yield AccountCatalogService(conn, batch_json_path=batch_json, backup_dir=tmp_path / "none"), conn
    conn.close()


def names(entries) -> list[str]:
    return sorted(e.username for e in entries)


def test_batch_json_does_not_create_ghost_entries_when_db_has_accounts(env) -> None:
    service, _conn = env

    entries = service.list_entries()

    assert names(entries) == ["alive"]  # no 'vinskawy' ghost, no no-path duplicate of the hidden deleted account
    assert all(e.source == "account_history" for e in entries)


def test_deleted_account_is_shown_in_the_tree_under_its_new_folder(env) -> None:
    service, _conn = env
    service.include_deleted = True

    entries = service.list_entries()
    deleted = next(e for e in entries if e.username == "adrieves19")
    roots = build_catalog_tree(entries)

    assert deleted.status is AccountHistoryStatus.DELETED
    assert deleted.destination_path.endswith("Adrianna-Eves-Deleted") and deleted.owner_id == "5596276486"
    assert [r.name for r in roots] == [ROOT]  # nothing under "Sin ruta"
    folder = roots[0].children[0].children[0]
    assert folder.name == "Adrianna-Eves-Deleted" and sorted(c.name for c in folder.children) == ["adrieves19", "alive"]


def test_find_entry_returns_hidden_accounts_with_current_path(env) -> None:
    service, _conn = env

    entry = service.find_entry("ADRIEVES19")

    assert entry is not None and entry.destination_path.endswith("Adrianna-Eves-Deleted")
    assert service.find_entry("nobody") is None


def test_batch_json_still_bootstraps_an_empty_catalog(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    batch_json = tmp_path / "batch.json"
    batch_json.write_text(json.dumps({"accounts": [{"username": "fresh"}]}), encoding="utf-8")

    entries = AccountCatalogService(conn, batch_json_path=batch_json).list_entries()

    assert names(entries) == ["fresh"]
    conn.close()
