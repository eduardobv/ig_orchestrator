from __future__ import annotations

from pathlib import Path
from typing import Final

from ig_orchestrator.models.download_file import MediaType


IMAGE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }
)
VIDEO_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
    }
)


def classify_file_media_type(path: Path | str) -> MediaType:
    """Classify a downloaded file by its extension."""

    extension = Path(path).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    if extension in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    return MediaType.UNKNOWN
