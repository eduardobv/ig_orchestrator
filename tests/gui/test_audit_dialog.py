from __future__ import annotations

import json
import queue
import sqlite3
from pathlib import Path

from ig_orchestrator.db import init_gui_database
from ig_orchestrator.gui.library.audit_dialog import run_audit_in_thread

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "locales"


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
