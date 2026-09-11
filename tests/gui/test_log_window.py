from __future__ import annotations

import pytest

from ig_orchestrator.gui.i18n import load_language
from ig_orchestrator.gui.log_window import LogWindow


def _make_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    return tk, root


def test_append_after_close_does_not_raise() -> None:
    tk, root = _make_root()
    load_language("es")
    try:
        log = LogWindow(root)
        log.toggle()
        root.update_idletasks()
        log.append("run started\n")
        log._hide()
        root.update_idletasks()
        log.append("starting rename\n")
        assert "starting rename\n" in "".join(log._buffer)
        log.toggle()
        root.update_idletasks()
        assert log._window is not None
        assert log._window.winfo_viewable()
        assert "starting rename\n" in log._text.get("1.0", tk.END)
    finally:
        root.destroy()


def test_append_after_destroy_does_not_raise() -> None:
    tk, root = _make_root()
    load_language("es")
    try:
        log = LogWindow(root)
        log.toggle()
        root.update_idletasks()
        log._window.destroy()
        root.update_idletasks()
        log.append("after destroy\n")
        assert "after destroy\n" in "".join(log._buffer)
        assert log._window is None
        log.toggle()
        root.update_idletasks()
        assert log._window is not None
        assert log._window.winfo_exists()
        assert "after destroy\n" in log._text.get("1.0", tk.END)
    finally:
        root.destroy()
