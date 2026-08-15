from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from sqlite3 import Connection
from typing import Iterable

from ig_orchestrator.db import AccountHistoryRepository
from ig_orchestrator.models import AccountHistoryStatus


@dataclass(frozen=True, slots=True)
class AccountCatalogEntry:
    username: str
    start_now_date: str | None = None
    source: str = ""
    owner_id: str | None = None
    destination_path: str | None = None
    start_init_date: str | None = None
    status: AccountHistoryStatus = AccountHistoryStatus.ENABLED
    is_favorite: bool = False


class AccountCatalogService:
    def __init__(
        self,
        connection: Connection,
        *,
        batch_json_path: Path = Path("config/batch.json"),
        backup_dir: Path = Path("config/bkp"),
    ) -> None:
        self.connection = connection
        self.batch_json_path = batch_json_path
        self.backup_dir = backup_dir

    def list_entries(self) -> list[AccountCatalogEntry]:
        entries: list[AccountCatalogEntry] = []
        entries.extend(self._from_account_history())
        entries.extend(self._from_batch_json(self.batch_json_path, source="batch.json"))
        if not entries:
            for backup_path in sorted(self.backup_dir.glob("*.json")):
                entries.extend(self._from_batch_json(backup_path, source="backup"))
        return sorted(_deduplicate(entries), key=_catalog_sort_key)

    def disable(self, username: str) -> None:
        repository = AccountHistoryRepository(self.connection)
        repository.create_or_get(username)
        repository.update_status(
            username,
            AccountHistoryStatus.DISABLED,
        )

    def enable(self, username: str) -> None:
        """Reactivate a DISABLED or INACTIVE catalog account as ENABLED."""
        repository = AccountHistoryRepository(self.connection)
        repository.create_or_get(username)
        repository.update_status(
            username,
            AccountHistoryStatus.ENABLED,
        )

    def set_inactive(self, username: str) -> None:
        repository = AccountHistoryRepository(self.connection)
        repository.create_or_get(username)
        repository.set_inactive(username)

    def set_favorite(self, username: str, *, favorite: bool) -> None:
        AccountHistoryRepository(self.connection).set_favorite(
            username,
            favorite=favorite,
        )

    def list_destination_paths(self) -> list[str]:
        return AccountHistoryRepository(
            self.connection
        ).list_distinct_destination_paths()

    def filter_entries(
        self,
        entries: Iterable[AccountCatalogEntry],
        query: str,
    ) -> list[AccountCatalogEntry]:
        """Filter catalog rows; exact username match expands same-folder peers."""
        return filter_catalog_entries(entries, query)

    def list_usernames_active_on_date(self, day: date) -> set[str]:
        return list_usernames_active_on_date(self.connection, day)

    def _from_account_history(self) -> Iterable[AccountCatalogEntry]:
        for record in AccountHistoryRepository(self.connection).list_all():
            yield AccountCatalogEntry(
                username=record.user_name,
                source="account_history",
                owner_id=record.user_ig_id,
                destination_path=record.field1,
                start_init_date=record.field2,
                status=record.status,
                is_favorite=record.is_favorite,
            )

    def _from_batch_json(
        self,
        path: Path,
        *,
        source: str,
    ) -> Iterable[AccountCatalogEntry]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        accounts = payload.get("accounts")
        if not isinstance(accounts, list):
            return []

        entries: list[AccountCatalogEntry] = []
        for raw_account in accounts:
            if not isinstance(raw_account, dict):
                continue
            raw_username = raw_account.get("username")
            if not isinstance(raw_username, str):
                continue
            username = raw_username.strip().lstrip("@").strip()
            if not username:
                continue
            raw_start_date = raw_account.get("start_now_date")
            entries.append(
                AccountCatalogEntry(
                    username=username,
                    start_now_date=(
                        raw_start_date.strip()
                        if isinstance(raw_start_date, str) and raw_start_date.strip()
                        else None
                    ),
                    source=source,
                )
            )
        return entries


def _deduplicate(entries: Iterable[AccountCatalogEntry]) -> list[AccountCatalogEntry]:
    deduplicated: list[AccountCatalogEntry] = []
    seen: set[str] = set()
    for entry in entries:
        key = entry.username.lower()
        if key in seen:
            continue
        deduplicated.append(entry)
        seen.add(key)
    return deduplicated


def _catalog_sort_key(entry: AccountCatalogEntry) -> tuple[object, ...]:
    username = entry.username.casefold()
    destination_path = (entry.destination_path or "").strip().casefold()
    if entry.status is AccountHistoryStatus.DISABLED:
        return (4, username)
    if entry.status is AccountHistoryStatus.INACTIVE:
        return (3, username)
    if entry.is_favorite:
        return (0, not bool(destination_path), destination_path, username)
    if destination_path:
        return (1, destination_path, username)
    return (2, username)


def _normalized_destination_path(entry: AccountCatalogEntry) -> str:
    return (entry.destination_path or "").strip().casefold()


def filter_catalog_entries(
    entries: Iterable[AccountCatalogEntry],
    query: str,
) -> list[AccountCatalogEntry]:
    """Return catalog entries matching *query*.

    Empty query keeps every entry (caller order preserved).

    When *query* matches a username exactly (case-insensitive) and that entry
    has a non-empty ``destination_path`` (``account_history.field1``), the
    result is every entry that shares the same path, not only the matched
    username. The exact match is always listed first; remaining folder peers
    keep their original relative order. Without a path, only the exact match
    is returned.

    Without an exact username match, filtering is substring-based on username.
    """
    materialized = list(entries)
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return materialized

    exact_matches = [
        entry
        for entry in materialized
        if entry.username.casefold() == normalized_query
    ]
    if exact_matches:
        exact = exact_matches[0]
        folder_path = _normalized_destination_path(exact)
        if not folder_path:
            return [exact]
        peers = [
            entry
            for entry in materialized
            if _normalized_destination_path(entry) == folder_path
            and entry.username.casefold() != normalized_query
        ]
        return [exact, *peers]

    return [
        entry
        for entry in materialized
        if normalized_query in entry.username.casefold()
    ]


def _iso_to_local_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().date()


def list_usernames_active_on_date(connection: Connection, day: date) -> set[str]:
    """Usernames added to a batch or downloaded (non dry-run) on *day* (local)."""

    active: set[str] = set()
    for row in connection.execute(
        "SELECT username, created_at FROM accounts"
    ):
        username = str(row["username"] or "").strip()
        if not username:
            continue
        if _iso_to_local_date(row["created_at"]) == day:
            active.add(username.casefold())

    for row in connection.execute(
        """
        SELECT a.username, r.started_at, r.summary
        FROM runs r
        JOIN accounts a ON (
            (r.account_id IS NOT NULL AND a.id = r.account_id)
            OR (r.account_id IS NULL AND r.batch_id IS NOT NULL
                AND a.batch_id = r.batch_id)
        )
        """
    ):
        username = str(row["username"] or "").strip()
        if not username:
            continue
        summary = str(row["summary"] or "")
        if summary.startswith("Dry-run batch"):
            continue
        if _iso_to_local_date(row["started_at"]) == day:
            active.add(username.casefold())
    return active


__all__ = [
    "AccountCatalogEntry",
    "AccountCatalogService",
    "filter_catalog_entries",
    "list_usernames_active_on_date",
]
