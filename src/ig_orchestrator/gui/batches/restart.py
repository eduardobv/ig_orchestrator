from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from ig_orchestrator.models import InputBatchStatus


# A batch that is not running and has been started at least once.
_RESTARTABLE_BATCH_STATUSES = frozenset(
    {
        InputBatchStatus.IMPORTED.value,
        InputBatchStatus.PROCESSING.value,
        InputBatchStatus.PARTIAL.value,
        InputBatchStatus.FAILED.value,
        InputBatchStatus.COMPLETED.value,
        InputBatchStatus.AWAITING_RENAME.value,
    }
)


@dataclass(frozen=True, slots=True)
class BatchRestartResult:
    accounts_reset: int
    urls_reset: int
    download_records_discarded: int


def restart_batch(connection: Connection, batch_id: int) -> BatchRestartResult:
    """Leave an executed batch as if it had just been imported.

    Every URL goes back to ``PENDING`` with its retries and errors cleared and
    every account to ``PENDING``, so the next execution downloads it all again.
    Files already on disk are never touched; their ``download_files`` rows are
    kept as audit with status ``DELETED`` (discarded) so reports and rename do
    not count them again.
    """

    batch = connection.execute(
        "SELECT status FROM input_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if batch is None:
        raise ValueError(f"Batch not found: {batch_id}")
    if str(batch["status"]) not in _RESTARTABLE_BATCH_STATUSES:
        raise ValueError("Only an executed batch can be restarted")

    account_ids = [
        int(row["id"])
        for row in connection.execute(
            "SELECT id FROM accounts WHERE batch_id = ?", (batch_id,)
        ).fetchall()
    ]
    urls_reset = 0
    discarded = 0
    for account_id in account_ids:
        discarded += connection.execute(
            """
            UPDATE download_files
            SET status = 'DELETED', updated_at = datetime('now')
            WHERE status <> 'DELETED'
              AND url_job_id IN (SELECT id FROM url_jobs WHERE account_id = ?)
            """,
            (account_id,),
        ).rowcount
        urls_reset += connection.execute(
            """
            UPDATE url_jobs
            SET status = 'PENDING',
                retries = 0,
                last_error = NULL,
                last_error_type = NULL,
                non_retryable = 0,
                sent_message_id = NULL,
                started_at = NULL,
                finished_at = NULL,
                next_retry_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ?
            """,
            (account_id,),
        ).rowcount
    connection.execute(
        """
        UPDATE accounts SET status = 'PENDING', updated_at = datetime('now')
        WHERE batch_id = ?
        """,
        (batch_id,),
    )
    connection.execute(
        """
        UPDATE input_batches SET status = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (InputBatchStatus.IMPORTED.value, batch_id),
    )
    connection.commit()
    return BatchRestartResult(
        accounts_reset=len(account_ids),
        urls_reset=urls_reset,
        download_records_discarded=discarded,
    )


__all__ = ["BatchRestartResult", "restart_batch"]
