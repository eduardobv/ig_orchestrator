from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection, Row

from ig_orchestrator.db._mapping import load_datetime, load_path
from ig_orchestrator.db.run_repository import RunRecord
from ig_orchestrator.models import (
    DownloadFile,
    DownloadFileStatus,
    InputBatch,
    InputBatchStatus,
    MediaType,
    PublicationType,
    RunStatus,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_batch(row: Row | None) -> InputBatch | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored batch is missing timestamps")
    return InputBatch(
        id=row["id"],
        batch_name=row["batch_name"],
        schema_version=row["schema_version"],
        source_file=load_path(row["source_file"]),
        status=InputBatchStatus(row["status"]),
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_url_job(row: Row | None) -> UrlJob | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored batch URL is missing timestamps")
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


def _row_to_run(row: Row | None) -> RunRecord | None:
    if row is None:
        return None
    started_at = load_datetime(row["started_at"])
    if started_at is None:
        raise ValueError("Stored run is missing started_at")
    return RunRecord(
        id=int(row["id"]),
        status=RunStatus(row["status"]),
        started_at=started_at,
        batch_id=row["batch_id"],
        account_id=row["account_id"],
        total_urls=int(row["total_urls"] or 0),
        completed_urls=int(row["completed_urls"] or 0),
        failed_urls=int(row["failed_urls"] or 0),
        downloaded_files=int(row["downloaded_files"] or 0),
        report_path=load_path(row["report_path"]),
        finished_at=load_datetime(row["finished_at"]),
        summary=row["summary"],
    )


def _row_to_download(row: Row | None) -> DownloadFile | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored download file is missing timestamps")
    original = _join_root(row["root_path"], row["relative_path"])
    working = None
    if row["working_relative_path"]:
        working = _join_root(row["working_root_path"], row["working_relative_path"])
    status_code = str(row["status"])
    if status_code == "MOVED":
        file_status = DownloadFileStatus.MOVED_TO_WORKING_FOLDER
    elif status_code == "CLASSIFIED":
        file_status = DownloadFileStatus.CLASSIFIED_AS_POST
    else:
        file_status = DownloadFileStatus(status_code)
    return DownloadFile(
        id=row["id"],
        url_job_id=row["url_job_id"],
        original_path=original,
        working_path=working,
        final_path=None,
        media_type=MediaType(row["media_type"]),
        file_extension=row["file_extension"],
        file_size=row["file_size"],
        sha256=row["sha256"],
        status=file_status,
        created_at=created_at,
        updated_at=updated_at,
    )


def _download_status_code(status: DownloadFileStatus) -> str:
    if status is DownloadFileStatus.MOVED_TO_WORKING_FOLDER:
        return "MOVED"
    if status.value.startswith("CLASSIFIED_"):
        return "CLASSIFIED"
    if status is DownloadFileStatus.DETECTED:
        return "DETECTED"
    return "FINALIZED"


def _path_root(connection: Connection, code: str) -> str:
    row = connection.execute(
        "SELECT path FROM path_roots WHERE code = ?",
        (code,),
    ).fetchone()
    return str(row["path"]) if row is not None else ""


def _split_path(
    connection: Connection,
    path: Path,
    *,
    preferred: str,
) -> tuple[int, str]:
    row = connection.execute(
        "SELECT id, path FROM path_roots WHERE code = ?",
        (preferred,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Missing path_roots code: {preferred}")
    root = str(row["path"] or "").strip()
    relative = str(path)
    if root:
        try:
            relative = str(path.resolve().relative_to(Path(root).resolve()))
        except ValueError:
            relative = str(path)
    return int(row["id"]), relative


def _join_root(root_path: object, relative: object) -> Path:
    relative_text = str(relative)
    root_text = str(root_path or "").strip()
    if not root_text:
        return Path(relative_text)
    return Path(root_text) / relative_text

