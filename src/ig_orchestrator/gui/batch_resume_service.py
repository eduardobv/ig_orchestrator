from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.models import InputBatchStatus


_RESUMABLE_JOB_STATUSES = (
    "PENDING",
    "SENT_TO_BOT",
    "WAITING_DOWNLOAD",
    "RETRY_PENDING",
    "FAILED_TEMPORARY",
)
_RETRY_JOB_STATUSES = (
    "SENT_TO_BOT",
    "WAITING_DOWNLOAD",
    "RETRY_PENDING",
    "FAILED_TEMPORARY",
)


@dataclass(frozen=True, slots=True)
class PendingBatchSummary:
    batch_id: int
    batch_name: str
    batch_date: str
    status: str
    total_accounts: int
    completed_accounts: int
    retry_accounts: int
    remaining_accounts: int

    @property
    def is_draft(self) -> bool:
        return self.status == InputBatchStatus.DRAFT.value


@dataclass(frozen=True, slots=True)
class AccountRuntimeProgress:
    account_id: int
    username: str
    status: str
    total_items: int
    completed_items: int
    retry_items: int
    pending_items: int
    failed_items: int


def list_pending_batches(connection: Connection) -> list[PendingBatchSummary]:
    placeholders = ", ".join("?" for _ in _RESUMABLE_JOB_STATUSES)
    rows = connection.execute(
        f"""
        SELECT b.id, b.batch_name, b.created_at, b.status,
               (SELECT COUNT(*) FROM accounts a WHERE a.batch_id = b.id) AS total_accounts,
               (SELECT COUNT(*) FROM accounts a
                WHERE a.batch_id = b.id AND a.status = 'COMPLETED') AS completed_accounts,
               (SELECT COUNT(DISTINCT a.id)
                FROM accounts a JOIN url_jobs j ON j.account_id = a.id
                WHERE a.batch_id = b.id
                  AND j.status IN ({', '.join('?' for _ in _RETRY_JOB_STATUSES)})) AS retry_accounts,
               (SELECT COUNT(DISTINCT a.id)
                FROM accounts a JOIN url_jobs j ON j.account_id = a.id
                WHERE a.batch_id = b.id
                  AND j.status IN ({placeholders})) AS remaining_accounts
        FROM input_batches b
        WHERE b.status NOT IN ('DRAFT', 'COMPLETED')
          AND EXISTS (
              SELECT 1
              FROM accounts a JOIN url_jobs j ON j.account_id = a.id
              WHERE a.batch_id = b.id
                AND a.status IN ('PENDING', 'PROCESSING', 'PARTIAL')
                AND j.status IN ({placeholders})
          )
        ORDER BY b.created_at DESC, b.id DESC
        """,
        (*_RETRY_JOB_STATUSES, *_RESUMABLE_JOB_STATUSES, *_RESUMABLE_JOB_STATUSES),
    ).fetchall()
    return [
        PendingBatchSummary(
            batch_id=int(row["id"]),
            batch_name=str(row["batch_name"]),
            batch_date=str(row["created_at"]),
            status=str(row["status"]),
            total_accounts=int(row["total_accounts"]),
            completed_accounts=int(row["completed_accounts"]),
            retry_accounts=int(row["retry_accounts"]),
            remaining_accounts=int(row["remaining_accounts"]),
        )
        for row in rows
    ]


def list_managed_batches(connection: Connection) -> list[PendingBatchSummary]:
    """Return editable drafts and executions that still have resumable work."""

    executions = {item.batch_id: item for item in list_pending_batches(connection)}
    rows = connection.execute(
        """
        SELECT b.id, b.batch_name, b.created_at, b.status,
               COUNT(DISTINCT a.id) AS total_accounts
        FROM input_batches b
        LEFT JOIN accounts a ON a.batch_id = b.id
        WHERE b.status = 'DRAFT'
        GROUP BY b.id
        ORDER BY b.created_at DESC, b.id DESC
        """
    ).fetchall()
    for row in rows:
        batch_id = int(row["id"])
        executions[batch_id] = PendingBatchSummary(
            batch_id=batch_id,
            batch_name=str(row["batch_name"]),
            batch_date=str(row["created_at"]),
            status=str(row["status"]),
            total_accounts=int(row["total_accounts"] or 0),
            completed_accounts=0,
            retry_accounts=0,
            remaining_accounts=int(row["total_accounts"] or 0),
        )
    return sorted(
        executions.values(),
        key=lambda item: (item.batch_date, item.batch_id),
        reverse=True,
    )


def load_batch_draft(connection: Connection, batch_id: int) -> BatchDraft:
    batch = connection.execute(
        "SELECT * FROM input_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if batch is None:
        raise ValueError(f"Batch not found: {batch_id}")
    account_rows = connection.execute(
        "SELECT * FROM accounts WHERE batch_id = ? ORDER BY id",
        (batch_id,),
    ).fetchall()
    if not account_rows and str(batch["status"]) != InputBatchStatus.DRAFT.value:
        raise ValueError(f"Batch {batch_id} has no accounts")

    accounts: list[AccountDraft] = []
    for row in account_rows:
        url_rows = connection.execute(
            """
            SELECT url FROM url_jobs
            WHERE account_id = ? AND source = 'INPUT_URL'
            ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
        accounts.append(
            AccountDraft(
                username=str(row["username"]),
                download_stories=bool(row["download_stories"]),
                urls=[str(url_row["url"]) for url_row in url_rows],
                start_now_date=str(row["start_now_date"]),
                is_new_account=bool(row["is_new_account"]),
                owner_id=str(row["rename_owner_id"] or ""),
                start_init_date=str(row["rename_start_init_date"] or ""),
                destination_path=str(row["rename_destination_path"] or ""),
            )
        )

    default_date = batch["default_start_now_date"]
    if not default_date and account_rows:
        default_date = account_rows[0]["start_now_date"]
    if not default_date:
        raise ValueError(f"Batch {batch_id} has no default start date")
    return BatchDraft(
        batch_name=str(batch["batch_name"]),
        default_start_now_date=str(default_date),
        accounts=accounts,
        schema_version=str(batch["schema_version"]),
    )


def get_account_runtime_progress(
    connection: Connection,
    batch_id: int,
) -> list[AccountRuntimeProgress]:
    rows = connection.execute(
        """
        SELECT a.id, a.username, a.status,
               COUNT(j.id) AS total_items,
               SUM(CASE WHEN j.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_items,
               SUM(CASE WHEN j.status IN ('SENT_TO_BOT', 'WAITING_DOWNLOAD',
                                          'RETRY_PENDING', 'FAILED_TEMPORARY')
                        THEN 1 ELSE 0 END) AS retry_items,
               SUM(CASE WHEN j.status = 'PENDING' THEN 1 ELSE 0 END) AS pending_items,
               SUM(CASE WHEN j.status = 'FAILED_FINAL' THEN 1 ELSE 0 END) AS failed_items
        FROM accounts a
        LEFT JOIN url_jobs j ON j.account_id = a.id
        WHERE a.batch_id = ?
        GROUP BY a.id
        ORDER BY a.id
        """,
        (batch_id,),
    ).fetchall()
    return [
        AccountRuntimeProgress(
            account_id=int(row["id"]),
            username=str(row["username"]),
            status=str(row["status"]),
            total_items=int(row["total_items"] or 0),
            completed_items=int(row["completed_items"] or 0),
            retry_items=int(row["retry_items"] or 0),
            pending_items=int(row["pending_items"] or 0),
            failed_items=int(row["failed_items"] or 0),
        )
        for row in rows
    ]


def finish_batch(connection: Connection, batch_id: int) -> None:
    cursor = connection.execute(
        """
        UPDATE input_batches
        SET status = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (InputBatchStatus.COMPLETED.value, batch_id),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"Batch not found: {batch_id}")
    connection.commit()


def activate_draft_batch(connection: Connection, batch_id: int) -> None:
    """Lock a saved draft for editing immediately before its first execution."""

    row = connection.execute(
        "SELECT status FROM input_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Batch not found: {batch_id}")
    if str(row["status"]) == InputBatchStatus.DRAFT.value:
        connection.execute(
            """
            UPDATE input_batches
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (InputBatchStatus.IMPORTED.value, batch_id),
        )
        connection.commit()


def delete_draft_batch(connection: Connection, batch_id: int) -> None:
    """Delete only a never-executed draft and its draft-only child rows."""

    row = connection.execute(
        "SELECT status FROM input_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Batch not found: {batch_id}")
    if str(row["status"]) != InputBatchStatus.DRAFT.value:
        raise ValueError("Only saved DRAFT batches can be deleted")
    if connection.execute(
        "SELECT 1 FROM runs WHERE batch_id = ? LIMIT 1", (batch_id,)
    ).fetchone() is not None:
        raise ValueError("An executed batch cannot be deleted")
    account_ids = [
        int(item["id"])
        for item in connection.execute(
            "SELECT id FROM accounts WHERE batch_id = ?", (batch_id,)
        ).fetchall()
    ]
    for account_id in account_ids:
        connection.execute(
            "DELETE FROM duplicate_url_jobs WHERE account_id = ?", (account_id,)
        )
        connection.execute("DELETE FROM url_jobs WHERE account_id = ?", (account_id,))
    connection.execute("DELETE FROM accounts WHERE batch_id = ?", (batch_id,))
    connection.execute("DELETE FROM input_batches WHERE id = ?", (batch_id,))
    connection.commit()


def mark_batch_interrupted(connection: Connection, batch_id: int) -> None:
    connection.execute(
        """
        UPDATE input_batches
        SET status = ?, updated_at = datetime('now')
        WHERE id = ? AND status <> ?
        """,
        (
            InputBatchStatus.PARTIAL.value,
            batch_id,
            InputBatchStatus.COMPLETED.value,
        ),
    )
    connection.commit()


def fail_account_manually(
    connection: Connection,
    *,
    batch_id: int,
    account_id: int,
) -> int:
    """Stop one pending/processing account without deleting its audit trail."""
    account = connection.execute(
        "SELECT id, status FROM accounts WHERE id = ? AND batch_id = ?",
        (account_id, batch_id),
    ).fetchone()
    if account is None:
        raise ValueError(f"Account {account_id} does not belong to batch {batch_id}")
    if str(account["status"]) not in {"PENDING", "PROCESSING", "PARTIAL"}:
        raise ValueError(
            "Only pending or processing accounts can be removed from a running batch"
        )

    cursor = connection.execute(
        """
        UPDATE url_jobs
        SET status = 'FAILED_FINAL',
            last_error = 'Account removed manually from GUI',
            last_error_type = 'MANUAL_ACCOUNT_REMOVAL',
            non_retryable = 1,
            next_retry_at = NULL,
            finished_at = COALESCE(finished_at, datetime('now')),
            updated_at = datetime('now')
        WHERE account_id = ?
          AND status NOT IN ('COMPLETED', 'FAILED_FINAL')
        """,
        (account_id,),
    )
    connection.execute(
        """
        UPDATE accounts
        SET status = 'FAILED', updated_at = datetime('now')
        WHERE id = ?
        """,
        (account_id,),
    )
    connection.commit()
    return int(cursor.rowcount)


def complete_account_manually(
    connection: Connection,
    *,
    batch_id: int,
    account_id: int,
) -> int:
    """Close a stuck account while retaining unresolved URLs as audited failures."""

    batch = connection.execute(
        "SELECT status FROM input_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if batch is None:
        raise ValueError(f"Batch not found: {batch_id}")
    if str(batch["status"]) not in {"PARTIAL", "FAILED", "PROCESSING"}:
        raise ValueError("Manual completion is only available for an interrupted execution")
    account = connection.execute(
        "SELECT status FROM accounts WHERE id = ? AND batch_id = ?",
        (account_id, batch_id),
    ).fetchone()
    if account is None:
        raise ValueError(f"Account {account_id} does not belong to batch {batch_id}")
    if str(account["status"]) == "COMPLETED":
        raise ValueError("The selected account is already completed")

    cursor = connection.execute(
        """
        UPDATE url_jobs
        SET status = 'FAILED_FINAL',
            last_error = COALESCE(last_error, 'Account completed manually from GUI'),
            last_error_type = COALESCE(last_error_type, 'MANUAL_ACCOUNT_COMPLETION'),
            non_retryable = 1,
            next_retry_at = NULL,
            finished_at = COALESCE(finished_at, datetime('now')),
            updated_at = datetime('now')
        WHERE account_id = ?
          AND status NOT IN ('COMPLETED', 'FAILED_FINAL')
        """,
        (account_id,),
    )
    connection.execute(
        "UPDATE accounts SET status = 'COMPLETED', updated_at = datetime('now') WHERE id = ?",
        (account_id,),
    )
    remaining = connection.execute(
        """
        SELECT 1 FROM accounts
        WHERE batch_id = ? AND status <> 'COMPLETED'
        LIMIT 1
        """,
        (batch_id,),
    ).fetchone()
    connection.execute(
        "UPDATE input_batches SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (
            InputBatchStatus.COMPLETED.value
            if remaining is None
            else InputBatchStatus.PARTIAL.value,
            batch_id,
        ),
    )
    connection.commit()
    return int(cursor.rowcount)


def is_batch_ready_for_rename(connection: Connection, batch_id: int) -> bool:
    """A real run may be renamed once every account is operationally closed."""

    has_run = connection.execute(
        """
        SELECT 1 FROM runs
        WHERE batch_id = ? AND summary NOT LIKE 'Dry-run batch %'
        LIMIT 1
        """,
        (batch_id,),
    ).fetchone()
    if has_run is None:
        return False
    unfinished = connection.execute(
        "SELECT 1 FROM accounts WHERE batch_id = ? AND status <> 'COMPLETED' LIMIT 1",
        (batch_id,),
    ).fetchone()
    return unfinished is None


__all__ = [
    "AccountRuntimeProgress",
    "PendingBatchSummary",
    "activate_draft_batch",
    "complete_account_manually",
    "delete_draft_batch",
    "finish_batch",
    "fail_account_manually",
    "get_account_runtime_progress",
    "is_batch_ready_for_rename",
    "list_managed_batches",
    "list_pending_batches",
    "load_batch_draft",
    "mark_batch_interrupted",
]
