from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import connect
from ig_orchestrator.db.gui_migrations import init_gui_database
from ig_orchestrator.gui.i18n import load_language
from tests.orchestration.test_run_settings import _env  # type: ignore


def _make_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    return tk, root


def test_run_tab_shows_defaults_validates_and_saves(tmp_path: Path) -> None:
    from ig_orchestrator.gui.settings.run_tab import RunSettingsTab

    tk, root = _make_root()
    try:
        load_language("es")
        path = tmp_path / "orchestrator_gui.sqlite"
        init_gui_database(path)
        connection = connect(path)
        tab = RunSettingsTab(root, connection, _env(tmp_path))

        values = tab.collect()
        assert values["run.retry.max_retries"] == "5"
        assert values["processing.stories_first"] == "1"
        assert tab.validate() is None

        tab.variables["run.bot.parallel_downloads"].set("0")
        spec, _reason = tab.validate()
        assert spec.key == "run.bot.parallel_downloads"

        tab.variables["run.bot.parallel_downloads"].set("3")
        assert tab.save() is True
        stored = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'run.bot.parallel_downloads'"
        ).fetchone()
        assert stored[0] == "3"
    finally:
        root.destroy()


def test_every_run_field_has_locale_texts() -> None:
    from ig_orchestrator.gui.i18n import locale_keys
    from ig_orchestrator.orchestration.run_settings import GROUPS, RUN_SETTING_SPECS

    keys = locale_keys("es")
    for spec in RUN_SETTING_SPECS:
        assert f"run.{spec.field}" in keys and f"run.{spec.field}.help" in keys
    for group in GROUPS:
        assert f"run.group.{group}" in keys


def test_bot_stall_marker_updates_the_status_bar() -> None:
    from types import SimpleNamespace

    from ig_orchestrator.gui.run.controller import RunControllerMixin
    from ig_orchestrator.gui.theme import STATUS_TONE_BUSY, STATUS_TONE_IDLE

    calls: list[tuple[str, str]] = []
    app = SimpleNamespace(
        _set_status_tone=lambda tone: calls.append(("tone", tone)),
        _set_status=lambda text: calls.append(("status", text)),
        _write_console=lambda text: calls.append(("console", text)),
    )

    RunControllerMixin._handle_process_output(app, "[GUI_BOT_STATUS] STALLED\n")
    RunControllerMixin._handle_process_output(app, "[GUI_BOT_STATUS] RESUMED\n")

    assert calls[0] == ("tone", STATUS_TONE_BUSY)
    assert calls[1][0] == "status" and "esper" in calls[1][1].lower()
    assert ("tone", STATUS_TONE_IDLE) in calls
    assert calls[-2][0] == "status" and "esper" not in calls[-2][1].lower()
