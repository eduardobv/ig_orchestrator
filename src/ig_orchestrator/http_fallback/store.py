"""Which URL jobs were downloaded over HTTP (small side table, no model change)."""

from __future__ import annotations

from sqlite3 import Connection

from ig_orchestrator.logging_config import get_logger

logger = get_logger()

DOWNLOAD_METHOD_BOT = "bot"
DOWNLOAD_METHOD_HTTP = "http"


def ensure_http_fallback_schema(connection: Connection) -> None:
    from ig_orchestrator.db.schema_mode import is_gui_schema

    if not is_gui_schema(connection):
        return  # the v1 rollback database is never extended
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS http_downloads (
            url_job_id INTEGER PRIMARY KEY,
            files_count INTEGER NOT NULL DEFAULT 0,
            downloaded_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.commit()


def record_http_download(connection: Connection, url_job_id: int, files_count: int) -> None:
    try:
        ensure_http_fallback_schema(connection)
        connection.execute(
            """
            INSERT INTO http_downloads (url_job_id, files_count, downloaded_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(url_job_id) DO UPDATE SET
                files_count = excluded.files_count,
                downloaded_at = excluded.downloaded_at
            """,
            (url_job_id, files_count),
        )
        connection.commit()
    except Exception:
        logger.warning("Recording the HTTP download failed: job_id={}", url_job_id, exc_info=True)


def http_downloaded_job_ids(connection: Connection, job_ids: list[int]) -> set[int]:
    """Subset of ``job_ids`` whose files came over HTTP (empty if never used)."""

    if not job_ids:
        return set()
    try:
        placeholders = ",".join("?" for _ in job_ids)
        rows = connection.execute(
            f"SELECT url_job_id FROM http_downloads WHERE url_job_id IN ({placeholders})",
            job_ids,
        ).fetchall()
    except Exception:
        return set()
    return {int(row[0]) for row in rows}


__all__ = [
    "DOWNLOAD_METHOD_BOT",
    "DOWNLOAD_METHOD_HTTP",
    "ensure_http_fallback_schema",
    "http_downloaded_job_ids",
    "record_http_download",
]
