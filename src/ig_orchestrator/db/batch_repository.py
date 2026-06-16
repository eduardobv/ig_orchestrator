from __future__ import annotations

from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import (
    dump_datetime,
    dump_path,
    load_datetime,
    load_path,
)
from ig_orchestrator.models import InputBatch, InputBatchStatus


class BatchRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, batch: InputBatch) -> InputBatch:
        cursor = self.connection.execute(
            """
            INSERT INTO input_batches (
                batch_name, schema_version, source_file, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch.batch_name,
                batch.schema_version,
                dump_path(batch.source_file),
                batch.status.value,
                dump_datetime(batch.created_at),
                dump_datetime(batch.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Input batch was not stored")
        return stored

    def get_by_id(self, batch_id: int) -> InputBatch | None:
        row = self.connection.execute(
            "SELECT * FROM input_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        return _row_to_batch(row)

    def get_by_name(self, batch_name: str) -> InputBatch | None:
        row = self.connection.execute(
            """
            SELECT * FROM input_batches
            WHERE batch_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (batch_name,),
        ).fetchone()
        return _row_to_batch(row)

    def list_by_status(self, status: InputBatchStatus) -> list[InputBatch]:
        rows = self.connection.execute(
            "SELECT * FROM input_batches WHERE status = ? ORDER BY id",
            (status.value,),
        ).fetchall()
        return [_row_to_batch(row) for row in rows]

    def list_with_resumable_work(self) -> list[InputBatch]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT input_batches.*
            FROM input_batches
            JOIN accounts ON accounts.batch_id = input_batches.id
            JOIN url_jobs ON url_jobs.account_id = accounts.id
            WHERE accounts.status IN ('PENDING', 'PROCESSING', 'PARTIAL')
              AND url_jobs.status IN (
                  'PENDING',
                  'SENT_TO_BOT',
                  'WAITING_DOWNLOAD',
                  'RETRY_PENDING',
                  'FAILED_TEMPORARY'
              )
            ORDER BY input_batches.id
            """
        ).fetchall()
        return [_row_to_batch(row) for row in rows]

    def update_status(self, batch_id: int, status: InputBatchStatus) -> InputBatch:
        self.connection.execute(
            """
            UPDATE input_batches
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status.value, batch_id),
        )
        self.connection.commit()
        stored = self.get_by_id(batch_id)
        if stored is None:
            raise ValueError(f"Input batch not found: {batch_id}")
        return stored


def _row_to_batch(row: Row | None) -> InputBatch | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored input_batch row is missing timestamps")
    return InputBatch(
        id=row["id"],
        batch_name=row["batch_name"],
        schema_version=row["schema_version"],
        source_file=load_path(row["source_file"]),
        status=InputBatchStatus(row["status"]),
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["BatchRepository"]
