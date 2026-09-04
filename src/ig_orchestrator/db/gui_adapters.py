from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from sqlite3 import Connection, Row

from ig_orchestrator.db.account_repository import AccountRepository
from ig_orchestrator.db.batch_repository import BatchRepository
from ig_orchestrator.db.download_repository import DownloadRepository
from ig_orchestrator.db.lookups import LookupCache
from ig_orchestrator.db.run_repository import RunRecord, RunRepository
from ig_orchestrator.db.url_job_repository import UrlJobRepository
from ig_orchestrator.db._mapping import dump_datetime, dump_path, load_datetime, load_path
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class GuiAccountRepository(AccountRepository):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create(self, account: Account) -> Account:
        from ig_orchestrator.db.account_history_repository import (
            AccountHistoryRepository,
        )

        if account.batch_id is None:
            raise ValueError("Account.batch_id is required")
        catalog = AccountHistoryRepository(self.connection).create_or_get(
            account.username
        )
        if catalog.id is None:
            raise RuntimeError("Catalog account has no id")
        pending_id = self._lookups.id_for("batch_account_statuses", account.status.value)
        sort_order = self.connection.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0) + 1
            FROM batch_accounts
            WHERE batch_id = ?
            """,
            (account.batch_id,),
        ).fetchone()[0]
        working_rel = account.username
        cursor = self.connection.execute(
            """
            INSERT INTO batch_accounts (
                batch_id, catalog_account_id, download_stories,
                working_folder_rel, status_id, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account.batch_id,
                catalog.id,
                int(account.download_stories),
                working_rel,
                pending_id,
                int(sort_order),
                dump_datetime(account.created_at),
                dump_datetime(account.updated_at),
            ),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Batch account was not stored")
        return stored

    def get_by_id(self, account_id: int) -> Account | None:
        row = self.connection.execute(
            _ACCOUNT_SELECT + " WHERE ba.id = ?",
            (account_id,),
        ).fetchone()
        return self._row_to_account(row)

    def get_by_username(self, username: str) -> Account | None:
        row = self.connection.execute(
            _ACCOUNT_SELECT
            + " WHERE ca.username = ? COLLATE NOCASE ORDER BY ba.id DESC LIMIT 1",
            (username,),
        ).fetchone()
        return self._row_to_account(row)

    def list_by_batch(self, batch_id: int) -> list[Account]:
        rows = self.connection.execute(
            _ACCOUNT_SELECT + " WHERE ba.batch_id = ? ORDER BY ba.sort_order, ba.id",
            (batch_id,),
        ).fetchall()
        return [account for row in rows if (account := self._row_to_account(row))]

    def list_by_status(self, status: AccountStatus) -> list[Account]:
        status_id = self._lookups.id_for("batch_account_statuses", status.value)
        rows = self.connection.execute(
            _ACCOUNT_SELECT + " WHERE ba.status_id = ? ORDER BY ba.id",
            (status_id,),
        ).fetchall()
        return [account for row in rows if (account := self._row_to_account(row))]

    def update_status(self, account_id: int, status: AccountStatus) -> Account:
        status_id = self._lookups.id_for("batch_account_statuses", status.value)
        self.connection.execute(
            """
            UPDATE batch_accounts
            SET status_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_id, account_id),
        )
        self.connection.commit()
        stored = self.get_by_id(account_id)
        if stored is None:
            raise ValueError(f"Account not found: {account_id}")
        return stored

    def _row_to_account(self, row: Row | None) -> Account | None:
        if row is None:
            return None
        created_at = load_datetime(row["created_at"])
        updated_at = load_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("Stored batch account is missing timestamps")
        username = str(row["username"])
        download_stories = bool(row["download_stories"])
        working_rel = row["working_folder_rel"]
        working_root = _path_root(self.connection, "WORKING")
        working_folder = None
        if working_rel:
            working_folder = (
                Path(working_root) / str(working_rel)
                if working_root
                else Path(str(working_rel))
            )
        return Account(
            id=row["id"],
            batch_id=row["batch_id"],
            username=username,
            start_now_date=date.fromisoformat(str(row["start_date"])),
            download_stories=download_stories,
            generated_story_url=(
                f"https://www.instagram.com/stories/{username}/"
                if download_stories
                else None
            ),
            working_folder=working_folder,
            status=AccountStatus(str(row["status"])),
            created_at=created_at,
            updated_at=updated_at,
        )


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

_ACCOUNT_SELECT = """
SELECT
    ba.id,
    ba.batch_id,
    ca.username,
    b.start_date,
    ba.download_stories,
    ba.working_folder_rel,
    bas.code AS status,
    ba.created_at,
    ba.updated_at
FROM batch_accounts ba
JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
JOIN batches b ON b.id = ba.batch_id
JOIN batch_account_statuses bas ON bas.id = ba.status_id
"""

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


__all__ = [
    "GuiAccountRepository",
    "GuiBatchRepository",
    "GuiDownloadRepository",
    "GuiRunRepository",
    "GuiUrlJobRepository",
]
