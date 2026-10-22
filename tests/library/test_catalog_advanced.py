from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.library.account_card import load_card, majority_owner, save_card, validate_card
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.trash import CONFIRM_WORD, TrashError, TrashService


@pytest.fixture()
def env(tmp_path: Path):
    lib = tmp_path / "4K"
    for group in ("00.A", "01.B"):
        (lib / group).mkdir(parents=True)
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    conn.execute("UPDATE path_roots SET path = ? WHERE code = 'LIBRARY'", (str(lib),))
    fs = FsOperationService(conn)
    ids = {}
    for group in ("00.A", "01.B"):
        fs.ensure_folder_rows(group)
    for name in ("ann", "bea", "cyd"):
        folder = lib / "00.A" / name
        folder.mkdir()
        (folder / "2025-01-01 10.00.00 111_900.jpg").write_bytes(b"12345")
        ids[name] = int(conn.execute(
            "INSERT INTO catalog_accounts (username, instagram_user_id, folder_id, status_id, created_at, updated_at, rel_path,"
            " disk_state) VALUES (?, ?, ?, 1, 'x', 'x', ?, 'PRESENT')",
            (name, str(900 + len(ids)), fs.folder_id_for_rel("00.A"), f"00.A\\{name}"),
        ).lastrowid)
    conn.commit()
    yield conn, lib, fs, ids
    conn.close()


def test_card_validations_and_save(env) -> None:
    conn, _lib, _fs, ids = env
    conn.execute("INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?, 0, 1, 1, 777, 0, '')", (ids["ann"],))
    codes = lambda owner, date="": {i.code for i in validate_card(conn, ids["ann"], owner, date)}  # noqa: E731

    assert codes("12a") == {"ID_NOT_NUMERIC"}
    assert "ID_DUPLICATED" in codes("901")  # bea's id
    assert "ID_DIFFERS_FROM_FILES" in codes("555") and majority_owner(conn, ids["ann"]) == "777"
    assert codes("777") == set()
    assert codes("777", "2025-13-40") == {"DATE_FORMAT"} and codes("777", "2999-01-01") == {"DATE_FUTURE"}

    blocked = save_card(conn, ids["ann"], owner_id="12a", start_date="", notes="x", favorite=False)
    assert blocked and load_card(conn, ids["ann"]).instagram_user_id == "900"  # nothing written
    save_card(conn, ids["ann"], owner_id="777", start_date="2025-02-03", notes=" nota ", favorite=True)
    card = load_card(conn, ids["ann"])
    assert (card.instagram_user_id, card.start_init_date, card.notes, card.is_favorite, card.status) == ("777", "2025-02-03", "nota", True, "ENABLED")


def test_move_several_accounts_in_one_plan_and_undo(env) -> None:
    conn, lib, fs, ids = env
    (lib / "01.B" / "bea").mkdir()  # clash for one of them
    target = fs.folder_id_for_rel("01.B")

    plan = fs.plan_move_accounts(list(ids.values()), target)

    assert len(plan.steps) == 2 and plan.affected_accounts == 2 and plan.can_execute
    assert any("@bea se omite" in c.message for c in plan.conflicts) and not plan.blocking
    group = fs.execute(plan)
    assert (lib / "01.B" / "ann").is_dir() and (lib / "01.B" / "cyd").is_dir() and (lib / "00.A" / "bea").is_dir()
    assert conn.execute("SELECT rel_path FROM catalog_accounts WHERE username='ann'").fetchone()[0] == "01.B\\ann"
    assert fs.undo(group)
    assert (lib / "00.A" / "ann").is_dir() and (lib / "00.A" / "cyd").is_dir()


def test_move_several_with_nothing_movable_is_blocked(env) -> None:
    _conn, _lib, fs, ids = env
    plan = fs.plan_move_accounts([ids["ann"]], fs.folder_id_for_rel("00.A"))  # already there
    assert not plan.can_execute and plan.blocking


def test_trash_quarantine_restore_and_purge(env) -> None:
    conn, lib, _fs, ids = env
    trash = TrashService(conn)

    item = trash.quarantine(ids["ann"])

    assert not (lib / "00.A" / "ann").exists() and trash.list_items()[0].username == "ann"
    assert (lib / ".trash").is_dir() and trash.list_items()[0].files == 1 and trash.list_items()[0].bytes == 5
    row = conn.execute("SELECT rel_path, disk_state, status_id FROM catalog_accounts WHERE id = ?", (ids["ann"],)).fetchone()
    assert row["rel_path"] is None and row["disk_state"] == "TRASHED" and row["status_id"] == 6

    trash.restore(item)
    assert (lib / "00.A" / "ann" / "2025-01-01 10.00.00 111_900.jpg").exists()
    row = conn.execute("SELECT rel_path, disk_state, status_id FROM catalog_accounts WHERE id = ?", (ids["ann"],)).fetchone()
    assert (row["rel_path"], row["disk_state"], row["status_id"]) == ("00.A\\ann", "PRESENT", 1)

    second = trash.quarantine(ids["ann"])
    with pytest.raises(TrashError, match="ELIMINAR"):
        trash.purge(None, "si")
    assert trash.purge([second], CONFIRM_WORD) == (1, 1, 5)
    assert not list((lib / ".trash").iterdir()) and not trash.list_items()


def test_restore_refuses_when_the_place_is_taken(env) -> None:
    conn, lib, _fs, ids = env
    trash = TrashService(conn)
    item = trash.quarantine(ids["ann"])
    (lib / "00.A" / "ann").mkdir()

    with pytest.raises(TrashError, match="ocupado"):
        trash.restore(item)
    assert trash.list_items()


def test_trash_blockers(env) -> None:
    conn, lib, _fs, ids = env
    trash = TrashService(conn)
    conn.execute("INSERT INTO staged_accounts (catalog_account_id, staging_rel, target_rel, status, staged_at) VALUES (?, 'a', 'a', 'STAGED', 'x')", (ids["bea"],))
    conn.commit()

    assert "almacen" in trash.blockers(ids["bea"])[0]
    with pytest.raises(TrashError):
        trash.quarantine(ids["bea"])
    assert (lib / "00.A" / "bea").is_dir()
    lib.rename(lib.parent / "off")
    assert "no esta disponible" in trash.blockers(ids["cyd"])[0]


def test_scanner_ignores_the_trash_folder() -> None:
    from ig_orchestrator.library.rules import DEFAULT_NON_ACCOUNT_NAMES

    assert ".trash" in DEFAULT_NON_ACCOUNT_NAMES
