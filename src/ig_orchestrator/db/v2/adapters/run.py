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

_RUN_SELECT = """
SELECT
    r.id,
    r.batch_id,
    r.batch_account_id AS account_id,
    brs.code AS status,
    r.total_urls,
    r.completed_urls,
    r.failed_urls,
    r.downloaded_files,
    NULL AS report_path,
    r.started_at,
    r.finished_at,
    r.summary
FROM batch_runs r
JOIN batch_run_statuses brs ON brs.id = r.status_id
"""


class GuiRunRepository(RunRepository):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create(
        self,
        summary: RunSummary,
        *,
        batch_id: int | None = None,
        account_id: int | None = None,
        report_path: Path | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> RunRecord:
        status_id = self._lookups.id_for("batch_run_statuses", summary.status.value)
        cursor = self.connection.execute(
            """
            INSERT INTO batch_runs (
                batch_id, batch_account_id, status_id, total_urls, completed_urls,
                failed_urls, downloaded_files, started_at, finished_at, summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                account_id,
                status_id,
                summary.total_urls,
                summary.completed_urls,
                summary.failed_urls,
                summary.downloaded_files,
                dump_datetime(started_at or datetime.now(timezone.utc)),
                dump_datetime(finished_at),
                summary.summary,
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Run was not stored")
        return stored

    def get_by_id(self, run_id: int) -> RunRecord | None:
        row = self.connection.execute(
            _RUN_SELECT + " WHERE r.id = ?",
            (run_id,),
        ).fetchone()
        return _row_to_run(row)

    def list_by_status(self, status: RunStatus) -> list[RunRecord]:
        status_id = self._lookups.id_for("batch_run_statuses", status.value)
        rows = self.connection.execute(
            _RUN_SELECT + " WHERE r.status_id = ? ORDER BY r.id",
            (status_id,),
        ).fetchall()
        return [_row_to_run(row) for row in rows]

    def update_summary(
        self,
        run_id: int,
        summary: RunSummary,
        *,
        report_path: Path | None = None,
        finished_at: datetime | None = None,
    ) -> RunRecord:
        status_id = self._lookups.id_for("batch_run_statuses", summary.status.value)
        self.connection.execute(
            """
            UPDATE batch_runs
            SET status_id = ?,
                total_urls = ?,
                completed_urls = ?,
                failed_urls = ?,
                downloaded_files = ?,
                finished_at = COALESCE(?, finished_at),
                summary = ?
            WHERE id = ?
            """,
            (
                status_id,
                summary.total_urls,
                summary.completed_urls,
                summary.failed_urls,
                summary.downloaded_files,
                dump_datetime(finished_at),
                summary.summary,
                run_id,
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(run_id)
        if stored is None:
            raise ValueError(f"Run not found: {run_id}")
        return stored

