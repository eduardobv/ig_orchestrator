from __future__ import annotations

from datetime import date, datetime, timezone
from sqlite3 import Connection

from ig_orchestrator.db.lookups import LookupCache
from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.input.batch_creation_service import (
    BatchCreationRequest,
    BatchCreationResult,
    DuplicateBatchNameError,
    build_story_url,
    _ordered_accounts_for_creation,
)
from ig_orchestrator.input.url_classifier import classify_instagram_url
from ig_orchestrator.models import (
    InputBatchStatus,
    PublicationType,
    UrlJob,
)
from ig_orchestrator.settings import Settings


def create_gui_batch(
    request: BatchCreationRequest,
    connection: Connection,
    *,
    settings: Settings | None = None,
    status: InputBatchStatus = InputBatchStatus.IMPORTED,
    batch_id: int | None = None,
) -> BatchCreationResult:
    """Insert a GUI batch in a single transaction using executemany for URLs."""

    if not is_gui_schema(connection):
        raise RuntimeError("create_gui_batch requires a v2 GUI database")

    lookups = LookupCache(connection)
    now = datetime.now(timezone.utc).isoformat()
    start_date = _start_date(request)
    if settings is not None:
        _upsert_path_roots(connection, settings, now)

    if batch_id is None:
        if connection.execute(
            "SELECT id FROM batches WHERE name = ? LIMIT 1",
            (request.batch_name,),
        ).fetchone() is not None:
            raise DuplicateBatchNameError(
                f"Batch name '{request.batch_name}' already exists."
            )
        cursor = connection.execute(
            """
            INSERT INTO batches (
                name, schema_version, status_id, start_date, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.batch_name,
                request.schema_version,
                lookups.id_for("batch_statuses", status.value),
                start_date,
                now,
                now,
            ),
        )
        batch_id = int(cursor.lastrowid)
    else:
        connection.execute(
            """
            UPDATE batches
            SET name = ?, schema_version = ?, status_id = ?, start_date = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                request.batch_name,
                request.schema_version,
                lookups.id_for("batch_statuses", status.value),
                start_date,
                now,
                batch_id,
            ),
        )

    pending_account = lookups.id_for("batch_account_statuses", "PENDING")
    pending_url = lookups.id_for("batch_url_statuses", "PENDING")
    input_source = lookups.id_for("url_sources", "INPUT_URL")
    generated_source = lookups.id_for("url_sources", "GENERATED_STORY")
    enabled_catalog = lookups.id_for("catalog_account_statuses", "ENABLED")
    url_rows: list[tuple[object, ...]] = []
    duplicate_rows: list[tuple[object, ...]] = []
    created_account_ids: list[int] = []

    for sort_order, account_request in enumerate(
        _ordered_accounts_for_creation(request), start=1
    ):
        catalog_id = _ensure_catalog_id(
            connection,
            username=account_request.username,
            enabled_status_id=enabled_catalog,
            now=now,
        )
        working_rel = account_request.username
        cursor = connection.execute(
            """
            INSERT INTO batch_accounts (
                batch_id, catalog_account_id, download_stories,
                working_folder_rel, status_id, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                catalog_id,
                int(account_request.download_stories),
                working_rel,
                pending_account,
                sort_order,
                now,
                now,
            ),
        )
        account_id = int(cursor.lastrowid)
        created_account_ids.append(account_id)
        max_retries = settings.max_retries if settings is not None else None
        if account_request.download_stories:
            story_url = build_story_url(account_request.username)
            url_rows.append(
                _url_row(
                    lookups,
                    account_id=account_id,
                    url=story_url,
                    publication_type=PublicationType.STORY,
                    source_id=generated_source,
                    status_id=pending_url,
                    max_retries=max_retries,
                    now=now,
                )
            )
        for url in account_request.urls:
            url_rows.append(
                _url_row(
                    lookups,
                    account_id=account_id,
                    url=url,
                    publication_type=classify_instagram_url(url),
                    source_id=input_source,
                    status_id=pending_url,
                    max_retries=max_retries,
                    now=now,
                )
            )
        for duplicate in account_request.duplicate_urls:
            duplicate_rows.append(
                (
                    batch_id,
                    account_id,
                    duplicate.url,
                    lookups.id_for(
                        "publication_types",
                        classify_instagram_url(duplicate.url).value,
                    ),
                    input_source,
                    duplicate.occurrence_index,
                    now,
                    now,
                )
            )

    if url_rows:
        connection.executemany(
            """
            INSERT INTO batch_urls (
                batch_account_id, batch_run_id, url, publication_type_id,
                source_id, status_id, retries, max_retries, last_error_id,
                last_error_text, non_retryable, sent_message_id, started_at,
                finished_at, next_retry_at, created_at, updated_at
            )
            VALUES (?, NULL, ?, ?, ?, ?, 0, ?, NULL, NULL, 0, NULL, NULL, NULL, NULL, ?, ?)
            """,
            url_rows,
        )
    if duplicate_rows:
        connection.executemany(
            """
            INSERT INTO duplicate_urls (
                batch_id, batch_account_id, duplicate_of_url_id, url,
                publication_type_id, source_id, occurrence_index,
                created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
            """,
            duplicate_rows,
        )
    connection.commit()

    from ig_orchestrator.db import (
        AccountRepository,
        BatchRepository,
        UrlJobRepository,
    )

    batch = BatchRepository(connection).get_by_id(batch_id)
    if batch is None:
        raise RuntimeError("GUI batch disappeared after insert")
    accounts = AccountRepository(connection).list_by_batch(batch_id)
    jobs: list[UrlJob] = []
    for account in accounts:
        if account.id is None:
            continue
        jobs.extend(UrlJobRepository(connection).list_by_account(account.id))
    return BatchCreationResult(
        batch=batch,
        accounts=tuple(accounts),
        url_jobs=tuple(jobs),
    )


def replace_gui_draft_batch(
    batch_id: int,
    request: BatchCreationRequest,
    connection: Connection,
    *,
    settings: Settings | None = None,
) -> BatchCreationResult:
    from ig_orchestrator.db import BatchRepository

    batch = BatchRepository(connection).get_by_id(batch_id)
    if batch is None:
        raise ValueError(f"Input batch not found: {batch_id}")
    if batch.status is not InputBatchStatus.DRAFT:
        raise ValueError("Only saved DRAFT batches can be modified")
    if connection.execute(
        "SELECT 1 FROM batch_runs WHERE batch_id = ? LIMIT 1", (batch_id,)
    ).fetchone() is not None:
        raise ValueError("A batch that has already been executed cannot be modified")
    duplicate = connection.execute(
        "SELECT id FROM batches WHERE name = ? AND id <> ? LIMIT 1",
        (request.batch_name, batch_id),
    ).fetchone()
    if duplicate is not None:
        raise DuplicateBatchNameError(
            f"Batch name '{request.batch_name}' already exists with id {duplicate['id']}."
        )
    account_ids = [
        int(row["id"])
        for row in connection.execute(
            "SELECT id FROM batch_accounts WHERE batch_id = ?", (batch_id,)
        ).fetchall()
    ]
    for account_id in account_ids:
        connection.execute(
            "DELETE FROM duplicate_urls WHERE batch_account_id = ?", (account_id,)
        )
        connection.execute(
            "DELETE FROM batch_urls WHERE batch_account_id = ?", (account_id,)
        )
    connection.execute("DELETE FROM batch_accounts WHERE batch_id = ?", (batch_id,))
    return create_gui_batch(
        request,
        connection,
        settings=settings,
        status=InputBatchStatus.DRAFT,
        batch_id=batch_id,
    )


def _start_date(request: BatchCreationRequest) -> str:
    if request.accounts:
        return request.accounts[0].start_now_date.isoformat()
    return date.today().isoformat()


def _ensure_catalog_id(
    connection: Connection,
    *,
    username: str,
    enabled_status_id: int,
    now: str,
) -> int:
    row = connection.execute(
        """
        SELECT id FROM catalog_accounts
        WHERE username = ? COLLATE NOCASE
        ORDER BY id
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO catalog_accounts (
            username, status_id, is_favorite, created_at, updated_at
        )
        VALUES (?, ?, 0, ?, ?)
        """,
        (username, enabled_status_id, now, now),
    )
    return int(cursor.lastrowid)


def _url_row(
    lookups: LookupCache,
    *,
    account_id: int,
    url: str,
    publication_type: PublicationType,
    source_id: int,
    status_id: int,
    max_retries: int | None,
    now: str,
) -> tuple[object, ...]:
    return (
        account_id,
        url,
        lookups.id_for("publication_types", publication_type.value),
        source_id,
        status_id,
        max_retries,
        now,
        now,
    )


def _upsert_path_roots(
    connection: Connection, settings: Settings, now: str
) -> None:
    values = {
        "TELEGRAM_DESKTOP": str(settings.telegram_desktop_download_folder),
        "WORKING": str(settings.working_folder),
        "FINAL_BASE": (
            str(settings.final_base_folder) if settings.final_base_folder else ""
        ),
    }
    for code, path in values.items():
        connection.execute(
            "UPDATE path_roots SET path = ?, updated_at = ? WHERE code = ?",
            (path, now, code),
        )


__all__ = ["create_gui_batch", "replace_gui_draft_batch"]
