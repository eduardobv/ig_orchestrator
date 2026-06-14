from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.filesystem import classify_file_media_type
from ig_orchestrator.models import MediaType


@pytest.mark.parametrize(
    "filename",
    [
        "photo.jpg",
        "photo.jpeg",
        "photo.png",
        "photo.webp",
        "PHOTO.JPG",
        "Photo.JpEg",
    ],
)
def test_classify_file_media_type_detects_images(filename: str) -> None:
    assert classify_file_media_type(Path(filename)) is MediaType.IMAGE


@pytest.mark.parametrize(
    "filename",
    [
        "video.mp4",
        "video.mov",
        "video.mkv",
        "video.webm",
        "VIDEO.MP4",
        "Video.MoV",
    ],
)
def test_classify_file_media_type_detects_videos(filename: str) -> None:
    assert classify_file_media_type(filename) is MediaType.VIDEO


@pytest.mark.parametrize(
    "filename",
    [
        "archive.zip",
        "caption.txt",
        "without_extension",
        "photo.jpg.tmp",
    ],
)
def test_classify_file_media_type_returns_unknown_for_other_extensions(
    filename: str,
) -> None:
    assert classify_file_media_type(filename) is MediaType.UNKNOWN
