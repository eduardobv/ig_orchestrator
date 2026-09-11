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

_URL_SELECT = """
SELECT
    bu.id,
    bu.batch_account_id AS account_id,
    bu.batch_run_id AS run_id,
    bu.url,
    pt.code AS publication_type,
    us.code AS source,
    bus.code AS status,
    bu.retries,
    bu.max_retries,
    bu.last_error_text AS last_error,
    be.code AS last_error_type,
    bu.non_retryable,
    bu.sent_message_id,
    bu.started_at,
    bu.finished_at,
    bu.next_retry_at,
    bu.created_at,
    bu.updated_at
FROM batch_urls bu
JOIN publication_types pt ON pt.id = bu.publication_type_id
JOIN url_sources us ON us.id = bu.source_id
JOIN batch_url_statuses bus ON bus.id = bu.status_id
LEFT JOIN bot_errors be ON be.id = bu.last_error_id
"""


class GuiUrlJobRepository(UrlJobRepository):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create(self, job: UrlJob) -> UrlJob:
        cursor = self.connection.execute(
            """
            INSERT INTO batch_urls (
                batch_account_id, batch_run_id, url, publication_type_id,
                source_id, status_id, retries, max_retries, last_error_id,
                last_error_text, non_retryable, sent_message_id, started_at,
                finished_at, next_retry_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.account_id,
                job.run_id,
                job.url,
                self._lookups.id_for("publication_types", job.publication_type.value),
                self._lookups.id_for("url_sources", job.source.value),
                self._lookups.id_for("batch_url_statuses", job.status.value),
                job.retries,
                job.max_retries,
                self._lookups.optional_id_for("bot_errors", job.last_error_type),
                job.last_error,
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
            raise RuntimeError("URL was not stored")
        return stored

    def get_by_id(self, job_id: int) -> UrlJob | None:
        row = self.connection.execute(
            _URL_SELECT + " WHERE bu.id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_url_job(row)

    def list_by_account(self, account_id: int) -> list[UrlJob]:
        rows = self.connection.execute(
            _URL_SELECT + " WHERE bu.batch_account_id = ? ORDER BY bu.id",
            (account_id,),
        ).fetchall()
        return [_row_to_url_job(row) for row in rows]

    def list_by_status(self, status: UrlJobStatus) -> list[UrlJob]:
        status_id = self._lookups.id_for("batch_url_statuses", status.value)
        rows = self.connection.execute(
            _URL_SELECT + " WHERE bu.status_id = ? ORDER BY bu.id",
            (status_id,),
        ).fetchall()
        return [_row_to_url_job(row) for row in rows]

    def assign_unassigned_to_run_by_account(
        self,
        *,
        account_id: int,
        run_id: int,
    ) -> list[UrlJob]:
        if account_id <= 0:
            raise ValueError("account_id must be positive")
        if run_id <= 0:
            raise ValueError("run_id must be positive")
        self.connection.execute(
            """
            UPDATE batch_urls
            SET batch_run_id = ?, updated_at = datetime('now')
            WHERE batch_account_id = ? AND batch_run_id IS NULL
            """,
            (run_id, account_id),
        )
        self.connection.commit()
        return self.list_by_account(account_id)

    def update_status(
        self,
        job_id: int,
        status: UrlJobStatus,
        *,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> UrlJob:
        status_id = self._lookups.id_for("batch_url_statuses", status.value)
        self.connection.execute(
            """
            UPDATE batch_urls
            SET status_id = ?,
                started_at = COALESCE(?, started_at),
                finished_at = COALESCE(?, finished_at),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                status_id,
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
            UPDATE batch_urls
            SET sent_message_id = ?, updated_at = datetime('now')
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
        type_id = self._lookups.id_for("publication_types", publication_type.value)
        self.connection.execute(
            """
            UPDATE batch_urls
            SET publication_type_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (type_id, job_id),
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
        status_id = self._lookups.id_for("batch_url_statuses", status.value)
        self.connection.execute(
            """
            UPDATE batch_urls
            SET status_id = ?,
                last_error_text = ?,
                last_error_id = ?,
                non_retryable = ?,
                retries = ?,
                next_retry_at = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                status_id,
                last_error,
                self._lookups.optional_id_for("bot_errors", last_error_type),
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

