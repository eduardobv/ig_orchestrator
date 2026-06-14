from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import dump_datetime, load_datetime
from ig_orchestrator.models import PublicationType, UrlJob, UrlJobStatus, UrlSource


class UrlJobRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, job: UrlJob) -> UrlJob:
        cursor = self.connection.execute(
            """
            INSERT INTO url_jobs (
                account_id, run_id, url, publication_type, source, status,
                retries, max_retries, last_error, last_error_type, non_retryable,
                sent_message_id, started_at, finished_at, next_retry_at,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.account_id,
                job.run_id,
                job.url,
                job.publication_type.value,
                job.source.value,
                job.status.value,
                job.retries,
                job.max_retries,
                job.last_error,
                job.last_error_type,
                int(job.non_retryable),
                job.sent_message_id,
                dump_datetime(job.started_at),
                dump_datetime(job.finished_at),
                dump_datetime(job.next_retry_at),
                dump_datetime(job.created_at),
                dump_datetime(job.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("URL job was not stored")
        return stored

    def get_by_id(self, job_id: int) -> UrlJob | None:
        row = self.connection.execute(
            "SELECT * FROM url_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_url_job(row)

    def list_by_account(self, account_id: int) -> list[UrlJob]:
        rows = self.connection.execute(
            "SELECT * FROM url_jobs WHERE account_id = ? ORDER BY id",
            (account_id,),
        ).fetchall()
        return [_row_to_url_job(row) for row in rows]

    def list_by_status(self, status: UrlJobStatus) -> list[UrlJob]:
        rows = self.connection.execute(
            "SELECT * FROM url_jobs WHERE status = ? ORDER BY id",
            (status.value,),
        ).fetchall()
        return [_row_to_url_job(row) for row in rows]

    def update_status(
        self,
        job_id: int,
        status: UrlJobStatus,
        *,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> UrlJob:
        self.connection.execute(
            """
            UPDATE url_jobs
            SET status = ?,
                started_at = COALESCE(?, started_at),
                finished_at = COALESCE(?, finished_at),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                status.value,
                dump_datetime(started_at),
                dump_datetime(finished_at),
                job_id,
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(job_id)
        if stored is None:
            raise ValueError(f"URL job not found: {job_id}")
        return stored

    def update_sent_message_id(self, job_id: int, sent_message_id: int) -> UrlJob:
        if sent_message_id <= 0:
            raise ValueError("sent_message_id must be positive")

        self.connection.execute(
            """
            UPDATE url_jobs
            SET sent_message_id = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (sent_message_id, job_id),
        )
        self.connection.commit()
        stored = self.get_by_id(job_id)
        if stored is None:
            raise ValueError(f"URL job not found: {job_id}")
        return stored

    def update_publication_type(
        self,
        job_id: int,
        publication_type: PublicationType,
    ) -> UrlJob:
        self.connection.execute(
            """
            UPDATE url_jobs
            SET publication_type = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (publication_type.value, job_id),
        )
        self.connection.commit()
        stored = self.get_by_id(job_id)
        if stored is None:
            raise ValueError(f"URL job not found: {job_id}")
        return stored

    def update_error(
        self,
        job_id: int,
        *,
        status: UrlJobStatus,
        last_error: str,
        last_error_type: str,
        non_retryable: bool,
        retries: int | None = None,
        next_retry_at: datetime | None = None,
    ) -> UrlJob:
        current = self.get_by_id(job_id)
        if current is None:
            raise ValueError(f"URL job not found: {job_id}")
        self.connection.execute(
            """
            UPDATE url_jobs
            SET status = ?,
                last_error = ?,
                last_error_type = ?,
                non_retryable = ?,
                retries = ?,
                next_retry_at = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                status.value,
                last_error,
                last_error_type,
                int(non_retryable),
                current.retries if retries is None else retries,
                dump_datetime(next_retry_at),
                job_id,
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(job_id)
        if stored is None:
            raise ValueError(f"URL job not found after update: {job_id}")
        return stored


def _row_to_url_job(row: Row | None) -> UrlJob | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored url_job row is missing timestamps")
    return UrlJob(
        id=row["id"],
        account_id=row["account_id"],
        run_id=row["run_id"],
        url=row["url"],
        publication_type=PublicationType(row["publication_type"]),
        source=UrlSource(row["source"]),
        status=UrlJobStatus(row["status"]),
        retries=row["retries"],
        max_retries=row["max_retries"],
        last_error=row["last_error"],
        last_error_type=row["last_error_type"],
        non_retryable=bool(row["non_retryable"]),
        sent_message_id=row["sent_message_id"],
        started_at=load_datetime(row["started_at"]),
        finished_at=load_datetime(row["finished_at"]),
        next_retry_at=load_datetime(row["next_retry_at"]),
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["UrlJobRepository"]
