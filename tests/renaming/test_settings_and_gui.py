from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ig_orchestrator.db import Instance, InstanceRepository, connect, init_gui_database
from ig_orchestrator.gui.run.integrated_rename import describe_result
from ig_orchestrator.gui.run.rename_preview_dialog import source_choices
from ig_orchestrator.library.compat_lite import lite_path_from_settings
from ig_orchestrator.renaming.service import AccountResult, RenameResult
from ig_orchestrator.renaming.settings import (
    INTEGRATED,
    LEGACY,
    lite_mirror_enabled,
    preview_required,
    read_engine,
    write_setting,
)

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


def test_defaults_and_overrides(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    assert read_engine(conn) == INTEGRATED and preview_required(conn) and lite_mirror_enabled(conn)

    write_setting(conn, "renaming.engine", LEGACY)
    write_setting(conn, "renaming.preview", "0", "BOOLEAN")
    write_setting(conn, "compat.lite.enabled", "0", "BOOLEAN")
    write_setting(conn, "stories.accounts_db_path", str(tmp_path / "lite.sqlite"), "PATH")

    assert read_engine(conn) == LEGACY and not preview_required(conn) and not lite_mirror_enabled(conn)
    assert lite_path_from_settings(conn) is None  # the checkbox really switches the mirror off
    write_setting(conn, "compat.lite.enabled", "1", "BOOLEAN")
    assert lite_path_from_settings(conn) == tmp_path / "lite.sqlite"
    write_setting(conn, "renaming.engine", "nonsense")
    assert read_engine(conn) == INTEGRATED
    conn.close()


def test_a_v1_database_falls_back_to_the_external_engine() -> None:
    v1 = sqlite3.connect(":memory:")
    assert read_engine(v1) == LEGACY and preview_required(v1) and lite_mirror_enabled(v1)


def test_source_choices_list_own_folder_and_registered_instances(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    InstanceRepository(conn).save(
        Instance(None, "inst1", "WORKER", working_path=r"\\laptop\dw", exchange_path=r"\\laptop\share\tmp")
    )

    choices = source_choices(conn, r"C:\Users\x\work")

    assert choices[0][1] == r"C:\Users\x\work" and [c[1] for c in choices[1:]] == [r"\\laptop\dw", r"\\laptop\share\tmp"]
    assert any("inst1" in label for label, _p in choices[1:])
    conn.close()


def test_result_text_lists_every_account_and_problem() -> None:
    result = RenameResult(accounts=[
        AccountResult("alice", "RENAMED", renamed=2, duplicated=1, deleted_duplicates=1, moved=True),
        AccountResult("stranger", "SKIPPED", detail="No esta registrada"),
    ])

    text = describe_result(result)

    assert "@alice: RENAMED" in text and "@stranger: SKIPPED" in text and "No esta registrada" in text
    assert not result.ok and [a.username for a in result.problems] == ["stranger"]
    assert result.summary().startswith("2 cuentas")


def test_renamer_locale_keys_in_both_languages() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = {k for k in es if k.startswith(("rename.dialog", "rename.src", "rename.col", "rename.status", "rename.kind",
                                           "rename.result", "settings.rename", "settings.lite_mirror"))}
    keys |= {"rename.more", "rename.move.conflict", "rename.running", "rename.start_console"}
    assert len(keys) >= 30 and keys <= set(en)
