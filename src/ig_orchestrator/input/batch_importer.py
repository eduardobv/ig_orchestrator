from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.input.batch_creation_service import (
    BatchCreationAccount,
    BatchCreationDuplicateUrl,
    BatchCreationRequest,
    BatchCreationResult,
    DuplicateBatchNameError,
    build_story_url,
    create_batch,
)
from ig_orchestrator.input.batch_json_parser import (
    ParsedBatch,
    parse_batch_json,
)
from ig_orchestrator.input.url_classifier import classify_instagram_url
from ig_orchestrator.settings import Settings

BatchImportResult = BatchCreationResult


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

    request = BatchCreationRequest(
        schema_version=parsed_batch.schema_version,
        batch_name=parsed_batch.batch_name,
        source_file=parsed_batch.source_file,
        accounts=tuple(
            BatchCreationAccount(
                username=account.username,
                start_now_date=account.start_now_date,
                download_stories=account.download_stories,
                urls=account.urls,
                duplicate_urls=tuple(
                    BatchCreationDuplicateUrl(
                        url=duplicate.url,
                        occurrence_index=duplicate.occurrence_index,
                    )
                    for duplicate in account.duplicate_urls
                ),
            )
            for account in parsed_batch.accounts
        ),
    )
    return create_batch(request, connection, settings=settings)


__all__ = [
    "BatchImportResult",
    "DuplicateBatchNameError",
    "build_story_url",
    "classify_instagram_url",
    "import_batch_json",
    "import_parsed_batch",
]
