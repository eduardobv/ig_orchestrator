from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO
from sqlite3 import Connection
from urllib.parse import urlparse

from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.input import (
    BatchCreationAccount,
    BatchCreationRequest,
    BatchCreationResult,
    create_batch,
)
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


def save_batch_draft(
    draft: BatchDraft,
    connection: Connection,
    *,
    settings: Settings | None = None,
) -> BatchCreationResult:
    request = validate_batch_draft(draft)
    return create_batch(request, connection, settings=settings)


def validate_batch_draft(draft: BatchDraft) -> BatchCreationRequest:
    batch_name = draft.batch_name.strip()
    if not batch_name:
        raise BatchDraftValidationError("Batch name must not be blank")

    default_date = _parse_date(draft.default_start_now_date, "default start date")
    if not draft.accounts:
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

    start_now_date = (
        _parse_date(account.start_now_date, f"{context} start date")
        if account.start_now_date.strip()
        else default_date
    )
    urls, duplicates = _normalized_urls(account.urls)
    if duplicates:
        raise BatchDraftValidationError(
            f"{context}: duplicated URLs are not allowed before saving"
        )
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


def _normalize_username(value: str) -> str:
    return value.strip().lstrip("@").strip()


def _normalized_urls(values: list[str]) -> tuple[list[str], list[str]]:
    urls: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for raw_url in normalize_url_lines(values):
        url = raw_url.strip()
        if not url:
            continue
        if url in seen:
            duplicates.append(url)
            continue
        urls.append(url)
        seen.add(url)
    return urls, duplicates


def normalize_url_lines(values: list[str]) -> list[str]:
    text = "\n".join(values)
    parsed_urls: list[str] = []
    seen: set[str] = set()
    for row in csv.reader(StringIO(text), skipinitialspace=True):
        for raw_value in row:
            value = raw_value.strip().strip('"').strip("'").strip()
            if value.endswith(","):
                value = value[:-1].strip()
            if value and value not in seen:
                parsed_urls.append(value)
                seen.add(value)
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
    "inspect_account_draft",
    "normalize_url_lines",
    "save_batch_draft",
    "validate_batch_draft",
]
