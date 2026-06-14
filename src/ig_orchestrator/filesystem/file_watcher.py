from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Final


TEMPORARY_FILE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".crdownload",
        ".download",
        ".part",
        ".partial",
        ".tmp",
        ".temp",
    }
)


def watch_downloaded_files(
    folder: Path | str,
    start_time: datetime | float | int,
    timeout_seconds: float,
    stable_seconds: float,
    *,
    poll_interval_seconds: float = 0.25,
) -> list[Path]:
    """Return files created or modified after ``start_time`` once stable.

    The watcher is intentionally passive: it never moves, deletes, or opens the
    downloaded files for writing. It only observes direct children of ``folder``.
    """

    watch_folder = Path(folder)
    if not watch_folder.is_dir():
        raise FileNotFoundError(f"download folder does not exist: {watch_folder}")
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be greater than or equal to 0")
    if stable_seconds < 0:
        raise ValueError("stable_seconds must be greater than or equal to 0")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than 0")

    start_timestamp = _to_timestamp(start_time)
    deadline = time.monotonic() + timeout_seconds
    last_activity_at = time.monotonic()
    candidates: dict[Path, tuple[int, float]] = {}

    while True:
        now = time.monotonic()
        changed = _scan_folder(watch_folder, start_timestamp, candidates)
        if changed:
            last_activity_at = now

        if candidates and now - last_activity_at >= stable_seconds:
            return sorted(candidates)

        if now >= deadline:
            return sorted(candidates) if candidates and stable_seconds == 0 else []

        sleep_seconds = min(poll_interval_seconds, max(0.0, deadline - now))
        if sleep_seconds:
            time.sleep(sleep_seconds)


def _scan_folder(
    folder: Path,
    start_timestamp: float,
    candidates: dict[Path, tuple[int, float]],
) -> bool:
    changed = False
    current_paths: set[Path] = set()

    for path in folder.iterdir():
        if not _is_candidate_file(path, start_timestamp):
            continue

        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime)
        current_paths.add(path)
        if candidates.get(path) != signature:
            candidates[path] = signature
            changed = True

    for known_path in set(candidates) - current_paths:
        del candidates[known_path]
        changed = True

    return changed


def _is_candidate_file(path: Path, start_timestamp: float) -> bool:
    if not path.is_file():
        return False
    if _is_temporary_file(path):
        return False

    stat = path.stat()
    return max(stat.st_ctime, stat.st_mtime) >= start_timestamp


def _is_temporary_file(path: Path) -> bool:
    suffixes = {suffix.lower() for suffix in path.suffixes}
    return bool(suffixes & TEMPORARY_FILE_SUFFIXES)


def _to_timestamp(value: datetime | float | int) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return float(value)
