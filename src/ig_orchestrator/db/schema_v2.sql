PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS path_roots (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_account_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    color_hex TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS batch_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS batch_account_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS batch_url_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS batch_run_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS publication_types (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS url_sources (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS media_types (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS queue_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS queue_item_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS downloaded_file_statuses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bot_errors (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    match_pattern TEXT NOT NULL,
    match_kind TEXT NOT NULL,
    is_retryable INTEGER NOT NULL DEFAULT 0,
    max_retries_override INTEGER,
    notify_on_match INTEGER NOT NULL DEFAULT 0,
    notify_template TEXT,
    description TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS catalog_folders (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES catalog_folders(id),
    name TEXT NOT NULL,
    full_path TEXT NOT NULL,
    depth INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_folders_full_path
    ON catalog_folders(full_path);
CREATE INDEX IF NOT EXISTS idx_catalog_folders_parent
    ON catalog_folders(parent_id);

CREATE TABLE IF NOT EXISTS catalog_accounts (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE,
    instagram_user_id TEXT,
    folder_id INTEGER REFERENCES catalog_folders(id),
    start_init_date TEXT,
    status_id INTEGER NOT NULL REFERENCES catalog_account_statuses(id),
    is_favorite INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_accounts_username
    ON catalog_accounts(username COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_catalog_accounts_folder
    ON catalog_accounts(folder_id);
CREATE INDEX IF NOT EXISTS idx_catalog_accounts_status
    ON catalog_accounts(status_id);
CREATE INDEX IF NOT EXISTS idx_catalog_accounts_favorite
    ON catalog_accounts(is_favorite);

CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    status_id INTEGER NOT NULL REFERENCES batch_statuses(id),
    start_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_batches_name ON batches(name);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status_id);

CREATE TABLE IF NOT EXISTS batch_accounts (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    catalog_account_id INTEGER NOT NULL REFERENCES catalog_accounts(id),
    download_stories INTEGER NOT NULL DEFAULT 0,
    is_new_account INTEGER NOT NULL DEFAULT 0,
    is_catalog_update INTEGER NOT NULL DEFAULT 0,
    rename_owner_id TEXT,
    rename_start_init_date TEXT,
    rename_destination_path TEXT,
    working_folder_rel TEXT,
    status_id INTEGER NOT NULL REFERENCES batch_account_statuses(id),
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, catalog_account_id)
);
CREATE INDEX IF NOT EXISTS idx_batch_accounts_batch ON batch_accounts(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_accounts_catalog
    ON batch_accounts(catalog_account_id);
CREATE INDEX IF NOT EXISTS idx_batch_accounts_status ON batch_accounts(status_id);

CREATE TABLE IF NOT EXISTS batch_runs (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER REFERENCES batches(id),
    batch_account_id INTEGER REFERENCES batch_accounts(id),
    status_id INTEGER NOT NULL REFERENCES batch_run_statuses(id),
    total_urls INTEGER NOT NULL DEFAULT 0,
    completed_urls INTEGER NOT NULL DEFAULT 0,
    failed_urls INTEGER NOT NULL DEFAULT 0,
    downloaded_files INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_batch_runs_batch ON batch_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_runs_account ON batch_runs(batch_account_id);
CREATE INDEX IF NOT EXISTS idx_batch_runs_status ON batch_runs(status_id);

CREATE TABLE IF NOT EXISTS batch_urls (
    id INTEGER PRIMARY KEY,
    batch_account_id INTEGER NOT NULL REFERENCES batch_accounts(id),
    batch_run_id INTEGER REFERENCES batch_runs(id),
    url TEXT NOT NULL,
    publication_type_id INTEGER NOT NULL REFERENCES publication_types(id),
    source_id INTEGER NOT NULL REFERENCES url_sources(id),
    status_id INTEGER NOT NULL REFERENCES batch_url_statuses(id),
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER,
    last_error_id INTEGER REFERENCES bot_errors(id),
    last_error_text TEXT,
    non_retryable INTEGER NOT NULL DEFAULT 0,
    sent_message_id INTEGER,
    started_at TEXT,
    finished_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_urls_account_url
    ON batch_urls(batch_account_id, url);
CREATE INDEX IF NOT EXISTS idx_batch_urls_account ON batch_urls(batch_account_id);
CREATE INDEX IF NOT EXISTS idx_batch_urls_status ON batch_urls(status_id);
CREATE INDEX IF NOT EXISTS idx_batch_urls_run ON batch_urls(batch_run_id);

CREATE TABLE IF NOT EXISTS downloaded_files (
    id INTEGER PRIMARY KEY,
    batch_url_id INTEGER NOT NULL REFERENCES batch_urls(id),
    root_id INTEGER NOT NULL REFERENCES path_roots(id),
    relative_path TEXT NOT NULL,
    media_type_id INTEGER NOT NULL REFERENCES media_types(id),
    extension TEXT NOT NULL,
    file_size INTEGER,
    status_id INTEGER NOT NULL REFERENCES downloaded_file_statuses(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_url ON downloaded_files(batch_url_id);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_root ON downloaded_files(root_id);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_status ON downloaded_files(status_id);

CREATE TABLE IF NOT EXISTS duplicate_urls (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER REFERENCES batches(id),
    batch_account_id INTEGER NOT NULL REFERENCES batch_accounts(id),
    duplicate_of_url_id INTEGER REFERENCES batch_urls(id),
    url TEXT NOT NULL,
    publication_type_id INTEGER NOT NULL REFERENCES publication_types(id),
    source_id INTEGER NOT NULL REFERENCES url_sources(id),
    occurrence_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_duplicate_urls_batch ON duplicate_urls(batch_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_urls_account
    ON duplicate_urls(batch_account_id);

CREATE TABLE IF NOT EXISTS batch_queues (
    id INTEGER PRIMARY KEY,
    status_id INTEGER NOT NULL REFERENCES queue_statuses(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_batch_queues_status ON batch_queues(status_id);

CREATE TABLE IF NOT EXISTS batch_queue_items (
    id INTEGER PRIMARY KEY,
    queue_id INTEGER NOT NULL REFERENCES batch_queues(id),
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    sort_order INTEGER NOT NULL,
    status_id INTEGER NOT NULL REFERENCES queue_item_statuses(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(queue_id, batch_id)
);
CREATE INDEX IF NOT EXISTS idx_batch_queue_items_queue
    ON batch_queue_items(queue_id);
CREATE INDEX IF NOT EXISTS idx_batch_queue_items_status
    ON batch_queue_items(status_id);

CREATE VIEW IF NOT EXISTS v_all_statuses AS
SELECT 'catalog_account' AS domain, id, code, name, description FROM catalog_account_statuses
UNION ALL
SELECT 'batch', id, code, name, description FROM batch_statuses
UNION ALL
SELECT 'batch_account', id, code, name, description FROM batch_account_statuses
UNION ALL
SELECT 'batch_url', id, code, name, description FROM batch_url_statuses
UNION ALL
SELECT 'batch_run', id, code, name, description FROM batch_run_statuses
UNION ALL
SELECT 'publication_type', id, code, name, description FROM publication_types
UNION ALL
SELECT 'url_source', id, code, name, description FROM url_sources
UNION ALL
SELECT 'media_type', id, code, name, description FROM media_types
UNION ALL
SELECT 'queue', id, code, name, description FROM queue_statuses
UNION ALL
SELECT 'queue_item', id, code, name, description FROM queue_item_statuses
UNION ALL
SELECT 'downloaded_file', id, code, name, description FROM downloaded_file_statuses;

INSERT OR IGNORE INTO catalog_account_statuses (id, code, name, description, color_hex, sort_order) VALUES
    (1, 'ENABLED', 'Enabled', 'Visible and selectable in the catalog.', NULL, 1),
    (2, 'INACTIVE', 'Inactive', 'Parked in the catalog without deleting data.', '#fff2cc', 2),
    (3, 'DISABLED', 'Disabled', 'Hidden from normal use; data is kept.', '#f4cccc', 3),
    (4, 'CHANGED', 'Changed', 'Identity or path changed and needs review.', '#cfe2f3', 4);

INSERT OR IGNORE INTO batch_statuses (id, code, name, description, sort_order) VALUES
    (1, 'DRAFT', 'Draft', 'Saved from the GUI and not executed yet.', 1),
    (2, 'IMPORTED', 'Imported', 'Created and ready to run.', 2),
    (3, 'PROCESSING', 'Processing', 'A run is in progress.', 3),
    (4, 'COMPLETED', 'Completed', 'Finished successfully, including rename when applicable.', 4),
    (5, 'PARTIAL', 'Partial', 'Interrupted or finished with pending work.', 5),
    (6, 'FAILED', 'Failed', 'Finished with unrecoverable errors.', 6),
    (7, 'AWAITING_RENAME', 'Awaiting rename', 'Downloads done; waiting for the renamer.', 7);

INSERT OR IGNORE INTO batch_account_statuses (id, code, name, description, sort_order) VALUES
    (1, 'PENDING', 'Pending', 'Not started in this batch.', 1),
    (2, 'PROCESSING', 'Processing', 'Currently being downloaded.', 2),
    (3, 'COMPLETED', 'Completed', 'All URLs for this account finished.', 3),
    (4, 'FAILED', 'Failed', 'The account ended with unrecoverable errors.', 4),
    (5, 'PARTIAL', 'Partial', 'Some URLs remain or the run was interrupted.', 5);

INSERT OR IGNORE INTO batch_url_statuses (id, code, name, description, sort_order) VALUES
    (1, 'PENDING', 'Pending', 'Not sent to the bot yet.', 1),
    (2, 'SENT_TO_BOT', 'Sent to bot', 'URL was sent; waiting for a response.', 2),
    (3, 'WAITING_DOWNLOAD', 'Waiting download', 'Bot accepted the URL; waiting for files.', 3),
    (4, 'DOWNLOADED', 'Downloaded', 'Files were detected for this URL.', 4),
    (5, 'RETRY_PENDING', 'Retry pending', 'Temporary failure; will retry later.', 5),
    (6, 'FAILED_TEMPORARY', 'Failed temporary', 'Retryable error recorded.', 6),
    (7, 'FAILED_FINAL', 'Failed final', 'Retries exhausted or non-retryable error.', 7),
    (8, 'COMPLETED', 'Completed', 'URL fully processed.', 8);

INSERT OR IGNORE INTO batch_run_statuses (id, code, name, description, sort_order) VALUES
    (1, 'PROCESSING', 'Processing', 'This execution is running.', 1),
    (2, 'COMPLETED', 'Completed', 'This execution finished successfully.', 2),
    (3, 'PARTIAL', 'Partial', 'This execution stopped with remaining work.', 3),
    (4, 'FAILED', 'Failed', 'This execution failed.', 4);

INSERT OR IGNORE INTO publication_types (id, code, name, description, sort_order) VALUES
    (1, 'POST', 'Post', 'Instagram photo post (/p/ with img_index, or image-only result).', 1),
    (2, 'REEL', 'Reel', 'Instagram reel or video post.', 2),
    (3, 'STORY', 'Story', 'Profile stories URL.', 3),
    (4, 'HIGHLIGHTS', 'Highlights', 'Story highlight URL.', 4),
    (5, 'UNKNOWN', 'Unknown', 'URL that did not match a known Instagram type.', 5);

INSERT OR IGNORE INTO url_sources (id, code, name, description, sort_order) VALUES
    (1, 'GENERATED_STORY', 'Generated story', 'Built automatically when Stories is checked.', 1),
    (2, 'INPUT_URL', 'Input URL', 'Pasted or typed by the user.', 2);

INSERT OR IGNORE INTO media_types (id, code, name, description, sort_order) VALUES
    (1, 'IMAGE', 'Image', 'jpg, jpeg, png, webp.', 1),
    (2, 'VIDEO', 'Video', 'mp4, mov, mkv, webm.', 2),
    (3, 'UNKNOWN', 'Unknown', 'Unrecognized media extension.', 3);

INSERT OR IGNORE INTO queue_statuses (id, code, name, description, sort_order) VALUES
    (1, 'DRAFT', 'Draft', 'Queue is being built.', 1),
    (2, 'RUNNING', 'Running', 'A batch in the queue is executing.', 2),
    (3, 'PAUSED', 'Paused', 'Queue stopped and can be resumed.', 3),
    (4, 'AWAITING_RENAME', 'Awaiting rename', 'All batches done; waiting for combined rename.', 4),
    (5, 'COMPLETED', 'Completed', 'Queue finished including rename.', 5),
    (6, 'CANCELLED', 'Cancelled', 'Queue was cancelled.', 6);

INSERT OR IGNORE INTO queue_item_statuses (id, code, name, description, sort_order) VALUES
    (1, 'PENDING', 'Pending', 'Not started in this queue.', 1),
    (2, 'RUNNING', 'Running', 'This queue item is the current batch.', 2),
    (3, 'COMPLETED', 'Completed', 'This queue item finished.', 3),
    (4, 'REMOVED', 'Removed', 'Removed from the queue before running.', 4),
    (5, 'SKIPPED', 'Skipped', 'Skipped without running.', 5);

INSERT OR IGNORE INTO downloaded_file_statuses (id, code, name, description, sort_order) VALUES
    (1, 'DETECTED', 'Detected', 'File seen in the Telegram download folder.', 1),
    (2, 'MOVED', 'Moved', 'File moved into the account working folder.', 2),
    (3, 'CLASSIFIED', 'Classified', 'File classified as post, reel, story or highlight.', 3),
    (4, 'FINALIZED', 'Finalized', 'File processing for this run is done.', 4);

INSERT OR IGNORE INTO bot_errors (
    id, code, match_pattern, match_kind, is_retryable, max_retries_override,
    notify_on_match, notify_template, description, is_active, sort_order
) VALUES
    (1, 'SERVICE_OVERLOADED', 'The service is overloaded, please try again later.', 'CONTAINS', 1, NULL, 0, NULL, 'Bot or Instagram service is temporarily overloaded.', 1, 1),
    (2, 'GEOBLOCK_REQUIRED', 'geoblock_required', 'CONTAINS', 1, NULL, 0, NULL, 'Temporary geoblock from the bot.', 1, 2),
    (3, 'MEDIA_NOT_FOUND_OR_UNAVAILABLE', 'Media not found or unavailable', 'CONTAINS', 1, 1, 0, NULL, 'Media missing; retried at most once even if MAX_RETRIES is higher.', 1, 3),
    (4, 'NOT_FOUND', 'We''re sorry, we couldn''t find that.', 'CONTAINS', 0, NULL, 0, NULL, 'Publication not found; do not retry.', 1, 4),
    (5, 'PRIVATE_ACCOUNT_STORIES', 'We can''t get stories from a private account (instagram limit)', 'CONTAINS', 0, NULL, 0, NULL, 'Stories of a private account cannot be fetched.', 1, 5),
    (6, 'STORIES_NOT_FOUND', '\bstories\s+for\s+[^\r\n]+?\s+not\s+found\b', 'REGEX', 0, NULL, 0, NULL, 'No stories for that username; the username in the message varies.', 1, 6);

INSERT OR IGNORE INTO path_roots (id, code, path, updated_at) VALUES
    (1, 'TELEGRAM_DESKTOP', '', datetime('now')),
    (2, 'WORKING', '', datetime('now')),
    (3, 'FINAL_BASE', '', datetime('now'));

INSERT OR IGNORE INTO app_settings (key, value, value_type, updated_at) VALUES
    ('ui.language', 'es', 'TEXT', datetime('now')),
    ('ui.theme', 'light', 'TEXT', datetime('now')),
    ('ui.catalog_view', 'list', 'TEXT', datetime('now')),
    ('ui.show_catalog', '1', 'BOOLEAN', datetime('now')),
    ('ui.show_editor', '1', 'BOOLEAN', datetime('now')),
    ('ui.show_batch', '1', 'BOOLEAN', datetime('now')),
    ('ui.color_favorite', '#d9ead3', 'TEXT', datetime('now')),
    ('ui.color_in_batch', '#f5c08c', 'TEXT', datetime('now')),
    ('ui.color_today', '#fff59d', 'TEXT', datetime('now')),
    ('notify.enabled', '0', 'BOOLEAN', datetime('now')),
    ('notify.target', 'me', 'TEXT', datetime('now')),
    ('notify.template_batch_done', 'Instagram Orchestrator' || char(10) || 'Lote {batch_name} (id={batch_id}) completado' || char(10) || 'Cuentas: {accounts_done}/{accounts_total} · URLs ok: {urls_ok} · fallidas: {urls_failed}', 'TEXT', datetime('now')),
    ('retention.downloaded_files', 'on_complete', 'TEXT', datetime('now'));

PRAGMA user_version = 100;
