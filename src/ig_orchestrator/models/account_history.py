from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class AccountHistoryStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    CHANGED = "CHANGED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AccountHistory:
    user_name: str
    status: AccountHistoryStatus = AccountHistoryStatus.ENABLED
    id: int | None = None
    user_ig_id: str | None = None
    field1: str | None = None
    field2: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.id is not None and self.id <= 0:
            raise ValueError("AccountHistory.id must be positive when provided")
        if not self.user_name.strip():
            raise ValueError("AccountHistory.user_name must not be blank")
        if not isinstance(self.status, AccountHistoryStatus):
            raise ValueError("AccountHistory.status must be an AccountHistoryStatus")
