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
        WHERE b.status <> 'COMPLETED'
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
    if not account_rows:
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

    default_date = batch["default_start_now_date"] or account_rows[0]["start_now_date"]
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


__all__ = [
    "AccountRuntimeProgress",
    "PendingBatchSummary",
    "finish_batch",
    "get_account_runtime_progress",
    "list_pending_batches",
    "load_batch_draft",
    "mark_batch_interrupted",
]
