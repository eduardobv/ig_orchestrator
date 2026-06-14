from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    UNKNOWN = "UNKNOWN"


class DownloadFileStatus(StrEnum):
    DETECTED = "DETECTED"
    MOVED_TO_WORKING_FOLDER = "MOVED_TO_WORKING_FOLDER"
    CLASSIFIED_AS_REEL = "CLASSIFIED_AS_REEL"
    CLASSIFIED_AS_POST = "CLASSIFIED_AS_POST"
    CLASSIFIED_AS_STORY = "CLASSIFIED_AS_STORY"
    CLASSIFIED_AS_HIGHLIGHTS = "CLASSIFIED_AS_HIGHLIGHTS"
    FINALIZED = "FINALIZED"
    RENAMED = "RENAMED"
    DUPLICATED = "DUPLICATED"
    DELETED = "DELETED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DownloadFile:
    url_job_id: int
    original_path: Path
    media_type: MediaType
    file_extension: str
    status: DownloadFileStatus
    id: int | None = None
    working_path: Path | None = None
    final_path: Path | None = None
    file_size: int | None = None
    sha256: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.id is not None and self.id <= 0:
            raise ValueError("DownloadFile.id must be positive when provided")
        if self.url_job_id <= 0:
            raise ValueError("DownloadFile.url_job_id must be positive")
        if not isinstance(self.original_path, Path):
            raise ValueError("DownloadFile.original_path must be a pathlib.Path")
        if self.working_path is not None and not isinstance(self.working_path, Path):
            raise ValueError("DownloadFile.working_path must be a pathlib.Path")
        if self.final_path is not None and not isinstance(self.final_path, Path):
            raise ValueError("DownloadFile.final_path must be a pathlib.Path")
        if not isinstance(self.media_type, MediaType):
            raise ValueError("DownloadFile.media_type must be a MediaType")
        if not self.file_extension.strip().startswith("."):
            raise ValueError("DownloadFile.file_extension must start with '.'")
        if not isinstance(self.status, DownloadFileStatus):
            raise ValueError("DownloadFile.status must be a DownloadFileStatus")
        if self.file_size is not None and self.file_size < 0:
            raise ValueError("DownloadFile.file_size must not be negative")
        if self.sha256 is not None and len(self.sha256) != 64:
            raise ValueError("DownloadFile.sha256 must be 64 hexadecimal characters")
