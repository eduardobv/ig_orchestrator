from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path


class InputBatchStatus(StrEnum):
    DRAFT = "DRAFT"
    IMPORTED = "IMPORTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class InputBatch:
    batch_name: str
    schema_version: str
    status: InputBatchStatus
    id: int | None = None
    source_file: Path | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.id is not None and self.id <= 0:
            raise ValueError("InputBatch.id must be positive when provided")
        if not self.batch_name.strip():
            raise ValueError("InputBatch.batch_name must not be blank")
        if not self.schema_version.strip():
            raise ValueError("InputBatch.schema_version must not be blank")
        if not isinstance(self.status, InputBatchStatus):
            raise ValueError("InputBatch.status must be an InputBatchStatus")
        if self.source_file is not None and not isinstance(self.source_file, Path):
            raise ValueError("InputBatch.source_file must be a pathlib.Path")
