from __future__ import annotations

from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import dump_datetime, load_datetime
from ig_orchestrator.models import AppConfig, ConfigValueType


class ConfigRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert(self, config: AppConfig) -> AppConfig:
        self.connection.execute(
            """
            INSERT INTO app_config (key, value, value_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (
                config.key,
                config.value,
                config.value_type.value,
                dump_datetime(config.created_at),
                dump_datetime(config.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get(config.key)
        if stored is None:
            raise RuntimeError(f"Config key was not stored: {config.key}")
        return stored

    def get(self, key: str) -> AppConfig | None:
        row = self.connection.execute(
            "SELECT * FROM app_config WHERE key = ?",
            (key,),
        ).fetchone()
        return _row_to_config(row)

    def list_all(self) -> list[AppConfig]:
        rows = self.connection.execute(
            "SELECT * FROM app_config ORDER BY key"
        ).fetchall()
        return [_row_to_config(row) for row in rows]


def _row_to_config(row: Row | None) -> AppConfig | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored app_config row is missing timestamps")
    return AppConfig(
        key=row["key"],
        value=row["value"],
        value_type=ConfigValueType(row["value_type"]),
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["ConfigRepository"]
