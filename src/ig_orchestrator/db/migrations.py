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
    _add_column_if_missing(
        connection,
        table="input_batches",
        column="default_start_now_date",
        definition="TEXT",
    )
    for column, definition in (
        ("is_new_account", "INTEGER NOT NULL DEFAULT 0"),
        ("rename_owner_id", "TEXT"),
        ("rename_start_init_date", "TEXT"),
        ("rename_destination_path", "TEXT"),
    ):
        _add_column_if_missing(
            connection,
            table="accounts",
            column=column,
            definition=definition,
        )
    duplicates = connection.execute(
        """
        SELECT batch_name, COUNT(*) AS total
        FROM input_batches
        GROUP BY batch_name
        HAVING COUNT(*) > 1
        ORDER BY batch_name
        """
    ).fetchall()
    if duplicates:
        names = ", ".join(str(row["batch_name"]) for row in duplicates)
        raise RuntimeError(
            "Cannot enforce unique batch names because duplicates already exist: "
            f"{names}. Resolve those rows before running init-db again."
        )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_input_batches_batch_name
        ON input_batches(batch_name)
        """
    )
    connection.commit()


def _add_column_if_missing(
    connection: Connection,
    *,
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


__all__ = ["SCHEMA_PATH", "apply_migrations", "init_database"]
