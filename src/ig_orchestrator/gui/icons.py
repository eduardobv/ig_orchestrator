from __future__ import annotations

import tkinter as tk

_BG = (247, 248, 250)
_INK = (31, 41, 51)
_ACCENT = (37, 99, 235)
_DANGER = (185, 28, 28)
_OK = (21, 128, 61)


def _px(color: tuple[int, int, int], canvas: list[list[tuple[int, int, int]]], x: int, y: int) -> None:
    if 0 <= x < 16 and 0 <= y < 16:
        canvas[y][x] = color


def _line(
    canvas: list[list[tuple[int, int, int]]],
    color: tuple[int, int, int],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> None:
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        _px(color, canvas, x0, y0)
        if x0 == x1 and y0 == y1:
            break
        extra = 2 * err
        if extra > -dy:
            err -= dy
            x0 += sx
        if extra < dx:
            err += dx
            y0 += sy


def _fill_rect(
    canvas: list[list[tuple[int, int, int]]],
    color: tuple[int, int, int],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            _px(color, canvas, x, y)


def _blank() -> list[list[tuple[int, int, int]]]:
    return [[_BG for _ in range(16)] for _ in range(16)]


def _to_photo(canvas: list[list[tuple[int, int, int]]], root: tk.Misc) -> tk.PhotoImage:
    rows = []
    for y in range(16):
        for _scale_y in range(2):
            parts = []
            for x in range(16):
                r, g, b = canvas[y][x]
                parts.append(f"#{r:02x}{g:02x}{b:02x}")
                parts.append(f"#{r:02x}{g:02x}{b:02x}")
            rows.append("{" + " ".join(parts) + "}")
    image = tk.PhotoImage(width=32, height=32, master=root)
    image.put(" ".join(rows))
    return image


def _icon_new() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _INK, 3, 2, 12, 13)
    _fill_rect(c, _BG, 4, 3, 11, 12)
    _line(c, _ACCENT, 8, 5, 8, 10)
    _line(c, _ACCENT, 5, 8, 11, 8)
    return c


def _icon_save() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _ACCENT, 3, 3, 12, 13)
    _fill_rect(c, _BG, 5, 3, 10, 7)
    _fill_rect(c, _INK, 6, 9, 9, 12)
    return c


def _icon_folder() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _ACCENT, 2, 5, 13, 13)
    _fill_rect(c, _ACCENT, 2, 3, 7, 5)
    return c


def _icon_play() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    for y in range(4, 12):
        span = y - 4 if y < 8 else 11 - y
        for x in range(6, 7 + span):
            _px(_OK, c, x, y)
    return c


def _icon_stop() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _DANGER, 4, 4, 11, 11)
    return c


def _icon_rename() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _line(c, _INK, 3, 12, 12, 3)
    _line(c, _ACCENT, 11, 2, 13, 4)
    _fill_rect(c, _INK, 3, 12, 6, 13)
    return c


def _icon_terminal() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _INK, 2, 3, 13, 12)
    _line(c, _BG, 4, 6, 6, 8)
    _line(c, _BG, 6, 8, 4, 10)
    _line(c, _BG, 8, 10, 11, 10)
    return c


def _icon_plus() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _line(c, _ACCENT, 8, 3, 8, 12)
    _line(c, _ACCENT, 3, 8, 12, 8)
    _line(c, _ACCENT, 7, 3, 7, 12)
    _line(c, _ACCENT, 9, 3, 9, 12)
    return c


def _icon_clipboard_plus() -> list[list[tuple[int, int, int]]]:
    c = _icon_save()
    _line(c, _OK, 8, 8, 8, 13)
    _line(c, _OK, 6, 11, 10, 11)
    return c


def _icon_clipboard() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _INK, 4, 3, 11, 13)
    _fill_rect(c, _BG, 5, 5, 10, 12)
    _fill_rect(c, _ACCENT, 6, 2, 9, 4)
    return c


def _icon_wand() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _line(c, _ACCENT, 4, 12, 11, 5)
    _px(_INK, c, 12, 3)
    _px(_INK, c, 14, 5)
    _px(_INK, c, 12, 6)
    return c


def _icon_eraser() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _fill_rect(c, _DANGER, 3, 8, 8, 12)
    _fill_rect(c, _INK, 8, 4, 12, 8)
    return c


def _icon_list() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    for y in (4, 7, 10):
        _px(_ACCENT, c, 3, y)
        _line(c, _INK, 5, y, 12, y)
    return c


def _icon_tree() -> list[list[tuple[int, int, int]]]:
    c = _blank()
    _line(c, _INK, 4, 3, 4, 12)
    _line(c, _INK, 4, 6, 8, 6)
    _line(c, _INK, 4, 10, 8, 10)
    _px(_ACCENT, c, 10, 6)
    _px(_ACCENT, c, 10, 10)
    return c


_BUILDERS = {
    "new": _icon_new,
    "save": _icon_save,
    "folder-open": _icon_folder,
    "play": _icon_play,
    "stop": _icon_stop,
    "rename": _icon_rename,
    "terminal": _icon_terminal,
    "plus": _icon_plus,
    "clipboard-plus": _icon_clipboard_plus,
    "clipboard": _icon_clipboard,
    "wand": _icon_wand,
    "eraser": _icon_eraser,
    "list": _icon_list,
    "tree": _icon_tree,
}


class IconSet:
    """Keep PhotoImage refs so Tk does not garbage-collect toolbar icons."""

    def __init__(self, root: tk.Misc) -> None:
        self._images = {name: _to_photo(builder(), root) for name, builder in _BUILDERS.items()}

    def get(self, name: str) -> tk.PhotoImage:
        return self._images[name]


__all__ = ["IconSet"]
