from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.owner_groups import (
    ALL_DELETED,
    CROSS_CATEGORY,
    RENAME_PROBABLE,
    SAME_CATEGORY,
    find_owner_groups,
    ignore_group,
    unignore_group,
)

NOW = "2026-01-01T00:00:00"


@pytest.fixture()
def conn(tmp_path: Path):
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    connection = connect(db)
    yield connection
    connection.close()


def add(conn, username: str, owner: str | None, rel: str, last: str = "2026-06-01 00:00:00", status: str = "ENABLED", content: int = 5) -> None:
    conn.execute(
        "INSERT INTO catalog_accounts (username, instagram_user_id, status_id, created_at, updated_at, rel_path,"
        " last_media_at, posts_count) SELECT ?, ?, id, ?, ?, ?, ?, ? FROM catalog_account_statuses WHERE code = ?",
        (username, owner, NOW, NOW, rel, last, content, status),
    )
    conn.commit()


def hints(conn) -> dict[str, str]:
    return {g.owner_id: g.hint for g in find_owner_groups(conn)}


def test_groups_need_two_accounts_with_the_same_id(conn) -> None:
    add(conn, "solo", "1", "00.FAVORITES\\solo")
    add(conn, "empty1", None, "00.FAVORITES\\e1")
    add(conn, "empty2", "", "00.FAVORITES\\e2")

    assert find_owner_groups(conn) == []


def test_active_account_with_a_deleted_one_is_a_probable_rename(conn) -> None:
    add(conn, "new_name", "10", "00.FAVORITES\\Group\\new_name", last="2026-09-01 00:00:00")
    add(conn, "old_name", "10", "09.DELETED\\old_name", last="2024-01-01 00:00:00")
    add(conn, "old_two", "11", "00.FAVORITES\\Group\\old_two", last="2026-09-01 00:00:00")
    add(conn, "old_two_x", "11", "00.FAVORITES\\Group-Deleted\\old_two_x", last="2025-01-01 00:00:00")

    group = {g.owner_id: g for g in find_owner_groups(conn)}

    assert group["10"].hint == RENAME_PROBABLE and group["10"].suggested_current == "new_name"
    assert group["11"].hint == RENAME_PROBABLE and group["11"].suggested_current == "old_two"


def test_clearly_older_active_member_is_a_probable_rename(conn) -> None:
    add(conn, "recent", "20", "00.MODELS-A\\recent", last="2026-09-01 00:00:00")
    add(conn, "ancient", "20", "00.MODELS-A\\ancient", last="2022-01-01 00:00:00")

    assert hints(conn) == {"20": RENAME_PROBABLE}


def test_same_category_cross_category_and_all_deleted(conn) -> None:
    add(conn, "a1", "30", "00.FAVORITES\\a1", last="2026-09-01 00:00:00")
    add(conn, "a2", "30", "00.FAVORITES\\a2", last="2026-08-01 00:00:00")
    add(conn, "b1", "31", "00.FAVORITES\\b1", last="2026-09-01 00:00:00")
    add(conn, "b2", "31", "00.MODELS-A\\b2", last="2026-08-01 00:00:00")
    add(conn, "d1", "32", "09.DELETED\\d1")
    add(conn, "d2", "32", "09.DELETED\\d2")

    assert hints(conn) == {"30": SAME_CATEGORY, "31": CROSS_CATEGORY, "32": ALL_DELETED}


def test_groups_are_sorted_most_actionable_first(conn) -> None:
    add(conn, "d1", "1", "09.DELETED\\d1")
    add(conn, "d2", "1", "09.DELETED\\d2")
    add(conn, "n", "2", "00.FAVORITES\\n", last="2026-09-01 00:00:00")
    add(conn, "o", "2", "09.DELETED\\o", last="2020-01-01 00:00:00")

    assert [g.hint for g in find_owner_groups(conn)] == [RENAME_PROBABLE, ALL_DELETED]


def test_ignored_groups_disappear_until_unignored(conn) -> None:
    add(conn, "a1", "30", "00.FAVORITES\\a1")
    add(conn, "a2", "30", "00.FAVORITES\\a2")

    ignore_group(conn, "30", "no es renombrado")
    assert find_owner_groups(conn) == []
    assert [g.owner_id for g in find_owner_groups(conn, include_ignored=True)] == ["30"]

    unignore_group(conn, "30")
    assert [g.owner_id for g in find_owner_groups(conn)] == ["30"]
