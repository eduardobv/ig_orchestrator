from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO
from sqlite3 import Connection
from urllib.parse import urlparse

from ig_orchestrator.db import AccountHistoryRepository
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.input import (
    BatchCreationAccount,
    BatchCreationRequest,
    BatchCreationResult,
    create_batch,
    update_draft_batch,
)
from ig_orchestrator.models import InputBatchStatus
from ig_orchestrator.input.url_classifier import classify_instagram_url
from ig_orchestrator.settings import Settings


class BatchDraftValidationError(ValueError):
    """Raised when a GUI batch draft cannot be persisted."""


@dataclass(frozen=True, slots=True)
class AccountDraftValidation:
    username: str
    url_count: int
    duplicate_count: int
    invalid_urls: tuple[str, ...]
    publication_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NewAccountDetails:
    owner_id: str
    start_init_date: str
    destination_path: str


def save_batch_draft(
    draft: BatchDraft,
    connection: Connection,
    *,
    settings: Settings | None = None,
    batch_id: int | None = None,
) -> BatchCreationResult:
    request = validate_batch_draft(draft, allow_empty=batch_id is not None)
    if batch_id is None:
        result = create_batch(
            request,
            connection,
            settings=settings,
            status=InputBatchStatus.DRAFT,
        )
    else:
        result = update_draft_batch(
            batch_id,
            request,
            connection,
            settings=settings,
        )
    connection.execute(
        """
        UPDATE input_batches
        SET default_start_now_date = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (draft.default_start_now_date.strip(), result.batch.id),
    )
    stored_accounts = {account.username.casefold(): account for account in result.accounts}
    for account in draft.accounts:
        save_new_account_to_catalog(account, connection)
        stored = stored_accounts.get(_normalize_username(account.username).casefold())
        if stored is None or stored.id is None:
            continue
        connection.execute(
            """
            UPDATE accounts
            SET is_new_account = ?,
                rename_owner_id = ?,
                rename_start_init_date = ?,
                rename_destination_path = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                int(account.is_new_account),
                account.owner_id.strip() if account.is_new_account else None,
                account.start_init_date.strip() if account.is_new_account else None,
                account.destination_path.strip() if account.is_new_account else None,
                stored.id,
            ),
        )
    connection.commit()
    return result


def save_new_account_to_catalog(
    account: AccountDraft,
    connection: Connection,
) -> None:
    """Persist a checked new account in the global catalog immediately."""
    if not account.is_new_account:
        return
    username = _normalize_username(account.username)
    if not username:
        raise BatchDraftValidationError("username must not be blank")
    details = validate_new_account_details(account)
    AccountHistoryRepository(connection).update_rename_metadata(
        username,
        owner_id=details.owner_id,
        destination_path=details.destination_path,
        start_init_date=details.start_init_date,
    )


def validate_batch_draft(
    draft: BatchDraft,
    *,
    allow_empty: bool = False,
) -> BatchCreationRequest:
    batch_name = draft.batch_name.strip()
    if not batch_name:
        raise BatchDraftValidationError("Batch name must not be blank")

    default_date = _parse_date(draft.default_start_now_date, "default start date")
    if not draft.accounts and not allow_empty:
        raise BatchDraftValidationError("Batch must contain at least one account")

    accounts = []
    for index, account in enumerate(draft.accounts, start=1):
        accounts.append(_validate_account(account, index, default_date))

    return BatchCreationRequest(
        schema_version=draft.schema_version.strip() or "1.0",
        batch_name=batch_name,
        source_file=None,
        accounts=tuple(accounts),
    )


def inspect_account_draft(
    account: AccountDraft,
    *,
    default_start_now_date: str,
) -> AccountDraftValidation:
    default_date = _parse_date(default_start_now_date, "default start date")
    username = _normalize_username(account.username)
    urls, duplicates = _normalized_urls(account.urls)
    invalid_urls: list[str] = []
    publication_types: set[str] = set()
    for url in urls:
        try:
            publication_types.add(classify_instagram_url(url).value)
            _validate_instagram_domain(url)
        except ValueError:
            invalid_urls.append(url)

    return AccountDraftValidation(
        username=username,
        url_count=len(urls),
        duplicate_count=len(duplicates),
        invalid_urls=tuple(invalid_urls),
        publication_types=tuple(sorted(publication_types)),
    )


def _validate_account(
    account: AccountDraft,
    index: int,
    default_date: date,
) -> BatchCreationAccount:
    context = f"account #{index}"
    username = _normalize_username(account.username)
    if not username:
        raise BatchDraftValidationError(f"{context}: username must not be blank")

    if account.is_new_account:
        try:
            validate_new_account_details(account)
        except BatchDraftValidationError as exc:
            raise BatchDraftValidationError(f"{context}: {exc}") from exc

    start_now_date = (
        _parse_date(account.start_now_date, f"{context} start date")
        if account.start_now_date.strip()
        else default_date
    )
    urls, _duplicates = _normalized_urls(account.urls)
    for url in urls:
        try:
            _validate_instagram_domain(url)
            classify_instagram_url(url)
        except ValueError as exc:
            raise BatchDraftValidationError(f"{context}: invalid URL {url}") from exc

    if not account.download_stories and not urls:
        raise BatchDraftValidationError(
            f"{context}: enable stories or add at least one URL"
        )

    return BatchCreationAccount(
        username=username,
        start_now_date=start_now_date,
        download_stories=account.download_stories,
        urls=tuple(urls),
    )


def validate_new_account_details(account: AccountDraft) -> NewAccountDetails:
    owner_id = account.owner_id.strip()
    if not owner_id:
        raise BatchDraftValidationError("ownerId is required for a new account")

    start_init_date = account.start_init_date.strip()
    if not start_init_date:
        raise BatchDraftValidationError("startInitDate is required for a new account")
    _parse_date(start_init_date, "startInitDate")

    destination_path = account.destination_path.strip()
    if not destination_path:
        raise BatchDraftValidationError("path is required for a new account")

    return NewAccountDetails(
        owner_id=owner_id,
        start_init_date=start_init_date,
        destination_path=destination_path,
    )


def _normalize_username(value: str) -> str:
    return value.strip().lstrip("@").strip()


def _normalized_urls(values: list[str]) -> tuple[list[str], list[str]]:
    urls: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for raw_url in _parse_url_lines(values):
        url = raw_url.strip()
        if not url:
            continue
        identity = _url_identity(url)
        if identity in seen:
            duplicates.append(url)
            continue
        urls.append(url)
        seen.add(identity)
    return urls, duplicates


def normalize_url_lines(values: list[str]) -> list[str]:
    parsed_urls: list[str] = []
    seen: set[str] = set()
    for value in _parse_url_lines(values):
        identity = _url_identity(value)
        if identity not in seen:
            parsed_urls.append(value)
            seen.add(identity)
    return parsed_urls


def _url_identity(url: str) -> str:
    """Return a stable identity for equivalent Instagram publication URLs."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        (hostname == "instagram.com" or hostname.endswith(".instagram.com"))
        and len(path_parts) >= 2
        and path_parts[0].lower() in {"p", "reel"}
    ):
        return f"instagram-publication:{path_parts[1]}"
    return url


def _parse_url_lines(values: list[str]) -> list[str]:
    text = "\n".join(values)
    parsed_urls: list[str] = []
    for row in csv.reader(StringIO(text), skipinitialspace=True):
        for raw_value in row:
            value = raw_value.strip().strip('"').strip("'").strip()
            if value.endswith(","):
                value = value[:-1].strip()
            if value:
                parsed_urls.append(value)
    return parsed_urls


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise BatchDraftValidationError(
            f"{label} must use YYYY-MM-DD format"
        ) from exc


def _validate_instagram_domain(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname != "instagram.com" and not hostname.endswith(".instagram.com"):
        raise ValueError("URL must use an Instagram domain")


__all__ = [
    "AccountDraftValidation",
    "BatchDraftValidationError",
    "NewAccountDetails",
    "inspect_account_draft",
    "normalize_url_lines",
    "save_new_account_to_catalog",
    "save_batch_draft",
    "validate_new_account_details",
    "validate_batch_draft",
]
