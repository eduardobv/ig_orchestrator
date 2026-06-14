from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ig_orchestrator.input import BatchJsonParserError, parse_batch_json


def test_parse_valid_batch_json(tmp_path: Path) -> None:
    batch_path = _write_batch(
        tmp_path,
        {
            "schema_version": "1.0",
            "batch_name": "descargas_junio_2026",
            "defaults": {
                "download_stories": False,
                "start_now_date": "2026-06-04",
            },
            "accounts": [
                {
                    "username": " example_user ",
                    "download_stories": True,
                    "urls": [
                        " https://www.instagram.com/p/DZPjwEjitxx/?img_index=1 ",
                        "https://www.instagram.com/reel/ABC123xyz/",
                    ],
                }
            ],
        },
    )

    parsed = parse_batch_json(batch_path)

    assert parsed.schema_version == "1.0"
    assert parsed.batch_name == "descargas_junio_2026"
    assert parsed.source_file == batch_path
    assert len(parsed.accounts) == 1
    account = parsed.accounts[0]
    assert account.username == "example_user"
    assert account.start_now_date == date(2026, 6, 4)
    assert account.download_stories is True
    assert account.urls == (
        "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
        "https://www.instagram.com/reel/ABC123xyz/",
    )


def test_parse_inherits_defaults_and_allows_empty_urls_for_stories(
    tmp_path: Path,
) -> None:
    batch_path = _write_batch(
        tmp_path,
        {
            "schema_version": "1.0",
            "batch_name": "stories_only",
            "defaults": {
                "download_stories": True,
                "start_now_date": "2026-06-04",
            },
            "accounts": [
                {
                    "username": "example_user",
                    "urls": [],
                }
            ],
        },
    )

    parsed = parse_batch_json(batch_path)

    account = parsed.accounts[0]
    assert account.start_now_date == date(2026, 6, 4)
    assert account.download_stories is True
    assert account.urls == ()


def test_parse_removes_duplicate_urls_within_same_account(tmp_path: Path) -> None:
    batch_path = _write_batch(
        tmp_path,
        {
            "schema_version": "1.0",
            "batch_name": "dedupe",
            "defaults": {"start_now_date": "2026-06-04"},
            "accounts": [
                {
                    "username": "example_user",
                    "urls": [
                        "https://www.instagram.com/reel/ABC123xyz/",
                        " https://www.instagram.com/reel/ABC123xyz/ ",
                        "https://www.instagram.com/p/XYZ789abc/",
                    ],
                }
            ],
        },
    )

    parsed = parse_batch_json(batch_path)

    assert parsed.accounts[0].urls == (
        "https://www.instagram.com/reel/ABC123xyz/",
        "https://www.instagram.com/p/XYZ789abc/",
    )


def test_parse_rejects_invalid_date_with_account_context(tmp_path: Path) -> None:
    batch_path = _write_batch(
        tmp_path,
        {
            "schema_version": "1.0",
            "batch_name": "bad_date",
            "accounts": [
                {
                    "username": "example_user",
                    "start_now_date": "04-06-2026",
                    "download_stories": True,
                    "urls": [],
                }
            ],
        },
    )

    with pytest.raises(
        BatchJsonParserError,
        match=r"accounts\[1\]\.start_now_date.*YYYY-MM-DD",
    ):
        parse_batch_json(batch_path)


def test_parse_rejects_non_instagram_url_with_account_context(tmp_path: Path) -> None:
    batch_path = _write_batch(
        tmp_path,
        {
            "schema_version": "1.0",
            "batch_name": "bad_url",
            "defaults": {"start_now_date": "2026-06-04"},
            "accounts": [
                {
                    "username": "example_user",
                    "urls": ["https://example.com/p/XYZ789abc/"],
                }
            ],
        },
    )

    with pytest.raises(
        BatchJsonParserError,
        match=r"accounts\[1\]\.urls\[1\].*example_user.*Instagram domain",
    ):
        parse_batch_json(batch_path)


def test_parse_rejects_empty_urls_when_stories_are_disabled(tmp_path: Path) -> None:
    batch_path = _write_batch(
        tmp_path,
        {
            "schema_version": "1.0",
            "batch_name": "empty",
            "defaults": {
                "download_stories": False,
                "start_now_date": "2026-06-04",
            },
            "accounts": [{"username": "example_user", "urls": []}],
        },
    )

    with pytest.raises(BatchJsonParserError, match=r"accounts\[1\]\.urls"):
        parse_batch_json(batch_path)


def _write_batch(tmp_path: Path, payload: dict[str, object]) -> Path:
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(json.dumps(payload), encoding="utf-8")
    return batch_path
