"""Parse the download file names the renamer produces/consumes.

``YYYY-MM-DD HH.MM.SS {media_id}_{owner_id}[suffix].ext``
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

FILENAME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2}) (\d+)_(\d+)(.*)\.([A-Za-z0-9]+)$"
)

KIND_CODES = {"POST": 0, "REELS": 1, "STORY": 2, "HIGHLIGHTS": 3}
EXT_CODES = {"jpg": 0, "jpeg": 1, "mp4": 2}


@dataclass(frozen=True, slots=True)
class MediaName:
    taken_at: int
    media_id: int
    owner_id: int
    suffix: str
    ext: int


def parse_media_name(filename: str) -> MediaName | None:
    """Return the parsed name or ``None`` if it does not match / has unknown extension."""

    match = FILENAME_RE.match(filename)
    if match is None:
        return None
    ext = EXT_CODES.get(match.group(10).lower())
    if ext is None:
        return None
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    try:
        taken_at = calendar.timegm((year, month, day, hour, minute, second))
    except (ValueError, OverflowError):
        return None
    return MediaName(
        taken_at=taken_at,
        media_id=int(match.group(7)),
        owner_id=int(match.group(8)),
        suffix=match.group(9),
        ext=ext,
    )
