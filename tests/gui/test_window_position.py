from __future__ import annotations

import time
import tkinter as tk

import pytest

from ig_orchestrator.gui.catalog.colors import load_catalog_colors
from ig_orchestrator.gui.shared.window_position import (
    center_on_monitor,
    centered_position,
    install_auto_centering,
    monitor_rect,
)
from ig_orchestrator.db import connect, init_gui_database


@pytest.mark.parametrize(
    ("size", "monitor", "expected"),
    [
        ((1000, 600), (0, 0, 1920, 1080), (460, 240)),
        ((800, 400), (0, 0, 1366, 768), (283, 184)),
        ((1000, 600), (1920, 0, 3840, 1080), (2380, 240)),  # second monitor on the right
        ((1000, 600), (-1920, 0, 0, 1080), (-1460, 240)),  # monitor on the left (negative coordinates)
        ((900, 500), (0, 0, 3840, 2160), (1470, 830)),
    ],
)
def test_centered_position(size, monitor, expected) -> None:
    assert centered_position(*size, monitor) == expected


def pump(root, rounds: int = 6) -> None:
    for _ in range(rounds):
        root.update()
        time.sleep(0.03)


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    window.geometry("300x200+50+50")
    window.update()
    yield window
    window.destroy()


def test_new_windows_open_centred_on_the_monitor(root) -> None:
    install_auto_centering()
    window = tk.Toplevel(root)
    window.geometry("640x360")  # size set after creation, like the real dialogs
    pump(root)
    assert float(window.attributes("-alpha")) == 1.0  # visible again after being centred

    left, top, right, bottom = monitor_rect(root)
    border = window.winfo_rootx() - window.winfo_x()
    title = window.winfo_rooty() - window.winfo_y()
    centre_x = window.winfo_x() + (window.winfo_width() + 2 * border) // 2  # centre of the outer frame
    centre_y = window.winfo_y() + (window.winfo_height() + title + border) // 2
    assert abs(centre_x - (left + right) // 2) <= 2
    assert abs(centre_y - (top + bottom) // 2) <= 2
    window.destroy()


def test_popups_without_border_are_not_moved(root) -> None:
    install_auto_centering()
    tip = tk.Toplevel(root)
    tip.wm_overrideredirect(True)
    tip.wm_geometry("+10+20")
    pump(root)
    assert (tip.winfo_x(), tip.winfo_y()) == (10, 20)
    tip.destroy()


def test_explicit_centering_helper(root) -> None:
    window = tk.Toplevel(root)
    window.geometry("500x300")
    pump(root)
    center_on_monitor(window)
    pump(root)
    left, top, right, bottom = monitor_rect(root)
    border = window.winfo_rootx() - window.winfo_x()
    outer_width = window.winfo_width() + 2 * border
    assert abs(window.winfo_x() - (left + (right - left - outer_width) // 2)) <= 2
    window.destroy()


def test_deleted_and_disabled_share_one_colour(tmp_path) -> None:
    db = tmp_path / "gui.sqlite"
    init_gui_database(db)
    conn = connect(db)
    colors = load_catalog_colors(conn)
    assert colors["deleted"] == colors["disabled"] == "#f4cccc"
    conn.execute("UPDATE catalog_account_statuses SET color_hex = '#d9d2e9' WHERE code = 'DELETED'")
    conn.commit()
    assert load_catalog_colors(conn)["deleted"] == "#f4cccc"  # an old purple value in the database is ignored
    conn.close()
