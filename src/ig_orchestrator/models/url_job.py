from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class PublicationType(StrEnum):
    POST = "POST"
    REEL = "REEL"
    STORY = "STORY"
    HIGHLIGHTS = "HIGHLIGHTS"
    UNKNOWN = "UNKNOWN"


class UrlSource(StrEnum):
    GENERATED_STORY = "GENERATED_STORY"
    INPUT_URL = "INPUT_URL"


class UrlJobStatus(StrEnum):
    PENDING = "PENDING"
    SENT_TO_BOT = "SENT_TO_BOT"
    WAITING_DOWNLOAD = "WAITING_DOWNLOAD"
    DOWNLOADED = "DOWNLOADED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED_TEMPORARY = "FAILED_TEMPORARY"
    FAILED_FINAL = "FAILED_FINAL"
    CLASSIFIED = "CLASSIFIED"
    COMPLETED = "COMPLETED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class UrlJob:
    account_id: int
    url: str
    publication_type: PublicationType
    source: UrlSource
    status: UrlJobStatus
    id: int | None = None
    run_id: int | None = None
    retries: int = 0
    max_retries: int | None = None
    last_error: str | None = None
    last_error_type: str | None = None
    non_retryable: bool = False
    sent_message_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next_retry_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _validate_positive("UrlJob.id", self.id, allow_none=True)
        _validate_positive("UrlJob.account_id", self.account_id)
        _validate_positive("UrlJob.run_id", self.run_id, allow_none=True)
        _validate_positive(
            "UrlJob.sent_message_id", self.sent_message_id, allow_none=True
        )
        if not self.url.strip():
            raise ValueError("UrlJob.url must not be blank")
        if not isinstance(self.publication_type, PublicationType):
            raise ValueError("UrlJob.publication_type must be a PublicationType")
        if not isinstance(self.source, UrlSource):
            raise ValueError("UrlJob.source must be a UrlSource")
        if not isinstance(self.status, UrlJobStatus):
            raise ValueError("UrlJob.status must be a UrlJobStatus")
        if self.retries < 0:
            raise ValueError("UrlJob.retries must not be negative")
        if self.max_retries is not None and self.max_retries < 0:
            raise ValueError("UrlJob.max_retries must not be negative")
        if not isinstance(self.non_retryable, bool):
            raise ValueError("UrlJob.non_retryable must be a bool")


def _validate_positive(name: str, value: int | None, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if value is None or value <= 0:
        raise ValueError(f"{name} must be positive")
