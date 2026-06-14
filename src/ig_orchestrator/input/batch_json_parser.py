from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BatchJsonParserError(ValueError):
    """Raised when the batch JSON does not match the expected contract."""


@dataclass(frozen=True, slots=True)
class ParsedBatchAccount:
    username: str
    start_now_date: date
    download_stories: bool
    urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedBatch:
    schema_version: str
    batch_name: str
    accounts: tuple[ParsedBatchAccount, ...]
    source_file: Path


def parse_batch_json(path: str | Path) -> ParsedBatch:
    source_file = Path(path)
    try:
        raw_content = source_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise BatchJsonParserError(f"Cannot read batch JSON '{source_file}': {exc}") from exc

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise BatchJsonParserError(
            f"Invalid JSON in '{source_file}' at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise BatchJsonParserError("Batch JSON root must be an object")

    schema_version = _required_non_blank_string(payload, "schema_version", "batch")
    batch_name = _required_non_blank_string(payload, "batch_name", "batch")
    defaults = _optional_object(payload.get("defaults"), "batch.defaults")
    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list):
        raise BatchJsonParserError("batch.accounts must be a list")
    if not raw_accounts:
        raise BatchJsonParserError("batch.accounts must contain at least one account")

    parsed_accounts = tuple(
        _parse_account(account, index, defaults)
        for index, account in enumerate(raw_accounts, start=1)
    )

    return ParsedBatch(
        schema_version=schema_version,
        batch_name=batch_name,
        accounts=parsed_accounts,
        source_file=source_file,
    )


def _parse_account(
    raw_account: Any, index: int, defaults: dict[str, Any]
) -> ParsedBatchAccount:
    context = f"accounts[{index}]"
    if not isinstance(raw_account, dict):
        raise BatchJsonParserError(f"{context} must be an object")

    username = _required_non_blank_string(raw_account, "username", context)
    start_now_date = _parse_inherited_date(
        raw_account, defaults, "start_now_date", context
    )
    download_stories = _parse_inherited_bool(
        raw_account,
        defaults,
        "download_stories",
        context,
        default=False,
    )
    urls = _parse_urls(raw_account.get("urls", []), context, username)

    if not urls and not download_stories:
        raise BatchJsonParserError(
            f"{context}.urls must contain at least one URL when download_stories is false"
        )

    return ParsedBatchAccount(
        username=username,
        start_now_date=start_now_date,
        download_stories=download_stories,
        urls=tuple(urls),
    )


def _required_non_blank_string(
    payload: dict[str, Any], field_name: str, context: str
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise BatchJsonParserError(f"{context}.{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise BatchJsonParserError(f"{context}.{field_name} must not be blank")
    return normalized


def _optional_object(value: Any, context: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BatchJsonParserError(f"{context} must be an object")
    return value


def _parse_inherited_date(
    payload: dict[str, Any],
    defaults: dict[str, Any],
    field_name: str,
    context: str,
) -> date:
    value = payload.get(field_name, defaults.get(field_name))
    if not isinstance(value, str):
        raise BatchJsonParserError(
            f"{context}.{field_name} must be a date string in YYYY-MM-DD format"
        )
    normalized = value.strip()
    if not DATE_PATTERN.fullmatch(normalized):
        raise BatchJsonParserError(
            f"{context}.{field_name} must use YYYY-MM-DD format"
        )
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise BatchJsonParserError(
            f"{context}.{field_name} must use YYYY-MM-DD format"
        ) from exc


def _parse_inherited_bool(
    payload: dict[str, Any],
    defaults: dict[str, Any],
    field_name: str,
    context: str,
    *,
    default: bool,
) -> bool:
    value = payload.get(field_name, defaults.get(field_name, default))
    if not isinstance(value, bool):
        raise BatchJsonParserError(f"{context}.{field_name} must be a boolean")
    return value


def _parse_urls(value: Any, context: str, username: str) -> list[str]:
    if not isinstance(value, list):
        raise BatchJsonParserError(f"{context}.urls must be a list")

    urls: list[str] = []
    seen: set[str] = set()
    for index, raw_url in enumerate(value, start=1):
        url_context = f"{context}.urls[{index}]"
        if not isinstance(raw_url, str):
            raise BatchJsonParserError(f"{url_context} must be a string")
        normalized = raw_url.strip()
        if not normalized:
            raise BatchJsonParserError(f"{url_context} must not be blank")
        _validate_instagram_url(normalized, url_context, username)
        if normalized not in seen:
            urls.append(normalized)
            seen.add(normalized)
    return urls


def _validate_instagram_url(url: str, context: str, username: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise BatchJsonParserError(
            f"{context} for account '{username}' must use http or https"
        )

    hostname = (parsed.hostname or "").lower()
    if hostname != "instagram.com" and not hostname.endswith(".instagram.com"):
        raise BatchJsonParserError(
            f"{context} for account '{username}' must use an Instagram domain"
        )
