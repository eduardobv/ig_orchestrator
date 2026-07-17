from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Iterable

from ig_orchestrator.db import AccountHistoryRepository


@dataclass(frozen=True, slots=True)
class AccountCatalogEntry:
    username: str
    start_now_date: str | None = None
    source: str = ""
    owner_id: str | None = None
    destination_path: str | None = None
    start_init_date: str | None = None


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
        return sorted(
            _deduplicate(entries),
            key=lambda entry: entry.username.casefold(),
        )

    def _from_account_history(self) -> Iterable[AccountCatalogEntry]:
        for record in AccountHistoryRepository(self.connection).list_all():
            yield AccountCatalogEntry(
                username=record.user_name,
                source="account_history",
                owner_id=record.user_ig_id,
                destination_path=record.field1,
                start_init_date=record.field2,
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


__all__ = ["AccountCatalogEntry", "AccountCatalogService"]
