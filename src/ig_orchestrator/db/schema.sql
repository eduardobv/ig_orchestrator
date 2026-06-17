PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS input_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_file TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    username TEXT NOT NULL,
    start_now_date TEXT NOT NULL,
    download_stories INTEGER NOT NULL DEFAULT 0,
    generated_story_url TEXT,
    working_folder TEXT,
    final_destination_folder TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES input_batches(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    account_id INTEGER,
    status TEXT NOT NULL,
    total_urls INTEGER NOT NULL DEFAULT 0,
    completed_urls INTEGER NOT NULL DEFAULT 0,
    failed_urls INTEGER NOT NULL DEFAULT 0,
    downloaded_files INTEGER NOT NULL DEFAULT 0,
    report_path TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT,
    FOREIGN KEY(batch_id) REFERENCES input_batches(id),
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS url_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    run_id INTEGER,
    url TEXT NOT NULL,
    publication_type TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER,
    last_error TEXT,
    last_error_type TEXT,
    non_retryable INTEGER NOT NULL DEFAULT 0,
    sent_message_id INTEGER,
    started_at TEXT,
    finished_at TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS download_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_job_id INTEGER NOT NULL,
    original_path TEXT NOT NULL,
    working_path TEXT,
    final_path TEXT,
    media_type TEXT NOT NULL,
    file_extension TEXT NOT NULL,
    file_size INTEGER,
    sha256 TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(url_job_id) REFERENCES url_jobs(id)
);

CREATE TABLE IF NOT EXISTS duplicate_url_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    account_id INTEGER NOT NULL,
    run_id INTEGER,
    duplicate_of_url_job_id INTEGER,
    url TEXT NOT NULL,
    publication_type TEXT NOT NULL,
    source TEXT NOT NULL,
    occurrence_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES input_batches(id),
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY(duplicate_of_url_job_id) REFERENCES url_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_input_batches_status ON input_batches(status);
CREATE INDEX IF NOT EXISTS idx_accounts_batch_id ON accounts(batch_id);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_url_jobs_account_id ON url_jobs(account_id);
CREATE INDEX IF NOT EXISTS idx_url_jobs_run_id ON url_jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_url_jobs_status ON url_jobs(status);
CREATE INDEX IF NOT EXISTS idx_download_files_url_job_id ON download_files(url_job_id);
CREATE INDEX IF NOT EXISTS idx_download_files_status ON download_files(status);
CREATE INDEX IF NOT EXISTS idx_duplicate_url_jobs_batch_id ON duplicate_url_jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_url_jobs_account_id ON duplicate_url_jobs(account_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_url_jobs_run_id ON duplicate_url_jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_url_jobs_duplicate_of ON duplicate_url_jobs(duplicate_of_url_job_id);
CREATE INDEX IF NOT EXISTS idx_runs_batch_id ON runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_runs_account_id ON runs(account_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

PRAGMA user_version = 1;
