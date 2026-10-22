"""Account card: read and edit the global data of a catalog account (id, first post date, notes).

Changing the Instagram id never renames files (the id lives in the existing file names).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass(frozen=True, slots=True)
class CardIssue:
    code: str
    message: str
    blocking: bool = False


@dataclass(slots=True)
class CardData:
    id: int
    username: str
    instagram_user_id: str
    start_init_date: str
    notes: str
    is_favorite: bool
    status: str
    rel_path: str
    disk_state: str
    posts: int
    reels: int
    stories: int
    highlights: int
    last_media_at: str
    previous_names: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    batches: list[str] = field(default_factory=list)
    is_private: bool = False


def card_summary_text(card: CardData, abs_path: str = "") -> str:
    """Plain-text dump of the whole card (what the "Copy all" button puts in the clipboard)."""

    lines = [
        f"Username: {card.username}",
        f"Instagram ID: {card.instagram_user_id or '-'}",
        f"Start date: {card.start_init_date or '-'}",
        f"Favorite: {'yes' if card.is_favorite else 'no'}",
        f"Private: {'yes' if card.is_private else 'no'}",
        f"Status: {card.status}",
        f"Path: {abs_path or card.rel_path or '-'}",
        f"Disk: {card.disk_state or '-'}",
        f"Posts/Reels/Stories/Highlights: {card.posts} / {card.reels} / {card.stories} / {card.highlights}",
        f"Last media: {card.last_media_at or '-'}",
        f"Previous names: {', '.join(card.previous_names) or '-'}",
        f"Batches: {', '.join(card.batches) or '-'}",
    ]
    if card.notes:
        lines.append(f"Notes: {card.notes}")
    return "\n".join(lines)


def ensure_notes_column(conn: sqlite3.Connection) -> None:
    if "notes" not in {r[1] for r in conn.execute("PRAGMA table_info(catalog_accounts)")}:
        conn.execute("ALTER TABLE catalog_accounts ADD COLUMN notes TEXT")
        conn.commit()


def ensure_private_column(conn: sqlite3.Connection) -> None:
    if "is_private" not in {r[1] for r in conn.execute("PRAGMA table_info(catalog_accounts)")}:
        conn.execute("ALTER TABLE catalog_accounts ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def list_private_usernames(conn: sqlite3.Connection) -> set[str]:
    """Case-folded usernames of the accounts marked as private (empty on a schema without the table)."""

    try:
        ensure_private_column(conn)
        return {str(r[0]).casefold() for r in conn.execute("SELECT username FROM catalog_accounts WHERE is_private = 1")}
    except sqlite3.Error:
        return set()


def set_account_private(conn: sqlite3.Connection, username: str, private: bool) -> bool:
    """Mark/unmark *username* as a private Instagram account. False when it is not in the catalog."""

    ensure_private_column(conn)
    cursor = conn.execute(
        "UPDATE catalog_accounts SET is_private = ?, updated_at = ? WHERE username = ? COLLATE NOCASE",
        (int(private), datetime.now(timezone.utc).isoformat(timespec="seconds"), username.strip().lstrip("@")),
    )
    conn.commit()
    return cursor.rowcount > 0


def load_card(conn: sqlite3.Connection, account_id: int) -> CardData:
    ensure_notes_column(conn)
    ensure_private_column(conn)
    row = conn.execute(
        "SELECT a.*, s.code AS status_code FROM catalog_accounts a JOIN catalog_account_statuses s ON s.id = a.status_id"
        " WHERE a.id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Cuenta no encontrada: {account_id}")
    names = [str(r[0]) for r in conn.execute(
        "SELECT username FROM account_usernames WHERE catalog_account_id = ? ORDER BY id", (account_id,))]
    operations = [
        f"{r['created_at'][:16]} {r['op_type']} {r['src_rel'] or ''} -> {r['dst_rel'] or ''} ({r['status']})"
        for r in conn.execute("SELECT * FROM fs_operations WHERE account_id = ? ORDER BY id DESC LIMIT 5", (account_id,))
    ]
    batches = [str(r[0]) for r in conn.execute(
        "SELECT DISTINCT b.name FROM batch_accounts ba JOIN batches b ON b.id = ba.batch_id"
        " WHERE ba.catalog_account_id = ? ORDER BY b.id DESC LIMIT 5", (account_id,))]
    return CardData(
        id=account_id, username=str(row["username"]), instagram_user_id=str(row["instagram_user_id"] or ""),
        start_init_date=str(row["start_init_date"] or ""), notes=str(row["notes"] or ""),
        is_favorite=bool(row["is_favorite"]), status=str(row["status_code"]), rel_path=str(row["rel_path"] or ""),
        disk_state=str(row["disk_state"] or ""), posts=int(row["posts_count"] or 0), reels=int(row["reels_count"] or 0),
        stories=int(row["story_count"] or 0), highlights=int(row["highlights_count"] or 0),
        last_media_at=str(row["last_media_at"] or ""), previous_names=names, operations=operations, batches=batches,
        is_private=bool(row["is_private"]),
    )


def majority_owner(conn: sqlite3.Connection, account_id: int) -> str | None:
    row = conn.execute(
        "SELECT owner_id FROM media_index WHERE account_id = ? GROUP BY owner_id ORDER BY COUNT(*) DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    return str(row[0]) if row is not None else None


def validate_card(conn: sqlite3.Connection, account_id: int, owner_id: str, start_date: str) -> list[CardIssue]:
    issues: list[CardIssue] = []
    owner_id, start_date = owner_id.strip(), start_date.strip()
    if owner_id:
        if not re.fullmatch(r"\d+", owner_id):
            issues.append(CardIssue("ID_NOT_NUMERIC", "El id de Instagram solo puede tener digitos", True))
        else:
            others = [str(r[0]) for r in conn.execute(
                "SELECT username FROM catalog_accounts WHERE instagram_user_id = ? AND id <> ?", (owner_id, account_id))]
            if others:
                issues.append(CardIssue("ID_DUPLICATED", "Otro registro ya tiene ese id: " + ", ".join(others[:5])))
            major = majority_owner(conn, account_id)
            if major and major != owner_id:
                issues.append(CardIssue("ID_DIFFERS_FROM_FILES", f"Los ficheros de la cuenta son mayoritariamente del id {major}"))
    if start_date:
        try:
            parsed = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            issues.append(CardIssue("DATE_FORMAT", "La fecha debe ser AAAA-MM-DD", True))
        else:
            if parsed > date.today():
                issues.append(CardIssue("DATE_FUTURE", "La fecha no puede ser futura", True))
    return issues


def save_card(
    conn: sqlite3.Connection, account_id: int, *, owner_id: str, start_date: str, notes: str, favorite: bool,
    private: bool | None = None,
) -> list[CardIssue]:
    """Validate and save. Returns the issues; nothing is written when one is blocking."""

    issues = validate_card(conn, account_id, owner_id, start_date)
    if any(i.blocking for i in issues):
        return issues
    ensure_notes_column(conn)
    if private is not None:
        ensure_private_column(conn)
        conn.execute("UPDATE catalog_accounts SET is_private = ? WHERE id = ?", (int(private), account_id))
    conn.execute(
        "UPDATE catalog_accounts SET instagram_user_id = ?, start_init_date = ?, notes = ?, is_favorite = ?, updated_at = ?"
        " WHERE id = ?",
        (owner_id.strip() or None, start_date.strip() or None, notes.strip() or None, int(favorite),
         datetime.now(timezone.utc).isoformat(timespec="seconds"), account_id),
    )
    conn.commit()
    return issues
