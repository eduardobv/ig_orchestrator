from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import dump_datetime, dump_path, load_datetime, load_path
from ig_orchestrator.models import RunStatus, RunSummary


@dataclass(slots=True)
class RunRecord:
    id: int
    status: RunStatus
    started_at: datetime
    batch_id: int | None = None
    account_id: int | None = None
    total_urls: int = 0
    completed_urls: int = 0
    failed_urls: int = 0
    downloaded_files: int = 0
    report_path: Path | None = None
    finished_at: datetime | None = None
    summary: str | None = None


class RunRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

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
        cursor = self.connection.execute(
            """
            INSERT INTO runs (
                batch_id, account_id, status, total_urls, completed_urls,
                failed_urls, downloaded_files, report_path, started_at,
                finished_at, summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                account_id,
                summary.status.value,
                summary.total_urls,
                summary.completed_urls,
                summary.failed_urls,
                summary.downloaded_files,
                dump_path(report_path),
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
            "SELECT * FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return _row_to_run(row)

    def list_by_status(self, status: RunStatus) -> list[RunRecord]:
        rows = self.connection.execute(
            "SELECT * FROM runs WHERE status = ? ORDER BY id",
            (status.value,),
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
        self.connection.execute(
            """
            UPDATE runs
            SET status = ?,
                total_urls = ?,
                completed_urls = ?,
                failed_urls = ?,
                downloaded_files = ?,
                report_path = COALESCE(?, report_path),
                finished_at = COALESCE(?, finished_at),
                summary = ?
            WHERE id = ?
            """,
            (
                summary.status.value,
                summary.total_urls,
                summary.completed_urls,
                summary.failed_urls,
                summary.downloaded_files,
                dump_path(report_path),
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

    def update_status(
        self,
        run_id: int,
        status: RunStatus,
        *,
        finished_at: datetime | None = None,
    ) -> RunRecord:
        self.connection.execute(
            """
            UPDATE runs
            SET status = ?,
                finished_at = COALESCE(?, finished_at)
            WHERE id = ?
            """,
            (status.value, dump_datetime(finished_at), run_id),
        )
        self.connection.commit()
        stored = self.get_by_id(run_id)
        if stored is None:
            raise ValueError(f"Run not found: {run_id}")
        return stored


def _row_to_run(row: Row | None) -> RunRecord | None:
    if row is None:
        return None
    started_at = load_datetime(row["started_at"])
    if started_at is None:
        raise ValueError("Stored run row is missing started_at")
    return RunRecord(
        id=row["id"],
        batch_id=row["batch_id"],
        account_id=row["account_id"],
        status=RunStatus(row["status"]),
        total_urls=row["total_urls"],
        completed_urls=row["completed_urls"],
        failed_urls=row["failed_urls"],
        downloaded_files=row["downloaded_files"],
        report_path=load_path(row["report_path"]),
        started_at=started_at,
        finished_at=load_datetime(row["finished_at"]),
        summary=row["summary"],
    )


__all__ = ["RunRecord", "RunRepository"]
