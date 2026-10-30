"""Additive tables that keep every «check account status» analysis (feat-uc7-1)."""

from __future__ import annotations

from sqlite3 import Connection

ACCOUNT_STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_check_runs (
    id INTEGER PRIMARY KEY,
    folder_id INTEGER,
    folder_rel TEXT NOT NULL,
    state TEXT NOT NULL,
    stop_reason TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_check_runs_folder ON account_check_runs(folder_id);

CREATE TABLE IF NOT EXISTS account_check_results (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES account_check_runs(id) ON DELETE CASCADE,
    account_id INTEGER,
    username TEXT NOT NULL COLLATE NOCASE,
    rel_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    http_status INTEGER,
    detail TEXT,
    checked_at TEXT,
    source_run_id INTEGER,
    UNIQUE (run_id, username)
);
CREATE INDEX IF NOT EXISTS idx_account_check_results_run ON account_check_results(run_id);
"""


def ensure_account_status_schema(connection: Connection) -> None:
    connection.executescript(ACCOUNT_STATUS_SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(account_check_results)")}
    if "source_run_id" not in columns:  # v4.13.x databases: answer copied from an earlier analysis
        connection.execute("ALTER TABLE account_check_results ADD COLUMN source_run_id INTEGER")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_account_check_results_user ON account_check_results(username, checked_at)"
    )


__all__ = ["ACCOUNT_STATUS_SCHEMA", "ensure_account_status_schema"]
