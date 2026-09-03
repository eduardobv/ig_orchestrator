from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk


def _resource_root() -> Path:
    """Return the application resource root, including PyInstaller builds."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


_ICON_DIR = _resource_root() / "static" / "icons"

_ICON_FILES = {
    "new": "new.png",
    "save": "save.png",
    "folder-open": "folder-open.png",
    "play": "play.png",
    "stop": "stop.png",
    "rename": "rename.png",
    "terminal": "terminal.png",
    "plus": "plus.png",
    "clipboard-plus": "clipboard-plus.png",
    "clipboard": "clipboard.png",
    "clipboard-black": "clipboard_black.png",
    "wand": "wand.png",
    "eraser": "eraser.png",
    "list": "list.png",
    "tree": "tree.png",
}


class IconSet:
    """Keep PhotoImage references so Tk does not garbage-collect toolbar icons."""

    def __init__(self, root: tk.Misc) -> None:
        self._images: dict[str, tk.PhotoImage] = {}

        for name, filename in _ICON_FILES.items():
            path = _ICON_DIR / filename

            if not path.exists():
                raise FileNotFoundError(
                    f"Icon asset not found: {path}"
                )

            self._images[name] = tk.PhotoImage(
                file=str(path),
                master=root,
            )

    def get(self, name: str) -> tk.PhotoImage:
        return self._images[name]

    def get_compact(self, name: str) -> tk.PhotoImage:
        """32px toolbar icon scaled to 24px, close to the compact ❌ buttons."""

        key = f"{name}:compact"
        cached = self._images.get(key)
        if cached is not None:
            return cached
        compact = self._images[name].zoom(3, 3).subsample(4, 4)
        self._images[key] = compact
        return compact


__all__ = ["IconSet"]
