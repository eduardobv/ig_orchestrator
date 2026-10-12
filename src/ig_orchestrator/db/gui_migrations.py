from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.db.connection import connect


SCHEMA_V2_PATH = Path(__file__).resolve().parent / "v2" / "schema.sql"
COMPAT_VIEWS_PATH = Path(__file__).resolve().parent / "v2" / "compat_views.sql"
GUI_SCHEMA_USER_VERSION = 100
_V1_SCHEMA_USER_VERSIONS = frozenset({1, 2, 3})


def prepare_sqlite(db_path: str | Path) -> None:
    """Initialize v1 or GUI schema based on user_version and filename."""

    from ig_orchestrator.db.migrations import init_database

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    probe = sqlite3.connect(path)
    try:
        version = int(probe.execute("PRAGMA user_version").fetchone()[0])
    finally:
        probe.close()
    if version >= GUI_SCHEMA_USER_VERSION or (
        version == 0 and "orchestrator_gui" in path.name
    ):
        init_gui_database(path)
        return
    init_database(path)


def init_gui_database(db_path: str | Path) -> None:
    """Create or migrate the GUI SQLite database without deleting existing data."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        apply_gui_migrations(connection)


def apply_gui_migrations(connection: Connection) -> None:
    """Apply the v2 GUI schema to an existing connection."""

    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version in _V1_SCHEMA_USER_VERSIONS:
        raise RuntimeError(
            "Refusing to initialize the GUI schema on a v1 orchestrator "
            f"database (user_version={current_version}). "
            "Set SQLITE_GUI_DB_PATH to a new file such as "
            r"data\orchestrator_gui.sqlite."
        )
    if current_version > GUI_SCHEMA_USER_VERSION:
        raise RuntimeError(
            "GUI database user_version "
            f"{current_version} is newer than supported "
            f"{GUI_SCHEMA_USER_VERSION}. Use a matching app version."
        )
    if current_version == 0:
        schema = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
        stored_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if stored_version != GUI_SCHEMA_USER_VERSION:
            raise RuntimeError(
                "GUI schema did not set user_version to "
                f"{GUI_SCHEMA_USER_VERSION} (got {stored_version})"
            )
    elif current_version == GUI_SCHEMA_USER_VERSION:
        pass
    else:
        raise RuntimeError(
            "GUI database user_version "
            f"{current_version} cannot be migrated automatically."
        )
    _patch_gui_schema(connection)
    connection.executescript(COMPAT_VIEWS_PATH.read_text(encoding="utf-8"))
    connection.commit()


def _patch_gui_schema(connection: Connection) -> None:
    """Idempotent lookup/column patches for databases already at v100."""

    backup_before_library_migration(connection)

    connection.execute(
        """
        INSERT OR IGNORE INTO batch_url_statuses
            (id, code, name, description, sort_order, is_active)
        VALUES
            (8, 'CLASSIFIED', 'Classified',
             'Files were classified after download.', 8, 1)
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO batch_account_statuses
            (id, code, name, description, sort_order, is_active)
        VALUES
            (6, 'INCOMPLETE', 'Incomplete',
             'Stories finished; remaining non-story URLs are pending.', 6, 1)
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO app_settings (key, value, value_type, updated_at)
        VALUES ('processing.stories_first', '1', 'BOOLEAN', datetime('now'))
        """
    )
    _add_column_if_missing(
        connection, "batch_accounts", "priority", "INTEGER NOT NULL DEFAULT 0"
    )
    _add_column_if_missing(
        connection, "downloaded_files", "working_relative_path", "TEXT"
    )
    _add_column_if_missing(connection, "downloaded_files", "sha256", "TEXT")
    _add_column_if_missing(connection, "downloaded_files", "updated_at", "TEXT")
    _patch_library_schema(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS instances (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('MAIN', 'WORKER')),
            is_local INTEGER NOT NULL DEFAULT 0,
            working_path TEXT,
            exchange_path TEXT,
            exchange_local_path TEXT,
            app_version TEXT,
            last_seen_at TEXT,
            notes TEXT
        )
        """
    )


def _patch_library_schema(connection: Connection) -> None:
    """v3 feat 3: whole-library catalog (paths, counters) + per-account media index."""

    connection.execute(
        """
        INSERT OR IGNORE INTO catalog_account_statuses
            (id, code, name, description, color_hex, sort_order, is_active)
        VALUES (5, 'ARCHIVED', 'Archived',
                'On disk only; never downloaded by the app.', '#e8eaed', 5, 1)
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO catalog_account_statuses
            (id, code, name, description, color_hex, sort_order, is_active)
        VALUES (6, 'DELETED', 'Deleted on Instagram',
                'Account no longer exists; folder archived.', '#d9d2e9', 6, 1)
        """
    )
    for column, definition in (
        ("deleted_at", "TEXT"),
        ("previous_rel_path", "TEXT"),
        ("rel_path", "TEXT"),
        ("posts_count", "INTEGER"),
        ("reels_count", "INTEGER"),
        ("story_count", "INTEGER"),
        ("highlights_count", "INTEGER"),
        ("last_media_at", "TEXT"),
        ("last_scan_at", "TEXT"),
        ("disk_state", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
        ("legacy_lite_id", "INTEGER"),
    ):
        _add_column_if_missing(connection, "catalog_accounts", column, definition)
    _add_column_if_missing(connection, "catalog_folders", "rel_path", "TEXT")
    _add_column_if_missing(
        connection, "catalog_folders", "kind", "TEXT NOT NULL DEFAULT 'GROUP'"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_accounts_rel_path "
        "ON catalog_accounts(rel_path) WHERE rel_path IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_accounts_owner "
        "ON catalog_accounts(instagram_user_id)"
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS library_import_issues (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            username TEXT,
            owner_id TEXT,
            rel_path TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );
        -- Only what the renamer needs: keyed by the account primary key (not username).
        CREATE TABLE IF NOT EXISTS media_index (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
            kind INTEGER NOT NULL,       -- 0 post/root, 1 reels, 2 story, 3 highlights
            media_id INTEGER NOT NULL,
            taken_at INTEGER NOT NULL,   -- naive local time of the file name, as epoch seconds
            owner_id INTEGER NOT NULL,
            ext INTEGER NOT NULL,        -- 0 jpg, 1 jpeg, 2 mp4
            suffix TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_media_index_lookup
            ON media_index(account_id, kind, media_id);
        CREATE TABLE IF NOT EXISTS fs_operations (
            id INTEGER PRIMARY KEY,
            op_group TEXT NOT NULL,
            seq INTEGER NOT NULL,
            op_type TEXT NOT NULL,       -- MKDIR | MOVE_DIR | RENAME_DIR | RMDIR
            src_rel TEXT,
            dst_rel TEXT,
            account_id INTEGER REFERENCES catalog_accounts(id) ON DELETE SET NULL,
            status TEXT NOT NULL,        -- PLANNED | DISK_DONE | COMMITTED | FAILED | UNDONE
            error TEXT,
            undo_of INTEGER REFERENCES fs_operations(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fs_operations_group ON fs_operations(op_group, seq);
        CREATE TABLE IF NOT EXISTS exchange_publications (
            id INTEGER PRIMARY KEY,
            package_id TEXT NOT NULL UNIQUE,
            batch_ids TEXT NOT NULL,      -- JSON list of batch ids
            status TEXT NOT NULL,         -- PENDING | PUBLISHED | FAILED
            path TEXT,
            files INTEGER,
            bytes INTEGER,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exchange_imports (
            id INTEGER PRIMARY KEY,
            package_id TEXT NOT NULL UNIQUE,
            source_instance TEXT,
            batch_id INTEGER REFERENCES batches(id),
            imported_at TEXT NOT NULL,
            files INTEGER,
            bytes INTEGER
        );
        CREATE TABLE IF NOT EXISTS account_lifecycle (
            id INTEGER PRIMARY KEY,
            op_group TEXT,
            account_id INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,           -- DELETE | LABEL | RESTORE
            prev_status_id INTEGER,
            prev_favorite INTEGER,
            prev_rel_path TEXT,
            created_at TEXT NOT NULL,
            undone INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_account_lifecycle_group ON account_lifecycle(op_group);
        CREATE TABLE IF NOT EXISTS media_index_state (
            account_id INTEGER NOT NULL REFERENCES catalog_accounts(id) ON DELETE CASCADE,
            kind INTEGER NOT NULL,
            items INTEGER NOT NULL,
            max_media_id INTEGER,
            indexed_at TEXT NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY (account_id, kind)
        );
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO path_roots (code, path, updated_at)
        SELECT 'LIBRARY', COALESCE(
            (SELECT NULLIF(TRIM(path), '') FROM path_roots WHERE code = 'FINAL_BASE'),
            (SELECT full_path FROM catalog_folders WHERE parent_id IS NULL ORDER BY id LIMIT 1),
            ''
        ), datetime('now')
        """
    )


def backup_before_library_migration(connection: Connection) -> Path | None:
    """Copy the database to ``<db dir>/bkp`` before the v3 library migration.

    Runs only when the migration is still pending and the catalog has data.
    """

    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(catalog_accounts)").fetchall()
    }
    if not columns or "rel_path" in columns:
        return None
    if connection.execute("SELECT COUNT(*) FROM catalog_accounts").fetchone()[0] == 0:
        return None
    return backup_database(connection, "pre_v3")


def backup_database(connection: Connection, label: str) -> Path | None:
    """Copy the main database to ``<db dir>/bkp/<name>_<label>_<timestamp>``."""

    file_name = next(
        (str(row[2]) for row in connection.execute("PRAGMA database_list") if row[1] == "main"),
        "",
    )
    if not file_name:
        return None
    source = Path(file_name)
    target_dir = source.parent / "bkp"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"{source.stem}_{label}_{stamp}{source.suffix}"
    connection.commit()
    backup = sqlite3.connect(target)
    try:
        connection.backup(backup)
    finally:
        backup.close()
    return target


def _add_column_if_missing(
    connection: Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


__all__ = [
    "GUI_SCHEMA_USER_VERSION",
    "SCHEMA_V2_PATH",
    "apply_gui_migrations",
    "init_gui_database",
    "prepare_sqlite",
]
