from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ig_orchestrator.filesystem import watch_downloaded_files


def test_watch_downloaded_files_returns_new_stable_files(tmp_path: Path) -> None:
    start_time = time.time()
    downloaded_file = tmp_path / "photo.jpg"
    downloaded_file.write_text("image", encoding="utf-8")

    files = watch_downloaded_files(
        tmp_path,
        start_time,
        timeout_seconds=1,
        stable_seconds=0.05,
        poll_interval_seconds=0.01,
    )

    assert files == [downloaded_file]


def test_watch_downloaded_files_ignores_old_files_directories_and_temporaries(
    tmp_path: Path,
) -> None:
    old_file = tmp_path / "old.jpg"
    old_file.write_text("old", encoding="utf-8")
    start_time = time.time() + 60
    (tmp_path / "nested").mkdir()
    (tmp_path / "video.mp4.crdownload").write_text("temporary", encoding="utf-8")

    files = watch_downloaded_files(
        tmp_path,
        start_time,
        timeout_seconds=0.05,
        stable_seconds=0.01,
        poll_interval_seconds=0.01,
    )

    assert files == []


def test_watch_downloaded_files_waits_until_size_is_stable(tmp_path: Path) -> None:
    start_time = time.time()
    downloaded_file = tmp_path / "video.mp4"

    def write_in_chunks() -> None:
        time.sleep(0.03)
        downloaded_file.write_text("first", encoding="utf-8")
        time.sleep(0.05)
        downloaded_file.write_text("first second", encoding="utf-8")

    writer = threading.Thread(target=write_in_chunks)
    writer.start()

    files = watch_downloaded_files(
        tmp_path,
        start_time,
        timeout_seconds=1,
        stable_seconds=0.1,
        poll_interval_seconds=0.01,
    )
    writer.join(timeout=1)

    assert files == [downloaded_file]
    assert downloaded_file.read_text(encoding="utf-8") == "first second"


def test_watch_downloaded_files_returns_empty_list_on_timeout(tmp_path: Path) -> None:
    files = watch_downloaded_files(
        tmp_path,
        time.time(),
        timeout_seconds=0.05,
        stable_seconds=0.01,
        poll_interval_seconds=0.01,
    )

    assert files == []


def test_watch_downloaded_files_rejects_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="download folder"):
        watch_downloaded_files(
            tmp_path / "missing",
            time.time(),
            timeout_seconds=0.05,
            stable_seconds=0.01,
            poll_interval_seconds=0.01,
        )
