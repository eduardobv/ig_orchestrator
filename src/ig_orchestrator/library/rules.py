"""Library scanning rules (ported from ``sc1`` and now configurable via ``app_settings``)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# Content/category folders that are never usernames (same list as sc1).
DEFAULT_NON_ACCOUNT_NAMES = (
    ".thumb.stogram", "highlights", "mobile", "reels", "story", "tagged", "telegram", "otros", "captura",
)
DEFAULT_MEDIA_SUBFOLDERS = ("reels", "story", "highlights")
DEFAULT_MEDIA_EXTENSIONS = ("mp4", "mov", "wmv", "jpe", "jpeg", "jpg", "png")
DEFAULT_MAX_DEPTH = 3


def _csv(text: str, *, strip_dot: bool = False) -> frozenset[str]:
    items = (item.strip().casefold() for item in text.split(","))
    return frozenset(item.lstrip(".") if strip_dot else item for item in items if item)


@dataclass(frozen=True, slots=True)
class LibraryRules:
    max_depth: int = DEFAULT_MAX_DEPTH
    media_subfolders: frozenset[str] = frozenset(DEFAULT_MEDIA_SUBFOLDERS)
    media_extensions: frozenset[str] = frozenset(DEFAULT_MEDIA_EXTENSIONS)
    non_account_names: frozenset[str] = frozenset(DEFAULT_NON_ACCOUNT_NAMES)

    def is_multimedia(self, filename: str) -> bool:
        if "." not in filename:
            return False
        extension = filename.rsplit(".", 1)[1].lower()
        return bool(extension) and extension in self.media_extensions

    @staticmethod
    def load(conn: sqlite3.Connection | None) -> "LibraryRules":
        """Rules from ``app_settings`` (``library.*`` keys), defaults for anything missing."""

        if conn is None:
            return LibraryRules()

        def value(key: str, default: str) -> str:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            return str(row[0]).strip() if row is not None and str(row[0]).strip() else default

        try:
            depth = int(value("library.max_depth", str(DEFAULT_MAX_DEPTH)))
        except ValueError:
            depth = DEFAULT_MAX_DEPTH
        return LibraryRules(
            max_depth=max(1, depth),
            media_subfolders=_csv(value("library.media_subfolders", ",".join(DEFAULT_MEDIA_SUBFOLDERS))),
            media_extensions=_csv(value("library.media_extensions", ",".join(DEFAULT_MEDIA_EXTENSIONS)), strip_dot=True),
            non_account_names=_csv(value("library.non_account_names", ",".join(DEFAULT_NON_ACCOUNT_NAMES))),
        )
