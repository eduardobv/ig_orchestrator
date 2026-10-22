"""Centre windows on the monitor where the application is (any resolution, any monitor).

``install_auto_centering()`` makes **every** ``tk.Toplevel`` (and ``simpledialog`` dialogs) open with its
centre on the centre of the monitor that holds the main window, except tooltips and other
``overrideredirect`` pop-ups. The position is computed once, when the window is first shown (its size is known by then).
"""

from __future__ import annotations

import ctypes
import re
import sys
import tkinter as tk
from ctypes import wintypes

Rect = tuple[int, int, int, int]  # left, top, right, bottom
_GEOMETRY = re.compile(r"^(\d+)x(\d+)")
_installed = False


def centered_position(width: int, height: int, monitor: Rect) -> tuple[int, int]:
    """Top-left corner that puts a ``width`` x ``height`` window at the centre of ``monitor``."""

    left, top, right, bottom = monitor
    return left + (right - left - width) // 2, top + (bottom - top - height) // 2


def monitor_rect(widget: tk.Misc, around: tuple[int, int] | None = None) -> Rect:
    """Rectangle of the monitor containing ``around`` (default: the centre of the widget's top-level window)."""

    if around is None:
        top = widget.winfo_toplevel()
        around = (top.winfo_rootx() + top.winfo_width() // 2, top.winfo_rooty() + top.winfo_height() // 2)
    rect = _windows_monitor(around) if sys.platform == "win32" else None
    if rect is not None:
        return rect
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def _windows_monitor(point: tuple[int, int]) -> Rect | None:
    try:
        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = wintypes.HANDLE
        handle = user32.MonitorFromPoint(wintypes.POINT(int(point[0]), int(point[1])), 2)  # nearest monitor
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not handle or not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            return None
        r = info.rcMonitor
        return int(r.left), int(r.top), int(r.right), int(r.bottom)
    except (AttributeError, OSError):
        return None


def window_size(window: tk.Misc) -> tuple[int, int]:
    """Size the window has or has asked for (an unmapped window reports 1x1 until shown)."""

    match = _GEOMETRY.match(window.winfo_geometry() if window.winfo_ismapped() else window.geometry())
    width, height = (int(match.group(1)), int(match.group(2))) if match else (1, 1)
    if width <= 1 or height <= 1:
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    return width, height


def center_on_monitor(window: tk.Toplevel | tk.Tk, anchor: tk.Misc | None = None) -> None:
    """Move ``window`` so its centre is the centre of the monitor of ``anchor`` (default: its own master)."""

    window.update_idletasks()
    reference = anchor if anchor is not None else (window.master if window.master is not None else window)
    width, height = window_size(window)
    if window.winfo_ismapped():  # include the title bar and borders: the position is that of the outer frame
        border = max(window.winfo_rootx() - window.winfo_x(), 0)
        title = max(window.winfo_rooty() - window.winfo_y(), 0)
        width, height = width + 2 * border, height + title + border
    x, y = centered_position(width, height, monitor_rect(reference))
    window.geometry(f"+{x}+{y}")


def install_auto_centering() -> None:
    """Patch ``tk.Toplevel`` once so every new window is centred on the monitor of the main window.

    A window that has not been shown yet does not know its real size, so it is created transparent and
    centred the moment it is mapped (no flash at the corner); then it becomes opaque.
    """

    global _installed
    if _installed:
        return
    _installed = True
    original = tk.Toplevel.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            return
        state = {"done": False}

        def on_map(event) -> None:
            if event.widget is not self or state["done"]:
                return
            state["done"] = True

            def apply() -> None:
                try:
                    if not self.overrideredirect():
                        center_on_monitor(self)  # tooltips / notifications position themselves
                    if float(self.attributes("-alpha")) == 0.0:  # still our transparent value
                        self.attributes("-alpha", 1.0)
                except tk.TclError:
                    pass

            # the window manager places a window while it is being mapped: move it right after
            self.after(15, apply)

        self.bind("<Map>", on_map, add="+")

    tk.Toplevel.__init__ = init
