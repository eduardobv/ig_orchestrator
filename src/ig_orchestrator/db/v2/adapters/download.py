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

_DOWNLOAD_SELECT = """
SELECT
    df.id,
    df.batch_url_id AS url_job_id,
    pr.path AS root_path,
    df.relative_path,
    df.working_relative_path,
    wr.path AS working_root_path,
    mt.code AS media_type,
    df.extension AS file_extension,
    df.file_size,
    df.sha256,
    dfs.code AS status,
    df.created_at,
    COALESCE(df.updated_at, df.created_at) AS updated_at
FROM downloaded_files df
JOIN path_roots pr ON pr.id = df.root_id
JOIN media_types mt ON mt.id = df.media_type_id
JOIN downloaded_file_statuses dfs ON dfs.id = df.status_id
LEFT JOIN path_roots wr ON wr.code = 'WORKING'
"""


class GuiDownloadRepository(DownloadRepository):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create(self, download_file: DownloadFile) -> DownloadFile:
        root_id, relative = _split_path(
            self.connection, download_file.original_path, preferred="TELEGRAM_DESKTOP"
        )
        working_rel = None
        if download_file.working_path is not None:
            _, working_rel = _split_path(
                self.connection, download_file.working_path, preferred="WORKING"
            )
        status_id = self._lookups.id_for(
            "downloaded_file_statuses", _download_status_code(download_file.status)
        )
        media_id = self._lookups.id_for("media_types", download_file.media_type.value)
        now = _now()
        cursor = self.connection.execute(
            """
            INSERT INTO downloaded_files (
                batch_url_id, root_id, relative_path, working_relative_path,
                media_type_id, extension, file_size, sha256, status_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                download_file.url_job_id,
                root_id,
                relative,
                working_rel,
                media_id,
                download_file.file_extension,
                download_file.file_size,
                download_file.sha256,
                status_id,
                dump_datetime(download_file.created_at) or now,
                dump_datetime(download_file.updated_at) or now,
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Download file was not stored")
        return stored

    def get_by_id(self, file_id: int) -> DownloadFile | None:
        row = self.connection.execute(
            _DOWNLOAD_SELECT + " WHERE df.id = ?",
            (file_id,),
        ).fetchone()
        return _row_to_download(row)

    def list_by_url_job(self, url_job_id: int) -> list[DownloadFile]:
        rows = self.connection.execute(
            _DOWNLOAD_SELECT + " WHERE df.batch_url_id = ? ORDER BY df.id",
            (url_job_id,),
        ).fetchall()
        return [_row_to_download(row) for row in rows]

    def list_by_status(self, status: DownloadFileStatus) -> list[DownloadFile]:
        status_id = self._lookups.id_for(
            "downloaded_file_statuses", _download_status_code(status)
        )
        rows = self.connection.execute(
            _DOWNLOAD_SELECT + " WHERE df.status_id = ? ORDER BY df.id",
            (status_id,),
        ).fetchall()
        return [_row_to_download(row) for row in rows]

    def update_status(self, file_id: int, status: DownloadFileStatus) -> DownloadFile:
        status_id = self._lookups.id_for(
            "downloaded_file_statuses", _download_status_code(status)
        )
        self.connection.execute(
            """
            UPDATE downloaded_files
            SET status_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_id, file_id),
        )
        self.connection.commit()
        stored = self.get_by_id(file_id)
        if stored is None:
            raise ValueError(f"Download file not found: {file_id}")
        return stored

    def update(self, download_file: DownloadFile) -> DownloadFile:
        if download_file.id is None:
            raise ValueError("DownloadFile.id is required for update")
        working_rel = None
        if download_file.working_path is not None:
            _, working_rel = _split_path(
                self.connection, download_file.working_path, preferred="WORKING"
            )
        status_id = self._lookups.id_for(
            "downloaded_file_statuses", _download_status_code(download_file.status)
        )
        media_id = self._lookups.id_for("media_types", download_file.media_type.value)
        self.connection.execute(
            """
            UPDATE downloaded_files
            SET working_relative_path = ?,
                media_type_id = ?,
                extension = ?,
                file_size = ?,
                sha256 = ?,
                status_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                working_rel,
                media_id,
                download_file.file_extension,
                download_file.file_size,
                download_file.sha256,
                status_id,
                dump_datetime(download_file.updated_at),
                download_file.id,
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(download_file.id)
        if stored is None:
            raise ValueError(f"Download file not found: {download_file.id}")
        return stored

