from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.folder_suggestions import find_folder_matches, split_state, suggest_destinations


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K"
    for rel in ("00.FAV\\Ana-Model", "00.FAV\\Ana-Model-Deleted", "00.FAV\\Ana-Model-Inactive", "00.FAV\\Bea-Model",
                "09.DELETED", "04.OLD\\Cy-Model"):
        (lib / rel).mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    for rel in ("00.FAV\\Ana-Model", "00.FAV\\Ana-Model-Deleted", "00.FAV\\Ana-Model-Inactive", "00.FAV\\Bea-Model", "09.DELETED", "04.OLD\\Cy-Model"):
        fs.ensure_folder_rows(rel)

    def account(name: str, parent: str, previous: str | None = None) -> int:
        (lib / parent / name).mkdir(exist_ok=True)
        return int(conn.execute(
            "INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at, rel_path, previous_rel_path)"
            " VALUES (?, ?, 1, 'x', 'x', ?, ?)", (name, fs.folder_id_for_rel(parent), f"{parent}\\{name}", previous)).lastrowid)

    yield conn, account
    conn.close()


def names(suggestions) -> list[str]:
    return [s.label for s in suggestions]


def test_split_state() -> None:
    assert split_state("Ana-Model") == ("Ana-Model", "active")
    assert split_state("Ana-Model-Deleted") == ("Ana-Model", "deleted")
    assert split_state("Ana-Model-Inactive") == ("Ana-Model", "inactive")
    assert split_state("X-delete") == ("X", "deleted")


def test_from_the_main_folder_suggests_deleted_inactive_and_the_deleted_folder(env) -> None:
    conn, account = env
    aid = account("ana1", "00.FAV\\Ana-Model")

    result = suggest_destinations(conn, [aid])

    assert names(result) == ["Ana-Model-Deleted", "Ana-Model-Inactive", "09.DELETED"]
    assert all(s.folder_id is not None for s in result) and len(result) == 3


def test_from_deleted_suggests_the_inverse(env) -> None:
    conn, account = env
    aid = account("ana2", "00.FAV\\Ana-Model-Deleted")

    assert names(suggest_destinations(conn, [aid])) == ["Ana-Model", "Ana-Model-Inactive"]
    aid2 = account("ana3", "00.FAV\\Ana-Model-Inactive")
    assert names(suggest_destinations(conn, [aid2])) == ["Ana-Model", "Ana-Model-Deleted"]


def test_missing_sibling_is_offered_as_a_folder_to_create(env) -> None:
    conn, account = env
    aid = account("bea1", "00.FAV\\Bea-Model")

    result = suggest_destinations(conn, [aid])

    created = [s for s in result if s.folder_id is None]
    assert [s.rel for s in created] == ["00.FAV\\Bea-Model-Deleted", "00.FAV\\Bea-Model-Inactive"]
    assert names(result)[0] == "09.DELETED"  # existing folders come before the ones to create
    assert len(result) == 3


def test_previous_place_is_suggested_and_multi_selection_uses_the_common_folder(env) -> None:
    conn, account = env
    a1 = account("ana4", "00.FAV\\Ana-Model-Deleted", previous="04.OLD\\Cy-Model\\ana4")
    a2 = account("ana5", "00.FAV\\Ana-Model-Deleted")

    result = suggest_destinations(conn, [a1, a2])

    assert names(result) == ["Ana-Model", "Ana-Model-Inactive", "Cy-Model"]
    assert result[2].reason == "previous"
    assert suggest_destinations(conn, []) == []


def test_find_folder_matches_orders_exact_then_prefix() -> None:
    folders = [(1, "Ana-Model-Deleted", "a\\Ana-Model-Deleted"), (2, "Ana", "a\\Ana"), (3, "Bana", "b\\Bana"), (4, "Ana-Model", "a\\Ana-Model")]

    assert find_folder_matches(folders, "ana") == [2, 4, 1, 3]
    assert find_folder_matches(folders, "  DELETED ") == [1]
    assert find_folder_matches(folders, "zzz") == [] and find_folder_matches(folders, "") == []
