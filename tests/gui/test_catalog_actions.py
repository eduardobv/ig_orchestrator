from __future__ import annotations

import json
from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.gui.catalog.service import AccountCatalogService
from ig_orchestrator.gui.catalog.tree import build_catalog_tree
from ig_orchestrator.gui.library.plan_dialog import plan_rows
from ig_orchestrator.library.fsops_plan import Conflict, OpType, Plan, Step

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"
ROOT = r"G:\4K Stogram"


def test_tree_shows_empty_folders() -> None:
    roots = build_catalog_tree([], extra_folder_paths=[ROOT + r"\00.FAVORITES\Maria-Perez"])

    node = roots[0]
    assert node.name == ROOT
    assert [c.name for c in node.children] == ["00.FAVORITES"]
    assert [c.name for c in node.children[0].children] == ["Maria-Perez"]


def test_service_lists_only_folders_without_accounts(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    with connect(db) as conn:
        now = "2026-01-01T00:00:00"

        def folder(parent, name, path, depth):
            return conn.execute(
                "INSERT INTO catalog_folders (parent_id, name, full_path, depth, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)", (parent, name, path, depth, now, now)).lastrowid

        root = folder(None, "root", ROOT, 0)
        used = folder(root, "00.FAVORITES", ROOT + r"\00.FAVORITES", 1)
        person = folder(used, "Alice", ROOT + r"\00.FAVORITES\Alice", 2)
        folder(root, "Empty", ROOT + r"\Empty", 1)
        conn.execute("INSERT INTO catalog_accounts (username, folder_id, status_id, created_at, updated_at)"
                     " VALUES ('alice', ?, 1, ?, ?)", (person, now, now))
        conn.commit()

        empty = AccountCatalogService(conn).list_empty_folder_paths()

    assert empty == [ROOT + r"\Empty"]


def test_plan_rows_and_blocking() -> None:
    plan = Plan("x", steps=[Step(OpType.MOVE_DIR, "a\b", "c\b")], conflicts=[Conflict("DEST_EXISTS", "ya existe")])

    assert plan_rows(plan) == [("Mover", "a\b", "c\b")]
    assert not plan.can_execute
    assert Plan("y", steps=[Step(OpType.MKDIR, None, "n")]).can_execute
    assert not Plan("z").can_execute  # nothing to do


def test_fsops_locale_keys_in_both_languages() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = {k for k in es if k.startswith(("plan.", "picker.", "fsops.", "ops.")) or k == "menu.catalog.ops"}
    assert len(keys) > 20 and keys <= set(en)
