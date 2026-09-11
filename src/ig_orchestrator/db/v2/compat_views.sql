-- Read/write compatibility views so existing GUI SQL keeps working.

CREATE VIEW IF NOT EXISTS input_batches AS
SELECT
    b.id,
    b.name AS batch_name,
    b.schema_version,
    CAST(NULL AS TEXT) AS source_file,
    bs.code AS status,
    b.start_date AS default_start_now_date,
    b.created_at,
    b.updated_at
FROM batches b
JOIN batch_statuses bs ON bs.id = b.status_id;

CREATE TRIGGER IF NOT EXISTS input_batches_update
INSTEAD OF UPDATE ON input_batches
BEGIN
    UPDATE batches
    SET name = NEW.batch_name,
        schema_version = NEW.schema_version,
        status_id = COALESCE(
            (SELECT id FROM batch_statuses WHERE code = NEW.status),
            status_id
        ),
        start_date = COALESCE(NEW.default_start_now_date, start_date),
        updated_at = datetime('now')
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS input_batches_delete
INSTEAD OF DELETE ON input_batches
BEGIN
    DELETE FROM batch_queue_items WHERE batch_id = OLD.id;
    DELETE FROM duplicate_urls WHERE batch_id = OLD.id;
    DELETE FROM batch_urls
    WHERE batch_account_id IN (SELECT id FROM batch_accounts WHERE batch_id = OLD.id);
    DELETE FROM batch_accounts WHERE batch_id = OLD.id;
    DELETE FROM batch_runs WHERE batch_id = OLD.id;
    DELETE FROM batches WHERE id = OLD.id;
END;

CREATE VIEW IF NOT EXISTS accounts AS
SELECT
    ba.id,
    ba.batch_id,
    ca.username,
    b.start_date AS start_now_date,
    ba.download_stories,
    CASE
        WHEN ba.download_stories = 1
        THEN 'https://www.instagram.com/stories/' || ca.username || '/'
        ELSE NULL
    END AS generated_story_url,
    ba.working_folder_rel AS working_folder,
    CAST(NULL AS TEXT) AS final_destination_folder,
    ba.is_new_account,
    ba.rename_owner_id,
    ba.rename_start_init_date,
    ba.rename_destination_path,
    bas.code AS status,
    ba.created_at,
    ba.updated_at
FROM batch_accounts ba
JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
JOIN batches b ON b.id = ba.batch_id
JOIN batch_account_statuses bas ON bas.id = ba.status_id;

CREATE TRIGGER IF NOT EXISTS accounts_update
INSTEAD OF UPDATE ON accounts
BEGIN
    UPDATE batch_accounts
    SET download_stories = NEW.download_stories,
        is_new_account = NEW.is_new_account,
        rename_owner_id = NEW.rename_owner_id,
        rename_start_init_date = NEW.rename_start_init_date,
        rename_destination_path = NEW.rename_destination_path,
        working_folder_rel = NEW.working_folder,
        status_id = COALESCE(
            (SELECT id FROM batch_account_statuses WHERE code = NEW.status),
            status_id
        ),
        updated_at = datetime('now')
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS accounts_delete
INSTEAD OF DELETE ON accounts
BEGIN
    DELETE FROM duplicate_urls WHERE batch_account_id = OLD.id;
    DELETE FROM batch_urls WHERE batch_account_id = OLD.id;
    DELETE FROM batch_accounts WHERE id = OLD.id;
END;

CREATE VIEW IF NOT EXISTS url_jobs AS
SELECT
    bu.id,
    bu.batch_account_id AS account_id,
    bu.batch_run_id AS run_id,
    bu.url,
    pt.code AS publication_type,
    us.code AS source,
    bus.code AS status,
    bu.retries,
    bu.max_retries,
    bu.last_error_text AS last_error,
    be.code AS last_error_type,
    bu.non_retryable,
    bu.sent_message_id,
    bu.started_at,
    bu.finished_at,
    bu.next_retry_at,
    bu.created_at,
    bu.updated_at
FROM batch_urls bu
JOIN publication_types pt ON pt.id = bu.publication_type_id
JOIN url_sources us ON us.id = bu.source_id
JOIN batch_url_statuses bus ON bus.id = bu.status_id
LEFT JOIN bot_errors be ON be.id = bu.last_error_id;

CREATE TRIGGER IF NOT EXISTS url_jobs_update
INSTEAD OF UPDATE ON url_jobs
BEGIN
    UPDATE batch_urls
    SET batch_run_id = NEW.run_id,
        status_id = COALESCE(
            (SELECT id FROM batch_url_statuses WHERE code = NEW.status),
            status_id
        ),
        retries = NEW.retries,
        max_retries = NEW.max_retries,
        last_error_text = NEW.last_error,
        last_error_id = (SELECT id FROM bot_errors WHERE code = NEW.last_error_type),
        non_retryable = NEW.non_retryable,
        sent_message_id = NEW.sent_message_id,
        started_at = NEW.started_at,
        finished_at = NEW.finished_at,
        next_retry_at = NEW.next_retry_at,
        updated_at = datetime('now')
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS url_jobs_delete
INSTEAD OF DELETE ON url_jobs
BEGIN
    DELETE FROM downloaded_files WHERE batch_url_id = OLD.id;
    DELETE FROM duplicate_urls WHERE duplicate_of_url_id = OLD.id;
    DELETE FROM batch_urls WHERE id = OLD.id;
END;

CREATE VIEW IF NOT EXISTS runs AS
SELECT
    r.id,
    r.batch_id,
    r.batch_account_id AS account_id,
    brs.code AS status,
    r.total_urls,
    r.completed_urls,
    r.failed_urls,
    r.downloaded_files,
    CAST(NULL AS TEXT) AS report_path,
    r.started_at,
    r.finished_at,
    r.summary
FROM batch_runs r
JOIN batch_run_statuses brs ON brs.id = r.status_id;

CREATE VIEW IF NOT EXISTS duplicate_url_jobs AS
SELECT
    d.id,
    d.batch_id,
    d.batch_account_id AS account_id,
    CAST(NULL AS INTEGER) AS run_id,
    d.duplicate_of_url_id AS duplicate_of_url_job_id,
    d.url,
    pt.code AS publication_type,
    us.code AS source,
    d.occurrence_index,
    d.created_at,
    d.updated_at
FROM duplicate_urls d
JOIN publication_types pt ON pt.id = d.publication_type_id
JOIN url_sources us ON us.id = d.source_id;

CREATE TRIGGER IF NOT EXISTS duplicate_url_jobs_delete
INSTEAD OF DELETE ON duplicate_url_jobs
BEGIN
    DELETE FROM duplicate_urls WHERE id = OLD.id;
END;

CREATE VIEW IF NOT EXISTS batch_run_queues AS
SELECT
    q.id,
    qs.code AS status,
    q.created_at,
    q.updated_at
FROM batch_queues q
JOIN queue_statuses qs ON qs.id = q.status_id;

CREATE TRIGGER IF NOT EXISTS batch_run_queues_insert
INSTEAD OF INSERT ON batch_run_queues
BEGIN
    INSERT INTO batch_queues (status_id, created_at, updated_at)
    VALUES (
        (SELECT id FROM queue_statuses WHERE code = NEW.status),
        NEW.created_at,
        NEW.updated_at
    );
END;

CREATE TRIGGER IF NOT EXISTS batch_run_queues_update
INSTEAD OF UPDATE ON batch_run_queues
BEGIN
    UPDATE batch_queues
    SET status_id = COALESCE(
            (SELECT id FROM queue_statuses WHERE code = NEW.status),
            status_id
        ),
        updated_at = datetime('now')
    WHERE id = OLD.id;
END;

CREATE VIEW IF NOT EXISTS batch_run_queue_items AS
SELECT
    i.id,
    i.queue_id,
    i.batch_id,
    i.sort_order,
    qis.code AS status,
    i.created_at,
    i.updated_at
FROM batch_queue_items i
JOIN queue_item_statuses qis ON qis.id = i.status_id;

CREATE TRIGGER IF NOT EXISTS batch_run_queue_items_insert
INSTEAD OF INSERT ON batch_run_queue_items
BEGIN
    INSERT INTO batch_queue_items (
        queue_id, batch_id, sort_order, status_id, created_at, updated_at
    )
    VALUES (
        NEW.queue_id,
        NEW.batch_id,
        NEW.sort_order,
        (SELECT id FROM queue_item_statuses WHERE code = NEW.status),
        NEW.created_at,
        NEW.updated_at
    );
END;

CREATE TRIGGER IF NOT EXISTS batch_run_queue_items_update
INSTEAD OF UPDATE ON batch_run_queue_items
BEGIN
    UPDATE batch_queue_items
    SET sort_order = NEW.sort_order,
        status_id = COALESCE(
            (SELECT id FROM queue_item_statuses WHERE code = NEW.status),
            status_id
        ),
        updated_at = datetime('now')
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS batch_run_queue_items_delete
INSTEAD OF DELETE ON batch_run_queue_items
BEGIN
    DELETE FROM batch_queue_items WHERE id = OLD.id;
END;
