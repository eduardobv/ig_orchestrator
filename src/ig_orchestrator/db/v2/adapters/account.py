from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import dump_datetime, dump_path, load_datetime, load_path
from ig_orchestrator.db.account_repository import AccountRepository
from ig_orchestrator.db.batch_repository import BatchRepository
from ig_orchestrator.db.download_repository import DownloadRepository
from ig_orchestrator.db.lookups import LookupCache
from ig_orchestrator.db.run_repository import RunRecord, RunRepository
from ig_orchestrator.db.url_job_repository import UrlJobRepository
from ig_orchestrator.db.v2.adapters.mapping import (
    _join_root,
    _now,
    _path_root,
    _row_to_batch,
    _row_to_download,
    _row_to_run,
    _row_to_url_job,
    _split_path,
    _download_status_code,
)
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    DownloadFile,
    DownloadFileStatus,
    InputBatch,
    InputBatchStatus,
    MediaType,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)

_ACCOUNT_SELECT = """
SELECT
    ba.id,
    ba.batch_id,
    ca.username,
    b.start_date,
    ba.download_stories,
    ba.working_folder_rel,
    bas.code AS status,
    ba.created_at,
    ba.updated_at
FROM batch_accounts ba
JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
JOIN batches b ON b.id = ba.batch_id
JOIN batch_account_statuses bas ON bas.id = ba.status_id
"""


class GuiAccountRepository(AccountRepository):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create(self, account: Account) -> Account:
        from ig_orchestrator.db.account_history_repository import (
            AccountHistoryRepository,
        )

        if account.batch_id is None:
            raise ValueError("Account.batch_id is required")
        catalog = AccountHistoryRepository(self.connection).create_or_get(
            account.username
        )
        if catalog.id is None:
            raise RuntimeError("Catalog account has no id")
        pending_id = self._lookups.id_for("batch_account_statuses", account.status.value)
        sort_order = self.connection.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0) + 1
            FROM batch_accounts
            WHERE batch_id = ?
            """,
            (account.batch_id,),
        ).fetchone()[0]
        working_rel = account.username
        cursor = self.connection.execute(
            """
            INSERT INTO batch_accounts (
                batch_id, catalog_account_id, download_stories,
                working_folder_rel, status_id, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account.batch_id,
                catalog.id,
                int(account.download_stories),
                working_rel,
                pending_id,
                int(sort_order),
                dump_datetime(account.created_at),
                dump_datetime(account.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Batch account was not stored")
        return stored

    def get_by_id(self, account_id: int) -> Account | None:
        row = self.connection.execute(
            _ACCOUNT_SELECT + " WHERE ba.id = ?",
            (account_id,),
        ).fetchone()
        return self._row_to_account(row)

    def get_by_username(self, username: str) -> Account | None:
        row = self.connection.execute(
            _ACCOUNT_SELECT
            + " WHERE ca.username = ? COLLATE NOCASE ORDER BY ba.id DESC LIMIT 1",
            (username,),
        ).fetchone()
        return self._row_to_account(row)

    def list_by_batch(self, batch_id: int) -> list[Account]:
        rows = self.connection.execute(
            _ACCOUNT_SELECT + " WHERE ba.batch_id = ? ORDER BY ba.sort_order, ba.id",
            (batch_id,),
        ).fetchall()
        return [account for row in rows if (account := self._row_to_account(row))]

    def list_by_status(self, status: AccountStatus) -> list[Account]:
        status_id = self._lookups.id_for("batch_account_statuses", status.value)
        rows = self.connection.execute(
            _ACCOUNT_SELECT + " WHERE ba.status_id = ? ORDER BY ba.id",
            (status_id,),
        ).fetchall()
        return [account for row in rows if (account := self._row_to_account(row))]

    def update_status(self, account_id: int, status: AccountStatus) -> Account:
        status_id = self._lookups.id_for("batch_account_statuses", status.value)
        self.connection.execute(
            """
            UPDATE batch_accounts
            SET status_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_id, account_id),
        )
        self.connection.commit()
        stored = self.get_by_id(account_id)
        if stored is None:
            raise ValueError(f"Account not found: {account_id}")
        return stored

    def _row_to_account(self, row: Row | None) -> Account | None:
        if row is None:
            return None
        created_at = load_datetime(row["created_at"])
        updated_at = load_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("Stored batch account is missing timestamps")
        username = str(row["username"])
        download_stories = bool(row["download_stories"])
        working_rel = row["working_folder_rel"]
        working_root = _path_root(self.connection, "WORKING")
        working_folder = None
        if working_rel:
            working_folder = (
                Path(working_root) / str(working_rel)
                if working_root
                else Path(str(working_rel))
            )
        return Account(
            id=row["id"],
            batch_id=row["batch_id"],
            username=username,
            start_now_date=date.fromisoformat(str(row["start_date"])),
            download_stories=download_stories,
            generated_story_url=(
                f"https://www.instagram.com/stories/{username}/"
                if download_stories
                else None
            ),
            working_folder=working_folder,
            status=AccountStatus(str(row["status"])),
            created_at=created_at,
            updated_at=updated_at,
        )

