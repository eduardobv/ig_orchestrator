from __future__ import annotations

from pathlib import Path
import tkinter as tk

import pytest

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.filesystem.story_inbox import StoryInboxReport, StoryInboxResult, StoryInboxStatus
from ig_orchestrator.gui.stories.dialog import StoriesInboxMixin


class _Host(StoriesInboxMixin):
    def __init__(self, root, connection) -> None:
        self.root = root
        self.connection = connection
        self.status = ""

    def _set_status(self, text: str) -> None:
        self.status = text

    def _write_console(self, text: str) -> None:
        pass


def test_modal_shows_only_problems_and_force_button(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    try:
        init_gui_database(tmp_path / "g.sqlite")
        with connect(tmp_path / "g.sqlite") as connection:
            host = _Host(root, connection)
            host._open_stories_inbox()
            w = host._stories_widgets
            dup = StoryInboxResult(
                Path("a-1.jpg"), "a", Path("x/a-1.jpg"), StoryInboxStatus.DESTINATION_EXISTS, "exists"
            )
            host._show_stories_report(StoryInboxReport(5, (dup,), (Path("a-1.jpg"),)))
            assert len(w["tree"].get_children()) == 1
            assert str(w["force_button"].cget("state")) == "normal"
            assert "5" in host.status
            host._show_stories_report(StoryInboxReport(6, (), ()))
            assert not w["tree"].get_children()
            assert str(w["force_button"].cget("state")) == "disabled"
            host._stories_inbox_window.destroy()
    finally:
        root.destroy()
