"""feat-gui-26: new toolbar icons, single Run/Pause button, pull button, copy buttons."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest
from PIL import Image

from ig_orchestrator.gui.run.controller import RunControllerMixin
from ig_orchestrator.gui.shared.icons import _ICON_DIR, _ICON_FILES, IconSet


def test_every_registered_icon_exists_and_is_32px_rgba() -> None:
    for name, filename in _ICON_FILES.items():
        path = _ICON_DIR / filename
        assert path.exists(), name
        with Image.open(path) as image:
            assert image.size == (32, 32), name
            assert image.mode == "RGBA", name


def test_stories_icon_is_transparent_not_a_black_square() -> None:
    with Image.open(_ICON_DIR / "stories.png") as image:
        assert image.convert("RGBA").getpixel((0, 0))[3] == 0


def test_previous_icons_are_kept_in_old_folder() -> None:
    for name in ("play", "pause", "rename", "stories"):
        assert (_ICON_DIR / "_old" / f"{name}.png").exists()


def test_icon_set_loads_new_icons() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        icons = IconSet(root)
        for name in ("pull", "copy-black", "play-pause"):
            assert icons.get(name).width() == 32
        assert icons.get_compact("copy-black").width() == 24
    finally:
        root.destroy()


class _Runner:
    def __init__(self, running: bool) -> None:
        self._running = running

    def is_running(self) -> bool:
        return self._running


def _app(root: tk.Tk, *, running: bool, kind: str | None, paused: int | None):
    class App(RunControllerMixin):
        pass

    app = App()
    frame = ttk.Frame(root)
    frame.pack()
    app.execute_button = ttk.Button(frame)
    app.pause_button = ttk.Button(frame)
    app.execute_button.grid(row=0, column=0)
    app.pause_button.grid(row=0, column=0)
    app.process_runner = _Runner(running)
    app.active_process_kind = kind
    app.paused_batch_id = paused
    return app


def test_run_and_pause_share_one_cell() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        idle = _app(root, running=False, kind=None, paused=None)
        idle._sync_run_pause_buttons()
        assert idle.execute_button.winfo_manager() == "grid"
        assert idle.pause_button.winfo_manager() == ""

        running = _app(root, running=True, kind="batch", paused=None)
        running._sync_run_pause_buttons()
        assert running.execute_button.winfo_manager() == ""
        assert running.pause_button.winfo_manager() == "grid"

        paused = _app(root, running=False, kind=None, paused=7)
        paused._sync_run_pause_buttons()
        assert paused.execute_button.winfo_manager() == ""
        assert paused.pause_button.winfo_manager() == "grid"

        renaming = _app(root, running=True, kind="rename", paused=None)
        renaming._sync_run_pause_buttons()
        assert renaming.execute_button.winfo_manager() == "grid"
    finally:
        root.destroy()


def test_gen_icons_script_is_in_repo() -> None:
    assert (Path(__file__).resolve().parents[2] / "tools" / "gen_icons.py").exists()
