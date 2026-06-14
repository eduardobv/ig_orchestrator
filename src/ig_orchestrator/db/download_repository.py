from __future__ import annotations

from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import (
    dump_datetime,
    dump_path,
    load_datetime,
    load_path,
)
from ig_orchestrator.models import DownloadFile, DownloadFileStatus, MediaType


class DownloadRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, download_file: DownloadFile) -> DownloadFile:
        cursor = self.connection.execute(
            """
            INSERT INTO download_files (
                url_job_id, original_path, working_path, final_path, media_type,
                file_extension, file_size, sha256, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                download_file.url_job_id,
                dump_path(download_file.original_path),
                dump_path(download_file.working_path),
                dump_path(download_file.final_path),
                download_file.media_type.value,
                download_file.file_extension,
                download_file.file_size,
                download_file.sha256,
                download_file.status.value,
                dump_datetime(download_file.created_at),
                dump_datetime(download_file.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Download file was not stored")
        return stored

    def get_by_id(self, file_id: int) -> DownloadFile | None:
        row = self.connection.execute(
            "SELECT * FROM download_files WHERE id = ?",
            (file_id,),
        ).fetchone()
        return _row_to_download_file(row)

    def list_by_url_job(self, url_job_id: int) -> list[DownloadFile]:
        rows = self.connection.execute(
            "SELECT * FROM download_files WHERE url_job_id = ? ORDER BY id",
            (url_job_id,),
        ).fetchall()
        return [_row_to_download_file(row) for row in rows]

    def list_by_status(self, status: DownloadFileStatus) -> list[DownloadFile]:
        rows = self.connection.execute(
            "SELECT * FROM download_files WHERE status = ? ORDER BY id",
            (status.value,),
        ).fetchall()
        return [_row_to_download_file(row) for row in rows]

    def update_status(
        self, file_id: int, status: DownloadFileStatus
    ) -> DownloadFile:
        self.connection.execute(
            """
            UPDATE download_files
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status.value, file_id),
        )
        self.connection.commit()
        stored = self.get_by_id(file_id)
        if stored is None:
            raise ValueError(f"Download file not found: {file_id}")
        return stored


def _row_to_download_file(row: Row | None) -> DownloadFile | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored download_file row is missing timestamps")
    original_path = load_path(row["original_path"])
    if original_path is None:
        raise ValueError("Stored download_file row is missing original_path")
    return DownloadFile(
        id=row["id"],
        url_job_id=row["url_job_id"],
        original_path=original_path,
        working_path=load_path(row["working_path"]),
        final_path=load_path(row["final_path"]),
        media_type=MediaType(row["media_type"]),
        file_extension=row["file_extension"],
        file_size=row["file_size"],
        sha256=row["sha256"],
        status=DownloadFileStatus(row["status"]),
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["DownloadRepository"]
