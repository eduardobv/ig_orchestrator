"""Transitional mirror bdapp -> accounts_lite (``accounts_dir.path``).

Keeps ``sc2`` and legacy tools working until the integrated renamer replaces
them. Idempotent: it only touches rows whose path differs from bdapp.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from ig_orchestrator.library.paths import to_abs

LITE_SETTING = "stories.accounts_db_path"
ENABLED_SETTING = "compat.lite.enabled"


def lite_path_from_settings(app: sqlite3.Connection) -> Path | None:
    enabled = app.execute(
        "SELECT value FROM app_settings WHERE key = ?", (ENABLED_SETTING,)
    ).fetchone()
    if enabled is not None and str(enabled[0]).strip().lower() in {"0", "false", "no"}:
        return None
    row = app.execute("SELECT value FROM app_settings WHERE key = ?", (LITE_SETTING,)).fetchone()
    if row is None or not str(row[0]).strip():
        return None
    return Path(os.path.normpath(str(row[0]).strip()))


def mirror_to_lite(app: sqlite3.Connection, lite_path: Path, root: str) -> int:
    """Update ``accounts_dir.path`` for accounts whose path differs. Returns rows changed.

    Raises ``sqlite3.Error`` / ``OSError`` if lite cannot be written (G: offline, locked...).
    """

    wanted = {
        int(row["legacy_lite_id"]): to_abs(str(row["rel_path"]), root)
        for row in app.execute(
            "SELECT legacy_lite_id, rel_path FROM catalog_accounts"
            " WHERE legacy_lite_id IS NOT NULL AND rel_path IS NOT NULL"
        )
    }
    if not wanted or not lite_path.is_file():
        return 0
    lite = sqlite3.connect(lite_path, timeout=5)
    try:
        current = {int(r[0]): str(r[1]) for r in lite.execute("SELECT id, path FROM accounts_dir")}
        changed = 0
        for lite_id, path in wanted.items():
            if lite_id in current and os.path.normcase(current[lite_id]) != os.path.normcase(path):
                lite.execute("UPDATE accounts_dir SET path = ? WHERE id = ?", (path, lite_id))
                changed += 1
        lite.commit()
        return changed
    finally:
        lite.close()


def add_to_lite(app: sqlite3.Connection, lite_path: Path, account_id: int, root: str, last_modified: str = "") -> int | None:
    """Register a new account in ``accounts_dir`` (what ``sc2`` used to do) and remember its id.

    Returns the lite row id, or ``None`` if lite is not available. Idempotent per path.
    """

    row = app.execute(
        "SELECT username, instagram_user_id, rel_path, legacy_lite_id FROM catalog_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None or not row["rel_path"] or not lite_path.is_file():
        return None
    path = to_abs(str(row["rel_path"]), root)
    stamp = datetime.now().isoformat(timespec="seconds")
    lite = sqlite3.connect(lite_path, timeout=5)
    try:
        existing = lite.execute("SELECT id FROM accounts_dir WHERE path = ?", (path,)).fetchone()
        if existing is not None:
            lite_id = int(existing[0])
        else:
            lite_id = int(lite.execute(
                "INSERT INTO accounts_dir (username, ownerId, path, last_modified, created_at, modified_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (row["username"], row["instagram_user_id"], path, last_modified or None, stamp, stamp),
            ).lastrowid)
        lite.commit()
    finally:
        lite.close()
    app.execute("UPDATE catalog_accounts SET legacy_lite_id = ? WHERE id = ?", (lite_id, account_id))
    app.commit()
    return lite_id
