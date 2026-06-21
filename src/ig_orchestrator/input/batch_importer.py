from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import Connection, Row

from ig_orchestrator.db import (
    AccountHistoryRepository,
    AccountRepository,
    BatchRepository,
    ConfigRepository,
    UrlJobRepository,
)
from ig_orchestrator.input.batch_json_parser import ParsedBatch, parse_batch_json
from ig_orchestrator.input.url_classifier import classify_instagram_url
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    AppConfig,
    ConfigValueType,
    InputBatch,
    InputBatchStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.settings import Settings


@dataclass(frozen=True, slots=True)
class BatchImportResult:
    batch: InputBatch
    accounts: tuple[Account, ...]
    url_jobs: tuple[UrlJob, ...]


class DuplicateBatchNameError(ValueError):
    """Raised when a new import reuses a batch_name already stored in SQLite."""


def import_batch_json(
    path: str | Path,
    connection: Connection,
    *,
    settings: Settings | None = None,
) -> BatchImportResult:
    """Parse and import a batch JSON file into SQLite."""

    return import_parsed_batch(parse_batch_json(path), connection, settings=settings)


def import_parsed_batch(
    parsed_batch: ParsedBatch,
    connection: Connection,
    *,
    settings: Settings | None = None,
) -> BatchImportResult:
    """Persist a parsed batch as batch, account and URL job rows."""

    batch = _create_unique_batch(parsed_batch, BatchRepository(connection))
    if settings is not None:
        _upsert_operational_config(ConfigRepository(connection), settings)
    account_repo = AccountRepository(connection)
    account_history_repo = AccountHistoryRepository(connection)
    url_job_repo = UrlJobRepository(connection)

    imported_accounts: list[Account] = []
    imported_jobs: list[UrlJob] = []

    for parsed_account in parsed_batch.accounts:
        account_history_repo.create_or_get(parsed_account.username)
        generated_story_url = (
            build_story_url(parsed_account.username)
            if parsed_account.download_stories
            else None
        )
        account = _get_or_create_account(
            connection,
            account_repo,
            batch_id=_required_id("batch", batch.id),
            username=parsed_account.username,
            start_now_date=parsed_account.start_now_date,
            download_stories=parsed_account.download_stories,
            generated_story_url=generated_story_url,
            working_folder=(
                settings.working_folder / parsed_account.username
                if settings is not None
                else None
            ),
        )
        imported_accounts.append(account)

        if generated_story_url is not None:
            imported_jobs.append(
                _get_or_create_url_job(
                    connection,
                    url_job_repo,
                    account_id=_required_id("account", account.id),
                    url=generated_story_url,
                    publication_type=PublicationType.STORY,
                    source=UrlSource.GENERATED_STORY,
                    max_retries=settings.max_retries if settings is not None else None,
                )
            )

        for url in parsed_account.urls:
            imported_jobs.append(
                _get_or_create_url_job(
                    connection,
                    url_job_repo,
                    account_id=_required_id("account", account.id),
                    url=url,
                    publication_type=classify_instagram_url(url),
                    source=UrlSource.INPUT_URL,
                    max_retries=settings.max_retries if settings is not None else None,
                )
            )

        for duplicate_url in parsed_account.duplicate_urls:
            original_job = _get_or_create_url_job(
                connection,
                url_job_repo,
                account_id=_required_id("account", account.id),
                url=duplicate_url.url,
                publication_type=classify_instagram_url(duplicate_url.url),
                source=UrlSource.INPUT_URL,
                max_retries=settings.max_retries if settings is not None else None,
            )
            _get_or_create_duplicate_url_job(
                connection,
                batch_id=_required_id("batch", batch.id),
                account_id=_required_id("account", account.id),
                duplicate_of_url_job_id=_required_id("url_job", original_job.id),
                url=duplicate_url.url,
                publication_type=original_job.publication_type,
                source=UrlSource.INPUT_URL,
                occurrence_index=duplicate_url.occurrence_index,
            )

    return BatchImportResult(
        batch=batch,
        accounts=tuple(imported_accounts),
        url_jobs=tuple(imported_jobs),
    )


def build_story_url(username: str) -> str:
    return f"https://www.instagram.com/stories/{username}/"


def _upsert_operational_config(
    repository: ConfigRepository,
    settings: Settings,
) -> None:
    config_values = {
        "telegram_desktop_download_folder": (
            str(settings.telegram_desktop_download_folder),
            ConfigValueType.PATH,
        ),
        "working_folder": (str(settings.working_folder), ConfigValueType.PATH),
        "reports_folder": (str(settings.reports_folder), ConfigValueType.PATH),
        "max_retries": (str(settings.max_retries), ConfigValueType.INTEGER),
        "retry_base_seconds": (
            str(settings.retry_base_seconds),
            ConfigValueType.INTEGER,
        ),
        "retry_max_seconds": (
            str(settings.retry_max_seconds),
            ConfigValueType.INTEGER,
        ),
        "download_wait_timeout_seconds": (
            str(settings.download_wait_timeout_seconds),
            ConfigValueType.INTEGER,
        ),
        "download_stable_seconds": (
            str(settings.download_stable_seconds),
            ConfigValueType.INTEGER,
        ),
    }
    for key, (value, value_type) in config_values.items():
        repository.upsert(AppConfig(key=key, value=value, value_type=value_type))


def _create_unique_batch(
    parsed_batch: ParsedBatch,
    repository: BatchRepository,
) -> InputBatch:
    existing = repository.get_by_name(parsed_batch.batch_name)
    if existing is not None:
        raise DuplicateBatchNameError(
            f"Batch name '{parsed_batch.batch_name}' already exists with id "
            f"{existing.id} and status {existing.status.value}. Use run_continue "
            "with --batch-id or --batch-name to resume it."
        )

    return repository.create(
        InputBatch(
            batch_name=parsed_batch.batch_name,
            schema_version=parsed_batch.schema_version,
            source_file=parsed_batch.source_file,
            status=InputBatchStatus.IMPORTED,
        )
    )


def _get_or_create_account(
    connection: Connection,
    repository: AccountRepository,
    *,
    batch_id: int,
    username: str,
    start_now_date,
    download_stories: bool,
    generated_story_url: str | None,
    working_folder: Path | None,
) -> Account:
    row = connection.execute(
        """
        SELECT * FROM accounts
        WHERE batch_id = ? AND username = ?
        ORDER BY id
        LIMIT 1
        """,
        (batch_id, username),
    ).fetchone()
    if row is not None:
        account_id = _row_id(row)
        connection.execute(
            """
            UPDATE accounts
            SET start_now_date = ?,
                download_stories = ?,
                generated_story_url = ?,
                working_folder = COALESCE(working_folder, ?),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                start_now_date.isoformat(),
                int(download_stories),
                generated_story_url,
                str(working_folder) if working_folder is not None else None,
                account_id,
            ),
        )
        connection.commit()
        stored = repository.get_by_id(account_id)
        if stored is None:
            raise RuntimeError(f"Account disappeared during import: {account_id}")
        return stored

    return repository.create(
        Account(
            batch_id=batch_id,
            username=username,
            start_now_date=start_now_date,
            download_stories=download_stories,
            generated_story_url=generated_story_url,
            working_folder=working_folder,
            status=AccountStatus.PENDING,
        )
    )


def _get_or_create_url_job(
    connection: Connection,
    repository: UrlJobRepository,
    *,
    account_id: int,
    url: str,
    publication_type: PublicationType,
    source: UrlSource,
    max_retries: int | None,
) -> UrlJob:
    row = connection.execute(
        """
        SELECT id FROM url_jobs
        WHERE account_id = ? AND url = ?
        ORDER BY id
        LIMIT 1
        """,
        (account_id, url),
    ).fetchone()
    if row is not None:
        stored = repository.get_by_id(_row_id(row))
        if stored is None:
            raise RuntimeError(f"URL job disappeared during import: {_row_id(row)}")
        return stored

    return repository.create(
        UrlJob(
            account_id=account_id,
            url=url,
            publication_type=publication_type,
            source=source,
            status=UrlJobStatus.PENDING,
            max_retries=max_retries,
        )
    )


def _get_or_create_duplicate_url_job(
    connection: Connection,
    *,
    batch_id: int,
    account_id: int,
    duplicate_of_url_job_id: int,
    url: str,
    publication_type: PublicationType,
    source: UrlSource,
    occurrence_index: int,
) -> None:
    row = connection.execute(
        """
        SELECT id FROM duplicate_url_jobs
        WHERE account_id = ?
          AND url = ?
          AND source = ?
          AND occurrence_index = ?
        ORDER BY id
        LIMIT 1
        """,
        (account_id, url, source.value, occurrence_index),
    ).fetchone()
    if row is not None:
        connection.execute(
            """
            UPDATE duplicate_url_jobs
            SET batch_id = ?,
                duplicate_of_url_job_id = ?,
                publication_type = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                batch_id,
                duplicate_of_url_job_id,
                publication_type.value,
                _row_id(row),
            ),
        )
        connection.commit()
        return

    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO duplicate_url_jobs (
            batch_id, account_id, duplicate_of_url_job_id, url,
            publication_type, source, occurrence_index, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            account_id,
            duplicate_of_url_job_id,
            url,
            publication_type.value,
            source.value,
            occurrence_index,
            now,
            now,
        ),
    )
    connection.commit()


def _required_id(entity_name: str, value: int | None) -> int:
    if value is None:
        raise RuntimeError(f"Stored {entity_name} has no id")
    return value


def _row_id(row: Row) -> int:
    return int(row["id"])


__all__ = [
    "BatchImportResult",
    "DuplicateBatchNameError",
    "build_story_url",
    "classify_instagram_url",
    "import_batch_json",
    "import_parsed_batch",
]
