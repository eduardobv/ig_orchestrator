from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db.connection import connect


SCHEMA_V2_PATH = Path(__file__).with_name("schema_v2.sql")
COMPAT_VIEWS_PATH = Path(__file__).with_name("compat_views_v2.sql")
GUI_SCHEMA_USER_VERSION = 100
_V1_SCHEMA_USER_VERSIONS = frozenset({1, 2, 3})


def prepare_sqlite(db_path: str | Path) -> None:
    """Initialize v1 or GUI schema based on user_version and filename."""

    from ig_orchestrator.db.migrations import init_database

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    probe = sqlite3.connect(path)
    try:
        version = int(probe.execute("PRAGMA user_version").fetchone()[0])
    finally:
        probe.close()
    if version >= GUI_SCHEMA_USER_VERSION or (
        version == 0 and "orchestrator_gui" in path.name
    ):
        init_gui_database(path)
        return
    init_database(path)


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
    if current_version == 0:
        schema = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
        stored_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if stored_version != GUI_SCHEMA_USER_VERSION:
            raise RuntimeError(
                "GUI schema did not set user_version to "
                f"{GUI_SCHEMA_USER_VERSION} (got {stored_version})"
            )
    elif current_version == GUI_SCHEMA_USER_VERSION:
        pass
    else:
        raise RuntimeError(
            "GUI database user_version "
            f"{current_version} cannot be migrated automatically."
        )
    _patch_gui_schema(connection)
    connection.executescript(COMPAT_VIEWS_PATH.read_text(encoding="utf-8"))
    connection.commit()


def _patch_gui_schema(connection: Connection) -> None:
    """Idempotent lookup/column patches for databases already at v100."""

    connection.execute(
        """
        INSERT OR IGNORE INTO batch_url_statuses
            (id, code, name, description, sort_order, is_active)
        VALUES
            (8, 'CLASSIFIED', 'Classified',
             'Files were classified after download.', 8, 1)
        """
    )
    _add_column_if_missing(
        connection, "downloaded_files", "working_relative_path", "TEXT"
    )
    _add_column_if_missing(connection, "downloaded_files", "sha256", "TEXT")
    _add_column_if_missing(connection, "downloaded_files", "updated_at", "TEXT")


def _add_column_if_missing(
    connection: Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


__all__ = [
    "GUI_SCHEMA_USER_VERSION",
    "SCHEMA_V2_PATH",
    "apply_gui_migrations",
    "init_gui_database",
    "prepare_sqlite",
]
