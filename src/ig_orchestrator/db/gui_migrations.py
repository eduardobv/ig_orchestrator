from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db.connection import connect


SCHEMA_V2_PATH = Path(__file__).with_name("schema_v2.sql")
GUI_SCHEMA_USER_VERSION = 100
_V1_SCHEMA_USER_VERSIONS = frozenset({1, 2, 3})


def init_gui_database(db_path: str | Path) -> None:
    """Create or migrate the GUI SQLite database without deleting existing data."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        apply_gui_migrations(connection)


def apply_gui_migrations(connection: Connection) -> None:
    """Apply the v2 GUI schema to an existing connection."""

    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version in _V1_SCHEMA_USER_VERSIONS:
        raise RuntimeError(
            "Refusing to initialize the GUI schema on a v1 orchestrator "
            f"database (user_version={current_version}). "
            "Set SQLITE_GUI_DB_PATH to a new file such as "
            r"data\orchestrator_gui.sqlite."
        )
    if current_version > GUI_SCHEMA_USER_VERSION:
        raise RuntimeError(
            "GUI database user_version "
            f"{current_version} is newer than supported "
            f"{GUI_SCHEMA_USER_VERSION}. Use a matching app version."
        )
    if current_version == GUI_SCHEMA_USER_VERSION:
        return
    schema = SCHEMA_V2_PATH.read_text(encoding="utf-8")
    connection.executescript(schema)
    stored_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if stored_version != GUI_SCHEMA_USER_VERSION:
        raise RuntimeError(
            "GUI schema did not set user_version to "
            f"{GUI_SCHEMA_USER_VERSION} (got {stored_version})"
        )
    connection.commit()


__all__ = [
    "GUI_SCHEMA_USER_VERSION",
    "SCHEMA_V2_PATH",
    "apply_gui_migrations",
    "init_gui_database",
]
