from __future__ import annotations

import json
from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.gui.library.scan_actions import deep_estimate_seconds
from ig_orchestrator.gui.library.scan_findings_dialog import KINDS
from ig_orchestrator.library.scanner import last_scan_age_days

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


def test_deep_estimate_uses_the_last_complete_run(tmp_path: Path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    assert deep_estimate_seconds(conn) is None and last_scan_age_days(conn) is None
    conn.execute("INSERT INTO scan_runs (scope, started_at, finished_at, seconds) VALUES ('ALL', 'x', 'y', 3)")
    conn.execute("INSERT INTO scan_runs (scope, started_at, finished_at, seconds) VALUES ('DEEP', 'x', 'y', 480.5)")
    conn.commit()

    assert deep_estimate_seconds(conn) == 480.5
    conn.close()


def test_scan_locale_keys_in_both_languages_and_every_kind_has_a_label() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = {k for k in es if k.startswith("scan.")}
    assert len(keys) >= 30 and keys <= set(en)
    for kind in KINDS:
        assert f"scan.kind.{kind}" in es and f"scan.kind.{kind}" in en
