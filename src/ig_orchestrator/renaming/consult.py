"""Reference timeline read from bdapp's file index instead of the disk (renaming without ``G:``).

``IndexConsultProvider`` returns the same ``ConsultItem`` objects as ``DiskConsultProvider`` so the renamer
cannot tell the difference. The index keeps only what the algorithm needs: media id, date, owner id,
extension and the suffix (``media_index``, keyed by the account primary key).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ig_orchestrator.renaming.files import ConsultItem

KIND_BY_SUBFOLDER = {"": 0, "reels": 1, "story": 2, "highlights": 3}
EXT_NAMES = ("jpg", "jpeg", "mp4")
MAX_INT64 = 2**63 - 1


def kind_for_rel(rel: str) -> int | None:
    """``media_index.kind`` of a relative sub-folder (``''`` root, ``reels``...); ``None`` for any other folder."""

    return KIND_BY_SUBFOLDER.get(rel.replace("/", "\\").strip("\\").casefold())


def to_datetime(taken_at: int) -> datetime:
    return datetime.fromtimestamp(taken_at, timezone.utc).replace(tzinfo=None)


def has_index(conn: sqlite3.Connection, account_id: int) -> bool:
    """True when the account has any indexed file or an index state (even an empty one)."""

    return bool(
        conn.execute("SELECT 1 FROM media_index WHERE account_id = ? LIMIT 1", (account_id,)).fetchone()
        or conn.execute("SELECT 1 FROM media_index_state WHERE account_id = ? LIMIT 1", (account_id,)).fetchone()
    )


def index_status(conn: sqlite3.Connection, account_id: int) -> str:
    """Short human text: ``'4718 ficheros · 12/07'`` or ``'sin indice'``."""

    count = conn.execute("SELECT COUNT(*) FROM media_index WHERE account_id = ?", (account_id,)).fetchone()[0]
    stamp = conn.execute(
        "SELECT MAX(indexed_at) FROM media_index_state WHERE account_id = ?", (account_id,)
    ).fetchone()[0]
    if not count and not stamp:
        return "sin indice"
    when = ""
    if stamp:
        try:
            parsed = datetime.fromisoformat(str(stamp))
            when = f" · {parsed.day:02d}/{parsed.month:02d}"
        except ValueError:
            pass
    return f"{count} ficheros{when}"


class IndexConsultProvider:
    def __init__(self, conn: sqlite3.Connection, account_id: int) -> None:
        self.conn = conn
        self.account_id = account_id

    def items(self, rel: str) -> list[ConsultItem] | None:
        kind = kind_for_rel(rel)
        if kind is None:
            return None  # a folder the library does not use (no reference)
        rows = self.conn.execute(
            "SELECT media_id, taken_at, owner_id, ext, suffix FROM media_index"
            " WHERE account_id = ? AND kind = ? ORDER BY media_id, id",
            (self.account_id, kind),
        ).fetchall()
        if not rows:
            known = kind == 0 or self.conn.execute(
                "SELECT 1 FROM media_index_state WHERE account_id = ? AND kind = ?", (self.account_id, kind)
            ).fetchone()
            return [] if known else None
        items = []
        for row in rows:
            ext = EXT_NAMES[int(row["ext"])]
            stamp = to_datetime(int(row["taken_at"]))
            name = f"{stamp:%Y-%m-%d %H.%M.%S} {row['media_id']}_{row['owner_id']}{row['suffix']}.{ext}"
            items.append(ConsultItem(name, stamp, int(row["media_id"]), str(row["owner_id"]), ext, str(row["suffix"])))
        return items


def write_through(
    conn: sqlite3.Connection, account_id: int, renamed: list[tuple[str, str]]
) -> int:
    """Add the files just renamed to the index. ``renamed`` is ``[(relative folder, new file name)]``."""

    from ig_orchestrator.library.filenames import parse_media_name

    rows = []
    kinds: set[int] = set()
    for rel, name in renamed:
        kind = kind_for_rel(rel)
        parsed = parse_media_name(name)
        if kind is None or parsed is None or parsed.media_id > MAX_INT64:
            continue
        kinds.add(kind)
        rows.append((account_id, kind, parsed.media_id, parsed.taken_at, parsed.owner_id, parsed.ext, parsed.suffix))
    conn.executemany(
        "INSERT INTO media_index (account_id, kind, media_id, taken_at, owner_id, ext, suffix) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    now = datetime.now(timezone.utc).isoformat()
    for kind in kinds:
        items, top = conn.execute(
            "SELECT COUNT(*), MAX(media_id) FROM media_index WHERE account_id = ? AND kind = ?", (account_id, kind)
        ).fetchone()
        conn.execute("DELETE FROM media_index_state WHERE account_id = ? AND kind = ?", (account_id, kind))
        conn.execute(
            "INSERT INTO media_index_state (account_id, kind, items, max_media_id, indexed_at, source)"
            " VALUES (?, ?, ?, ?, ?, 'rename')",
            (account_id, kind, items, top, now),
        )
    conn.commit()
    return len(rows)


def verify_index(conn: sqlite3.Connection, account_id: int, account_folder: str) -> dict[str, list[str]]:
    """Compare the index of one account with its folders on disk. Returns ``{'added': [...], 'removed': [...]}``.

    ``added`` = on disk but not in the index; ``removed`` = in the index but not on disk. Needs the library online.
    """

    import os

    from ig_orchestrator.library.filenames import parse_media_name

    added: list[str] = []
    removed: list[str] = []
    for rel, kind in KIND_BY_SUBFOLDER.items():
        folder = os.path.join(account_folder, rel) if rel else account_folder
        on_disk: dict[tuple, str] = {}
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                parsed = parse_media_name(name)
                if parsed is not None and os.path.isfile(os.path.join(folder, name)):
                    on_disk[(parsed.media_id, parsed.taken_at, parsed.owner_id, parsed.ext, parsed.suffix)] = name
        indexed = {
            (int(r[0]), int(r[1]), int(r[2]), int(r[3]), str(r[4]))
            for r in conn.execute(
                "SELECT media_id, taken_at, owner_id, ext, suffix FROM media_index WHERE account_id = ? AND kind = ?",
                (account_id, kind),
            )
        }
        label = rel or "(raiz)"
        added += [f"{label}/{name}" for key, name in on_disk.items() if key not in indexed]
        removed += [f"{label}: media_id {key[0]}{key[4]}" for key in indexed if key not in on_disk]
    return {"added": added, "removed": removed}
