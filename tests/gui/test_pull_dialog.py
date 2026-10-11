from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ig_orchestrator.exchange import scan_exchange
from ig_orchestrator.gui.exchange.pull_dialog import (
    STATE_BUSY,
    STATE_EMPTY,
    STATE_EXISTS,
    STATE_READY,
    folder_state,
    format_mb,
)

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


def test_folder_state_covers_every_row_state(tmp_path: Path) -> None:
    exchange, work = tmp_path / "ex", tmp_path / "work"
    (exchange / "busy").mkdir(parents=True)
    (exchange / "busy" / "a.jpg").write_bytes(b"x")  # just written -> in use
    (exchange / "ready").mkdir()
    (exchange / "ready" / "a.jpg").write_bytes(b"x")
    (exchange / "dup").mkdir()
    (exchange / "dup" / "a.jpg").write_bytes(b"x")
    (exchange / "empty").mkdir()
    work.mkdir()
    (work / "DUP").mkdir()
    old = time.time() - 3600
    for name in ("ready", "dup"):
        import os

        os.utime(exchange / name / "a.jpg", (old, old))

    states = {f.name: folder_state(f, work) for f in scan_exchange(exchange, stable_seconds=30)}

    assert states == {
        "busy": STATE_BUSY,
        "ready": STATE_READY,
        "dup": STATE_EXISTS,
        "empty": STATE_EMPTY,
    }


def test_format_mb() -> None:
    assert format_mb(1024 * 1024) == "1.0"


def test_pull_and_instance_locale_keys_complete() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    wanted = {k for k in es if k.startswith(("pull.", "settings.instances.")) or k in {
        "menu.batch.pull", "settings.tabs.instances"}}
    assert len(wanted) > 30
    assert wanted <= set(en)
    for state in ("ready", "busy", "exists", "empty"):
        assert f"pull.state.{state}" in es


def test_settings_tab_and_pull_dialog_construct(tmp_path: Path) -> None:
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk

    from ig_orchestrator.db import connect, init_gui_database
    from ig_orchestrator.gui.settings.instances_tab import InstancesTab

    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    try:
        with connect(db) as connection:
            tab = InstancesTab(ttk.Frame(root), connection)
            tab._repo.save(__import__("ig_orchestrator.db", fromlist=["Instance"]).Instance(
                None, "inst1", "WORKER", exchange_path=r"\HOST\share\tmp"))
            tab.refresh()
            assert len(tab.tree.get_children()) == 1
    finally:
        root.destroy()
