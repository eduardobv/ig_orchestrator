from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from pathlib import Path


class AccountStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Account:
    username: str
    start_now_date: date
    download_stories: bool
    status: AccountStatus
    id: int | None = None
    batch_id: int | None = None
    generated_story_url: str | None = None
    working_folder: Path | None = None
    final_destination_folder: Path | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.id is not None and self.id <= 0:
            raise ValueError("Account.id must be positive when provided")
        if self.batch_id is not None and self.batch_id <= 0:
            raise ValueError("Account.batch_id must be positive when provided")
        if not self.username.strip():
            raise ValueError("Account.username must not be blank")
        if not isinstance(self.start_now_date, date):
            raise ValueError("Account.start_now_date must be a date")
        if not isinstance(self.download_stories, bool):
            raise ValueError("Account.download_stories must be a bool")
        if not isinstance(self.status, AccountStatus):
            raise ValueError("Account.status must be an AccountStatus")
        if self.working_folder is not None and not isinstance(self.working_folder, Path):
            raise ValueError("Account.working_folder must be a pathlib.Path")
        if (
            self.final_destination_folder is not None
            and not isinstance(self.final_destination_folder, Path)
        ):
            raise ValueError(
                "Account.final_destination_folder must be a pathlib.Path"
            )
