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

_BATCH_SELECT = """
SELECT
    b.id,
    b.name AS batch_name,
    b.schema_version,
    NULL AS source_file,
    bs.code AS status,
    b.created_at,
    b.updated_at
FROM batches b
JOIN batch_statuses bs ON bs.id = b.status_id
"""


class GuiBatchRepository(BatchRepository):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create(self, batch: InputBatch) -> InputBatch:
        status_id = self._lookups.id_for("batch_statuses", batch.status.value)
        cursor = self.connection.execute(
            """
            INSERT INTO batches (
                name, schema_version, status_id, start_date, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch.batch_name,
                batch.schema_version,
                status_id,
                date.today().isoformat(),
                dump_datetime(batch.created_at),
                dump_datetime(batch.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Batch was not stored")
        return stored

    def get_by_id(self, batch_id: int) -> InputBatch | None:
        row = self.connection.execute(
            _BATCH_SELECT + " WHERE b.id = ?",
            (batch_id,),
        ).fetchone()
        return _row_to_batch(row)

    def get_by_name(self, batch_name: str) -> InputBatch | None:
        row = self.connection.execute(
            _BATCH_SELECT + " WHERE b.name = ? ORDER BY b.id DESC LIMIT 1",
            (batch_name,),
        ).fetchone()
        return _row_to_batch(row)

    def list_by_status(self, status: InputBatchStatus) -> list[InputBatch]:
        status_id = self._lookups.id_for("batch_statuses", status.value)
        rows = self.connection.execute(
            _BATCH_SELECT + " WHERE b.status_id = ? ORDER BY b.id",
            (status_id,),
        ).fetchall()
        return [_row_to_batch(row) for row in rows]

    def list_with_resumable_work(self) -> list[InputBatch]:
        rows = self.connection.execute(
            _BATCH_SELECT
            + """
            WHERE b.id IN (
                SELECT ba.batch_id
                FROM batch_accounts ba
                JOIN batch_urls bu ON bu.batch_account_id = ba.id
                JOIN batch_account_statuses bas ON bas.id = ba.status_id
                JOIN batch_url_statuses bus ON bus.id = bu.status_id
                WHERE bas.code IN ('PENDING', 'PROCESSING', 'PARTIAL', 'INCOMPLETE')
                  AND bus.code IN (
                      'PENDING', 'SENT_TO_BOT', 'WAITING_DOWNLOAD',
                      'RETRY_PENDING', 'FAILED_TEMPORARY'
                  )
            )
            ORDER BY b.id
            """
        ).fetchall()
        return [_row_to_batch(row) for row in rows]

    def has_resumable_work(self, batch_id: int) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM batch_accounts ba
            JOIN batch_urls bu ON bu.batch_account_id = ba.id
            JOIN batch_account_statuses bas ON bas.id = ba.status_id
            JOIN batch_url_statuses bus ON bus.id = bu.status_id
            WHERE ba.batch_id = ?
              AND bas.code IN ('PENDING', 'PROCESSING', 'PARTIAL', 'INCOMPLETE')
              AND bus.code IN (
                  'PENDING', 'SENT_TO_BOT', 'WAITING_DOWNLOAD',
                  'RETRY_PENDING', 'FAILED_TEMPORARY'
              )
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
        return row is not None

    def update_status(self, batch_id: int, status: InputBatchStatus) -> InputBatch:
        status_id = self._lookups.id_for("batch_statuses", status.value)
        self.connection.execute(
            """
            UPDATE batches
            SET status_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_id, batch_id),
        )
        self.connection.commit()
        stored = self.get_by_id(batch_id)
        if stored is None:
            raise ValueError(f"Input batch not found: {batch_id}")
        return stored

