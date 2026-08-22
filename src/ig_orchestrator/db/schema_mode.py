from __future__ import annotations

from sqlite3 import Connection

from ig_orchestrator.db.gui_migrations import GUI_SCHEMA_USER_VERSION


def schema_user_version(connection: Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def is_gui_schema(connection: Connection) -> bool:
    """Return True when the connection is a v2 GUI database."""

    return schema_user_version(connection) >= GUI_SCHEMA_USER_VERSION


__all__ = ["is_gui_schema", "schema_user_version"]
