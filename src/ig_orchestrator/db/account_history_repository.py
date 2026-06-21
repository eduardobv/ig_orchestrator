from __future__ import annotations

from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import dump_datetime, load_datetime
from ig_orchestrator.models.account_history import AccountHistory, AccountHistoryStatus


class AccountHistoryRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create_or_get(self, user_name: str) -> AccountHistory:
        normalized = user_name.strip()
        existing = self.get_by_user_name(normalized)
        if existing is not None:
            return existing

        record = AccountHistory(user_name=normalized)
        cursor = self.connection.execute(
            """
            INSERT INTO account_history (
                user_ig_id, user_name, status, field1, field2, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.user_ig_id,
                record.user_name,
                record.status.value,
                record.field1,
                record.field2,
                dump_datetime(record.created_at),
                dump_datetime(record.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Account history row was not stored")
        return stored

    def get_by_id(self, history_id: int) -> AccountHistory | None:
        row = self.connection.execute(
            "SELECT * FROM account_history WHERE id = ?",
            (history_id,),
        ).fetchone()
        return _row_to_history(row)

    def get_by_user_name(self, user_name: str) -> AccountHistory | None:
        row = self.connection.execute(
            """
            SELECT * FROM account_history
            WHERE user_name = ? COLLATE NOCASE
            ORDER BY id
            LIMIT 1
            """,
            (user_name.strip(),),
        ).fetchone()
        return _row_to_history(row)

    def list_all(self) -> list[AccountHistory]:
        rows = self.connection.execute(
            "SELECT * FROM account_history ORDER BY id"
        ).fetchall()
        return [_row_to_history(row) for row in rows]


def _row_to_history(row: Row | None) -> AccountHistory | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored account_history row is missing timestamps")
    return AccountHistory(
        id=row["id"],
        user_ig_id=row["user_ig_id"],
        user_name=row["user_name"],
        status=AccountHistoryStatus(row["status"]),
        field1=row["field1"],
        field2=row["field2"],
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["AccountHistoryRepository"]
