from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db.connection import connect


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def init_database(db_path: str | Path) -> None:
    """Create or migrate the SQLite database without deleting existing data."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        apply_migrations(connection)


def apply_migrations(connection: Connection) -> None:
    """Apply safe schema migrations to an existing connection."""

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema)
    connection.commit()


__all__ = ["SCHEMA_PATH", "apply_migrations", "init_database"]
