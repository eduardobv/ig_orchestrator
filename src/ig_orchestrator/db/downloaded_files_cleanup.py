from __future__ import annotations

from sqlite3 import Connection

from ig_orchestrator.db.schema_mode import is_gui_schema

DEFAULT_RETENTION = "on_complete"


def downloaded_files_retention(connection: Connection) -> str:
    if not is_gui_schema(connection):
        return DEFAULT_RETENTION
    row = connection.execute(
        "SELECT value FROM app_settings WHERE key = 'retention.downloaded_files'"
    ).fetchone()
    if row is None or not str(row["value"]).strip():
        return DEFAULT_RETENTION
    value = str(row["value"]).strip()
    if value not in {"on_complete", "keep"}:
        return DEFAULT_RETENTION
    return value


def purge_downloaded_files(
    connection: Connection,
    *,
    batch_id: int | None = None,
) -> int:
    """Delete downloaded file rows. Optionally limit to one batch.

    Does not change batch_urls / url_jobs status. Returns deleted row count.
    """

    if is_gui_schema(connection):
        if batch_id is None:
            cursor = connection.execute("DELETE FROM downloaded_files")
        else:
            cursor = connection.execute(
                """
                DELETE FROM downloaded_files
                WHERE batch_url_id IN (
                    SELECT bu.id
                    FROM batch_urls bu
                    JOIN batch_accounts ba ON ba.id = bu.batch_account_id
                    WHERE ba.batch_id = ?
                )
                """,
                (batch_id,),
            )
    else:
        if batch_id is None:
            cursor = connection.execute("DELETE FROM download_files")
        else:
            cursor = connection.execute(
                """
                DELETE FROM download_files
                WHERE url_job_id IN (
                    SELECT j.id
                    FROM url_jobs j
                    JOIN accounts a ON a.id = j.account_id
                    WHERE a.batch_id = ?
                )
                """,
                (batch_id,),
            )
    connection.commit()
    return int(cursor.rowcount or 0)


def maybe_purge_downloaded_files_for_batch(
    connection: Connection,
    batch_id: int,
) -> int:
    """Purge a completed batch when retention is on_complete."""

    if downloaded_files_retention(connection) != "on_complete":
        return 0
    return purge_downloaded_files(connection, batch_id=batch_id)


__all__ = [
    "DEFAULT_RETENTION",
    "downloaded_files_retention",
    "maybe_purge_downloaded_files_for_batch",
    "purge_downloaded_files",
]
