from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


@dataclass(slots=True)
class RunSummary:
    status: RunStatus
    total_urls: int = 0
    completed_urls: int = 0
    failed_urls: int = 0
    downloaded_files: int = 0
    summary: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RunStatus):
            raise ValueError("RunSummary.status must be a RunStatus")
        for field_name in (
            "total_urls",
            "completed_urls",
            "failed_urls",
            "downloaded_files",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"RunSummary.{field_name} must not be negative")
        if self.completed_urls + self.failed_urls > self.total_urls:
            raise ValueError(
                "RunSummary completed and failed URLs must not exceed total URLs"
            )
