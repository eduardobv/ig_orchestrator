from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlite3 import Connection


def purge_telemetry(
    connection: Connection,
    *,
    older_than_days: int | None = None,
    batch_id: int | None = None,
) -> int:
    """Delete attempts (and their events) older than N days and/or of a batch.

    Returns the number of attempts removed. At least one criterion is required.
    """

    if older_than_days is None and batch_id is None:
        raise ValueError("older_than_days or batch_id is required")
    conditions: list[str] = []
    params: list[object] = []
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        conditions.append("started_at < ?")
        params.append(cutoff.isoformat(timespec="seconds"))
    if batch_id is not None:
        conditions.append("batch_id = ?")
        params.append(batch_id)
    where = " AND ".join(conditions)
    with connection:
        ids = f"SELECT id FROM url_job_attempts WHERE {where}"
        connection.execute(
            f"DELETE FROM bot_message_events WHERE attempt_id IN ({ids})", params
        )
        connection.execute(
            f"DELETE FROM run_wait_events WHERE attempt_id IN ({ids})", params
        )
        cursor = connection.execute(
            f"DELETE FROM url_job_attempts WHERE {where}", params
        )
    return cursor.rowcount


__all__ = ["purge_telemetry"]
