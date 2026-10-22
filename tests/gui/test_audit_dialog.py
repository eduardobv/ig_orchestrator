from __future__ import annotations

import json
import queue
import sqlite3
from pathlib import Path

from ig_orchestrator.db import init_gui_database
from ig_orchestrator.gui.library.audit_dialog import run_audit_in_thread

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


def test_audit_locale_keys_in_both_languages() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    audit_keys = {k for k in es if k.startswith("audit.") or k == "menu.catalog.audit"}
    assert audit_keys
    assert audit_keys <= set(en)


def test_run_audit_in_thread_reports_result(tmp_path: Path) -> None:
    gui_db = tmp_path / "gui.sqlite"
    init_gui_database(gui_db)
    lite = tmp_path / "accounts_lite.sqlite"
    with sqlite3.connect(lite) as conn:
        conn.execute(
            "CREATE TABLE accounts_dir (id INTEGER PRIMARY KEY, username TEXT, ownerId TEXT,"
            " path TEXT, last_modified TEXT, created_at TEXT, modified_at TEXT)"
        )
    results: queue.Queue = queue.Queue()

    run_audit_in_thread(gui_db, lite, None, results).join(timeout=10)

    kind, payload = results.get_nowait()
    assert kind == "done"
    assert payload.findings == []


def test_run_audit_in_thread_reports_error(tmp_path: Path) -> None:
    results: queue.Queue = queue.Queue()

    run_audit_in_thread(tmp_path / "missing.sqlite", tmp_path / "x.sqlite", None, results).join(timeout=10)

    assert results.get_nowait()[0] == "error"


def test_native_path_text_uses_windows_separators() -> None:
    import os

    from ig_orchestrator.library.audit_cli import native_path_text

    assert native_path_text("G:/4K Stogram/accounts_lite.sqlite") == os.path.normpath(
        "G:/4K Stogram/accounts_lite.sqlite"
    )
    assert native_path_text("  ") == ""
    if os.name == "nt":
        assert native_path_text("G:/4K Stogram/x.sqlite") == r"G:\4K Stogram\x.sqlite"


def test_audit_keys_resolve_through_t() -> None:
    from ig_orchestrator.gui.i18n import load_language, t

    for language in ("es", "en"):
        load_language(language)
        for key in ("menu.catalog.audit", "audit.title", "audit.run", "audit.col.paths"):
            assert t(key) != key
    load_language("es")
