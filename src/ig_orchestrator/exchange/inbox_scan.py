"""List the account folders waiting in an exchange folder."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PART_SUFFIX = ".part"
_LONG_PREFIX = "\\\\?\\"


class ExchangeUnavailableError(OSError):
    """The exchange folder cannot be read (offline share, missing path...)."""


@dataclass(frozen=True, slots=True)
class ExchangeFolder:
    name: str
    path: Path
    file_count: int
    total_bytes: int
    newest_mtime: float
    is_stable: bool

    @property
    def is_empty(self) -> bool:
        return self.file_count == 0


def long_path(path: Path) -> str:
    """Windows extended-length form for paths near MAX_PATH; unchanged elsewhere."""

    text = str(path)
    if os.name != "nt" or text.startswith(_LONG_PREFIX) or len(text) < 240:
        return text
    if text.startswith("\\\\"):
        return _LONG_PREFIX + "UNC\\" + text[2:]
    return _LONG_PREFIX + text


def iter_files(folder: Path) -> Iterator[tuple[Path, int, float]]:
    """Yield ``(relative_path, size, mtime)`` for every file under *folder*."""

    base = long_path(folder)
    for current, _dirs, names in os.walk(base):
        for name in names:
            if name.endswith(PART_SUFFIX):
                continue
            full = os.path.join(current, name)
            try:
                info = os.stat(full)
            except OSError:
                continue
            yield Path(os.path.relpath(full, base)), info.st_size, info.st_mtime


def scan_exchange(
    root: Path,
    *,
    stable_seconds: float,
    now: float | None = None,
) -> list[ExchangeFolder]:
    """Top-level folders of *root* with size info and stability flag.

    A folder is *stable* when none of its files changed in the last
    ``stable_seconds`` (avoids pulling a folder the other instance is still writing).
    """

    try:
        with os.scandir(long_path(root)) as scan:
            entries = sorted(scan, key=lambda e: e.name.casefold())
            dir_names = [e.name for e in entries if _is_dir(e)]
    except OSError as exc:
        raise ExchangeUnavailableError(f"No se puede leer {root}: {exc}") from exc

    reference = time.time() if now is None else now
    folders: list[ExchangeFolder] = []
    for name in dir_names:
        # Packages (manifest) and unfinished packages (.partial) are handled by exchange.manifest.
        if name.endswith(".partial") or os.path.isfile(os.path.join(long_path(Path(root)), name, "manifest.json")):
            continue
        count = 0
        total = 0
        newest = 0.0
        for _rel, size, mtime in iter_files(Path(root) / name):
            count += 1
            total += size
            newest = max(newest, mtime)
        folders.append(
            ExchangeFolder(
                name=name,
                path=Path(root) / name,
                file_count=count,
                total_bytes=total,
                newest_mtime=newest,
                is_stable=count == 0 or (reference - newest) >= stable_seconds,
            )
        )
    return folders


def _is_dir(entry: os.DirEntry) -> bool:
    try:
        return entry.is_dir()
    except OSError:
        return False
