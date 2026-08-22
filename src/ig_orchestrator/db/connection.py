from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection configured for repository usage."""

    path = Path(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    return connection


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite file without writing (used to import the v1 catalog)."""

    uri = Path(db_path).resolve().as_posix()
    connection = sqlite3.connect(f"file:{uri}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


__all__ = ["connect", "connect_readonly"]
