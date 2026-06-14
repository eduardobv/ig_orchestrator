from __future__ import annotations

from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import (
    dump_date,
    dump_datetime,
    dump_path,
    load_date,
    load_datetime,
    load_path,
)
from ig_orchestrator.models import Account, AccountStatus


class AccountRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, account: Account) -> Account:
        cursor = self.connection.execute(
            """
            INSERT INTO accounts (
                batch_id, username, start_now_date, download_stories,
                generated_story_url, working_folder, final_destination_folder,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account.batch_id,
                account.username,
                dump_date(account.start_now_date),
                int(account.download_stories),
                account.generated_story_url,
                dump_path(account.working_folder),
                dump_path(account.final_destination_folder),
                account.status.value,
                dump_datetime(account.created_at),
                dump_datetime(account.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Account was not stored")
        return stored

    def get_by_id(self, account_id: int) -> Account | None:
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return _row_to_account(row)

    def get_by_username(self, username: str) -> Account | None:
        row = self.connection.execute(
            """
            SELECT * FROM accounts
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        return _row_to_account(row)

    def list_by_batch(self, batch_id: int) -> list[Account]:
        rows = self.connection.execute(
            "SELECT * FROM accounts WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()
        return [_row_to_account(row) for row in rows]

    def list_by_status(self, status: AccountStatus) -> list[Account]:
        rows = self.connection.execute(
            "SELECT * FROM accounts WHERE status = ? ORDER BY id",
            (status.value,),
        ).fetchall()
        return [_row_to_account(row) for row in rows]

    def update_status(self, account_id: int, status: AccountStatus) -> Account:
        self.connection.execute(
            """
            UPDATE accounts
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status.value, account_id),
        )
        self.connection.commit()
        stored = self.get_by_id(account_id)
        if stored is None:
            raise ValueError(f"Account not found: {account_id}")
        return stored


def _row_to_account(row: Row | None) -> Account | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored account row is missing timestamps")
    return Account(
        id=row["id"],
        batch_id=row["batch_id"],
        username=row["username"],
        start_now_date=load_date(row["start_now_date"]),
        download_stories=bool(row["download_stories"]),
        generated_story_url=row["generated_story_url"],
        working_folder=load_path(row["working_folder"]),
        final_destination_folder=load_path(row["final_destination_folder"]),
        status=AccountStatus(row["status"]),
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["AccountRepository"]
