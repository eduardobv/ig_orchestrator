"""Suggested destination folders when moving accounts, and folder search.

Library convention: a model has a group folder ``Name-Model`` that holds her accounts, with sibling
folders ``Name-Model-Deleted`` / ``Name-Model-Inactive``. The suggestions are the *inverse* of where the
account is now: from ``X`` -> ``X-Deleted`` / ``X-Inactive``; from ``X-Deleted`` -> ``X`` / ``X-Inactive``;
from ``X-Inactive`` -> ``X`` / ``X-Deleted``. A third one is the folder the account came from, or the
configured "deleted accounts" folder.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass

from ig_orchestrator.library.paths import parent_rel, rel_key

SUFFIXES = {"deleted": ("-Deleted", "-Delete"), "inactive": ("-Inactive", "-Inactiva", "-Inactivo")}
_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?P<suffix>-(?:deleted|delete|inactive|inactiva|inactivo))$", re.IGNORECASE)
MAX_SUGGESTIONS = 3


@dataclass(frozen=True, slots=True)
class Suggestion:
    label: str  # folder name shown on the button
    rel: str  # relative path of the folder
    folder_id: int | None  # None = does not exist yet (it would be created)
    reason: str  # deleted | inactive | active | previous | deleted_folder


def split_state(name: str) -> tuple[str, str]:
    """``('Ana-Model', 'active' | 'deleted' | 'inactive')`` for a group folder name."""

    match = _SUFFIX_RE.match(name.strip())
    if match is None:
        return name.strip(), "active"
    kind = "deleted" if match.group("suffix").lower().startswith("-delete") else "inactive"
    return match.group("base"), kind


def _folders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, parent_id, name, rel_path FROM catalog_folders WHERE rel_path IS NOT NULL").fetchall()


def _setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return str(row[0]).strip() if row is not None and str(row[0]).strip() else default


def suggest_destinations(conn: sqlite3.Connection, account_ids: list[int], limit: int = MAX_SUGGESTIONS) -> list[Suggestion]:
    """Up to ``limit`` suggested destination folders for the given accounts (existing folders first)."""

    parents: Counter[str] = Counter()
    previous: str | None = None
    for account_id in account_ids:
        row = conn.execute("SELECT rel_path, previous_rel_path FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None or not row["rel_path"]:
            continue
        parents[parent_rel(str(row["rel_path"]))] += 1
        if previous is None and row["previous_rel_path"]:
            previous = parent_rel(str(row["previous_rel_path"]))
    if not parents:
        return []
    current_rel = parents.most_common(1)[0][0]
    folders = _folders(conn)
    by_key = {rel_key(str(f["rel_path"])): f for f in folders}
    current = by_key.get(rel_key(current_rel))
    if current is None:
        return []
    base, state = split_state(str(current["name"]))
    wanted = {
        "active": [("deleted", SUFFIXES["deleted"][0]), ("inactive", SUFFIXES["inactive"][0])],
        "deleted": [("active", ""), ("inactive", SUFFIXES["inactive"][0])],
        "inactive": [("active", ""), ("deleted", SUFFIXES["deleted"][0])],
    }[state]
    grand = parent_rel(str(current["rel_path"]))
    existing: list[Suggestion] = []
    to_create: list[Suggestion] = []
    seen = {rel_key(current_rel)}

    def find(names: list[str]) -> sqlite3.Row | None:
        lowered = {n.casefold() for n in names}
        candidates = [f for f in folders if str(f["name"]).casefold() in lowered]
        candidates.sort(key=lambda f: (rel_key(parent_rel(str(f["rel_path"]))) != rel_key(grand), str(f["rel_path"])))
        return candidates[0] if candidates else None

    for reason, suffix in wanted:
        names = [base + suffix] if not suffix else [base + s for s in SUFFIXES[reason]]
        found = find(names)
        if found is not None and rel_key(str(found["rel_path"])) not in seen:
            seen.add(rel_key(str(found["rel_path"])))
            existing.append(Suggestion(str(found["name"]), str(found["rel_path"]), int(found["id"]), reason))
        elif found is None and reason != "active":
            new_name = names[0]
            rel = f"{grand}\\{new_name}" if grand else new_name
            to_create.append(Suggestion(new_name, rel, None, reason))
    if previous and rel_key(previous) not in seen and rel_key(previous) in by_key:
        found = by_key[rel_key(previous)]
        seen.add(rel_key(previous))
        existing.append(Suggestion(str(found["name"]), str(found["rel_path"]), int(found["id"]), "previous"))
    if state == "active":
        deleted_rel = _setting(conn, "library.deleted_folder_rel", "09.DELETED")
        found = by_key.get(rel_key(deleted_rel))
        if found is not None and rel_key(deleted_rel) not in seen:
            existing.append(Suggestion(str(found["name"]), str(found["rel_path"]), int(found["id"]), "deleted_folder"))
    return (existing + to_create)[:limit]


def find_folder_matches(folders: list[tuple[int, str, str]], text: str) -> list[int]:
    """Ids of folders whose name contains ``text`` (case-insensitive). ``folders`` = ``(id, name, rel_path)``.

    Exact name matches come first, then names that start with the text, then the rest (by path).
    """

    needle = text.strip().casefold()
    if not needle:
        return []
    hits = [(fid, name, rel) for fid, name, rel in folders if needle in name.casefold()]
    hits.sort(key=lambda h: (h[1].casefold() != needle, not h[1].casefold().startswith(needle), h[2].casefold()))
    return [h[0] for h in hits]
