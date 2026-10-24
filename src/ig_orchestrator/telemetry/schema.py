from __future__ import annotations

from sqlite3 import Connection

# Additive tables of the GUI database. No foreign keys on purpose: telemetry is
# observational and must never block or break the batch.
TELEMETRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS url_job_attempts (
    id INTEGER PRIMARY KEY,
    url_job_id INTEGER NOT NULL,
    batch_id INTEGER,
    batch_run_id INTEGER,
    account_id INTEGER,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    publication_type TEXT,
    expected_items INTEGER,
    album_size_bucket TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    t_send_ms INTEGER,
    t_first_response_ms INTEGER,
    t_first_media_ms INTEGER,
    t_last_media_ms INTEGER,
    t_description_ms INTEGER,
    t_end_wait_ms INTEGER,
    t_download_ms INTEGER,
    t_move_ms INTEGER,
    t_total_ms INTEGER,
    retry_wait_ms INTEGER,
    queue_wait_ms INTEGER,
    flood_wait_ms INTEGER NOT NULL DEFAULT 0,
    exit_reason TEXT,
    outcome TEXT,
    error_code TEXT,
    messages_count INTEGER NOT NULL DEFAULT 0,
    media_count INTEGER NOT NULL DEFAULT 0,
    files_count INTEGER NOT NULL DEFAULT 0,
    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
    duplicates_skipped INTEGER NOT NULL DEFAULT 0,
    aes_backend TEXT,
    settings_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_batch ON url_job_attempts(batch_id);
CREATE INDEX IF NOT EXISTS idx_attempts_job ON url_job_attempts(url_job_id);
CREATE INDEX IF NOT EXISTS idx_attempts_started ON url_job_attempts(started_at);

CREATE TABLE IF NOT EXISTS bot_message_events (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL,
    message_id INTEGER,
    grouped_id INTEGER,
    offset_ms INTEGER NOT NULL,
    kind TEXT NOT NULL,
    mime TEXT,
    has_filename INTEGER NOT NULL DEFAULT 0,
    size_bytes INTEGER,
    download_ms INTEGER,
    text_class TEXT,
    text_len INTEGER
);
CREATE INDEX IF NOT EXISTS idx_message_events_attempt ON bot_message_events(attempt_id);

CREATE TABLE IF NOT EXISTS run_wait_events (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER,
    kind TEXT NOT NULL,
    ms INTEGER NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wait_events_attempt ON run_wait_events(attempt_id);
"""


def ensure_telemetry_schema(connection: Connection) -> None:
    connection.executescript(TELEMETRY_SCHEMA)


def has_telemetry_schema(connection: Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'url_job_attempts'"
    ).fetchone()
    return row is not None


__all__ = ["TELEMETRY_SCHEMA", "ensure_telemetry_schema", "has_telemetry_schema"]
