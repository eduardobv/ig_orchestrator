"""Find accounts that share one Instagram id (probably the same person after a username change)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

RENAME_PROBABLE = "RENAME_PROBABLE"
SAME_CATEGORY = "SAME_CATEGORY"
ALL_DELETED = "ALL_DELETED"
CROSS_CATEGORY = "CROSS_CATEGORY"

DEAD_CATEGORIES = ("09.DELETED", "06.EXCLUDED", "10.TEMP", "11.DISCARTED")
DELETED_NAME = re.compile(r"-(deleted?|inactive)$", re.IGNORECASE)
STALE_DAYS = 365


@dataclass(frozen=True, slots=True)
class Member:
    account_id: int
    username: str
    rel_path: str
    status: str
    last_media_at: str
    content: int

    @property
    def category(self) -> str:
        return self.rel_path.split("\\", 1)[0] if self.rel_path else ""

    @property
    def is_dead(self) -> bool:
        parts = self.rel_path.split("\\") if self.rel_path else []
        category_dead = bool(parts) and parts[0].upper().startswith(DEAD_CATEGORIES)
        group_dead = any(DELETED_NAME.search(p) for p in parts[:-1])
        return category_dead or group_dead or self.status == "DELETED"


@dataclass(slots=True)
class OwnerGroup:
    owner_id: str
    members: list[Member] = field(default_factory=list)
    hint: str = CROSS_CATEGORY
    suggested_current: str = ""


def _days_between(older: str, newer: str) -> int | None:
    try:
        a = datetime.fromisoformat(older.replace(" ", "T")[:19])
        b = datetime.fromisoformat(newer.replace(" ", "T")[:19])
    except ValueError:
        return None
    return (b - a).days


def classify(members: list[Member]) -> tuple[str, str]:
    """``(hint, suggested current username)`` for a group."""

    alive = [m for m in members if not m.is_dead]
    if not alive:
        return ALL_DELETED, ""
    newest = max(alive, key=lambda m: (m.last_media_at, m.content))
    others = [m for m in members if m is not newest]
    if len(alive) == 1:
        return RENAME_PROBABLE, newest.username
    # several active members: a clearly older one is probably the previous name
    stale = [
        m for m in alive if m is not newest and (_days_between(m.last_media_at or "", newest.last_media_at or "") or 0) > STALE_DAYS
    ]
    if stale and len(stale) == len(alive) - 1:
        return RENAME_PROBABLE, newest.username
    if len({m.category.casefold() for m in members}) == 1:
        return SAME_CATEGORY, newest.username
    _ = others
    return CROSS_CATEGORY, newest.username


def find_owner_groups(conn: sqlite3.Connection, *, include_ignored: bool = False) -> list[OwnerGroup]:
    rows = conn.execute(
        """
        SELECT a.id, a.username, a.instagram_user_id AS owner, a.rel_path, s.code AS status, a.last_media_at,
               COALESCE(a.posts_count, 0) + COALESCE(a.reels_count, 0) + COALESCE(a.story_count, 0)
               + COALESCE(a.highlights_count, 0) AS content
        FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id
        WHERE a.instagram_user_id IS NOT NULL AND TRIM(a.instagram_user_id) <> ''
        ORDER BY a.instagram_user_id, a.username COLLATE NOCASE
        """
    ).fetchall()
    ignored = set() if include_ignored else {str(r[0]) for r in conn.execute("SELECT owner_id FROM owner_dup_ignored")}
    grouped: dict[str, list[Member]] = {}
    for row in rows:
        grouped.setdefault(str(row["owner"]).strip(), []).append(
            Member(int(row["id"]), str(row["username"]), str(row["rel_path"] or ""), str(row["status"]),
                   str(row["last_media_at"] or ""), int(row["content"] or 0))
        )
    groups = []
    for owner, members in grouped.items():
        if len(members) < 2 or owner in ignored:
            continue
        hint, current = classify(members)
        groups.append(OwnerGroup(owner, members, hint, current))
    order = {RENAME_PROBABLE: 0, SAME_CATEGORY: 1, CROSS_CATEGORY: 2, ALL_DELETED: 3}
    return sorted(groups, key=lambda g: (order[g.hint], g.owner_id))


def ignore_group(conn: sqlite3.Connection, owner_id: str, note: str = "") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO owner_dup_ignored (owner_id, note, created_at) VALUES (?, ?, ?)",
        (owner_id, note, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def unignore_group(conn: sqlite3.Connection, owner_id: str) -> None:
    conn.execute("DELETE FROM owner_dup_ignored WHERE owner_id = ?", (owner_id,))
    conn.commit()
