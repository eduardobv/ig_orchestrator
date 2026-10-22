"""File discovery and name parsing for the renamer (port of ``sc2`` ``file_utils.py``)."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

PHOTO_VIDEO_EXT = (".jpg", ".jpeg", ".mp4")
FILENAME_MANUAL_RE = re.compile(r"^(\d{10,})\.(jpg|jpeg|mp4)$", re.IGNORECASE)
FILENAME_CONSULT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}) (\d{10,})_(\d+)(.*)\.(jpg|jpeg|mp4)$", re.IGNORECASE
)


@dataclass(slots=True)
class ConsultItem:
    """A file (or index row) of the library: the reference timeline of an account folder."""

    filename: str
    date: datetime
    num_id: int
    user_id: str
    ext: str
    rest: str = ""


def parse_date(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H.%M.%S")


def find_media_files(folder: str) -> list[str]:
    """Media files directly inside *folder*, in ``os.listdir`` order (kept for parity with sc2)."""

    try:
        return [
            name
            for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(PHOTO_VIDEO_EXT)
        ]
    except OSError:
        return []


def consult_items_from_names(names: list[str]) -> list[ConsultItem]:
    """Parse library file names; invalid names are ignored. Sorted by ``num_id`` ascending."""

    items = []
    for name in names:
        match = FILENAME_CONSULT_RE.match(name)
        if not match:
            continue
        date_str, num_id, user_id, rest, ext = match.groups()
        try:
            stamp = parse_date(date_str)
        except ValueError:
            continue
        items.append(ConsultItem(name, stamp, int(num_id), user_id, ext, rest))
    return sorted(items, key=lambda item: item.num_id)


def consult_files_structure(folder: str) -> list[ConsultItem]:
    return consult_items_from_names(find_media_files(folder))


def group_manual_files_by_prefix(manual_files: list[dict]) -> list[list[dict]]:
    """Group by the first 6 digits of the id; each group sorted by ``num_id`` descending."""

    groups: dict[str, list[dict]] = defaultdict(list)
    for info in manual_files:
        groups[str(info["num_id"])[:6]].append(info)
    return [sorted(group, key=lambda item: item["num_id"], reverse=True) for group in groups.values()]
