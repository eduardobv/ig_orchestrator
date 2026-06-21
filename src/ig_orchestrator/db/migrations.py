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


__all__ = ["SCHEMA_PATH", "apply_migrations", "init_database"]
