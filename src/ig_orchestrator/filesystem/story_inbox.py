"""Move dumped story media into each account's ``story`` folder.

The source filenames look like ``{username}-{timestamp}-….jpeg``. The
destination comes from an external SQLite table ``accounts_dir``
(``username`` → ``path``), not from ``orchestrator_gui.sqlite``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import shutil
import sqlite3

from ig_orchestrator.filesystem.file_classifier import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

EXTRA_MEDIA_EXTENSIONS = frozenset({".bmp", ".gif", ".m4v", ".avi"})
STORY_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | EXTRA_MEDIA_EXTENSIONS
STORY_SUBFOLDER = "story"


class StoryInboxError(ValueError):
    """Raised when the inbox or accounts database cannot be used at all."""


class StoryInboxStatus(StrEnum):
    MOVED = "MOVED"
    NO_USERNAME_IN_NAME = "NO_USERNAME_IN_NAME"
    USERNAME_NOT_IN_DB = "USERNAME_NOT_IN_DB"
    EMPTY_PATH = "EMPTY_PATH"
    ACCOUNT_PATH_MISSING = "ACCOUNT_PATH_MISSING"
    DESTINATION_EXISTS = "DESTINATION_EXISTS"
    MOVE_FAILED = "MOVE_FAILED"


@dataclass(frozen=True, slots=True)
class StoryInboxResult:
    source: Path
    username: str
    destination: Path | None
    status: StoryInboxStatus
    detail: str = ""


def username_from_story_filename(name: str) -> str | None:
    """Return the username prefix before the first ``-``, or ``None``."""

    filename = Path(name).name
    if "-" not in filename:
        return None
    prefix = filename.split("-", 1)[0].strip()
    return prefix or None


def list_inbox_media(inbox: Path) -> list[Path]:
    """Non-recursive media files in *inbox*, sorted by name."""

    if not inbox.is_dir():
        return []
    files: list[Path] = []
    try:
        entries = list(inbox.iterdir())
    except OSError:
        return []
    for entry in entries:
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        if entry.suffix.lower() in STORY_MEDIA_EXTENSIONS:
            files.append(entry)
    files.sort(key=lambda item: item.name.casefold())
    return files


def _connect_accounts_db(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    uri = resolved.as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        connection = sqlite3.connect(resolved)
    connection.row_factory = sqlite3.Row
    return connection


def _lookup_account_path(connection: sqlite3.Connection, username: str) -> str | None:
    row = connection.execute(
        """
        SELECT path FROM accounts_dir
        WHERE username = ? COLLATE NOCASE
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if row is None:
        return None
    return str(row["path"] if "path" in row.keys() else row[0] or "")


def organize_story_inbox(
    *,
    inbox: Path | str,
    accounts_db: Path | str,
) -> list[StoryInboxResult]:
    """Move each media file in *inbox* to ``{accounts_dir.path}/story``."""

    inbox_path = Path(inbox)
    db_path = Path(accounts_db)
    if not inbox_path.is_dir():
        raise StoryInboxError(f"Stories folder does not exist: {inbox_path}")
    if not db_path.is_file():
        raise StoryInboxError(f"Accounts database does not exist: {db_path}")

    try:
        connection = _connect_accounts_db(db_path)
    except sqlite3.Error as exc:
        raise StoryInboxError(f"Cannot open accounts database: {exc}") from exc

    results: list[StoryInboxResult] = []
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "accounts_dir" not in tables:
            raise StoryInboxError(
                "The database has no accounts_dir table. "
                f"File: {db_path}"
            )
        for source in list_inbox_media(inbox_path):
            results.append(_move_one(connection, source))
    finally:
        connection.close()
    return results


def _move_one(connection: sqlite3.Connection, source: Path) -> StoryInboxResult:
    username = username_from_story_filename(source.name)
    if not username:
        return StoryInboxResult(
            source=source,
            username="",
            destination=None,
            status=StoryInboxStatus.NO_USERNAME_IN_NAME,
            detail="filename has no username prefix before '-'",
        )
    try:
        account_path = _lookup_account_path(connection, username)
    except sqlite3.Error as exc:
        return StoryInboxResult(
            source=source,
            username=username,
            destination=None,
            status=StoryInboxStatus.USERNAME_NOT_IN_DB,
            detail=str(exc),
        )
    if account_path is None:
        return StoryInboxResult(
            source=source,
            username=username,
            destination=None,
            status=StoryInboxStatus.USERNAME_NOT_IN_DB,
            detail=f"@{username} not found in accounts_dir",
        )
    stripped = account_path.strip()
    if not stripped:
        return StoryInboxResult(
            source=source,
            username=username,
            destination=None,
            status=StoryInboxStatus.EMPTY_PATH,
            detail="accounts_dir.path is empty",
        )
    account_root = Path(stripped)
    if not account_root.is_dir():
        return StoryInboxResult(
            source=source,
            username=username,
            destination=None,
            status=StoryInboxStatus.ACCOUNT_PATH_MISSING,
            detail=f"account folder missing: {account_root}",
        )
    destination_dir = account_root / STORY_SUBFOLDER
    destination = destination_dir / source.name
    if destination.exists():
        return StoryInboxResult(
            source=source,
            username=username,
            destination=destination,
            status=StoryInboxStatus.DESTINATION_EXISTS,
            detail=f"already exists: {destination}",
        )
    try:
        destination_dir.mkdir(parents=False, exist_ok=True)
        shutil.move(str(source), str(destination))
    except OSError as exc:
        return StoryInboxResult(
            source=source,
            username=username,
            destination=destination,
            status=StoryInboxStatus.MOVE_FAILED,
            detail=str(exc),
        )
    return StoryInboxResult(
        source=source,
        username=username,
        destination=destination,
        status=StoryInboxStatus.MOVED,
    )


def summarize_results(results: list[StoryInboxResult]) -> tuple[int, int]:
    moved = sum(1 for item in results if item.status is StoryInboxStatus.MOVED)
    errors = len(results) - moved
    return moved, errors


__all__ = [
    "STORY_MEDIA_EXTENSIONS",
    "STORY_SUBFOLDER",
    "StoryInboxError",
    "StoryInboxResult",
    "StoryInboxStatus",
    "list_inbox_media",
    "organize_story_inbox",
    "summarize_results",
    "username_from_story_filename",
]
