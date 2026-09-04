from pathlib import Path

from ig_orchestrator.db import (
    GUI_SCHEMA_USER_VERSION,
    connect,
    init_database,
    init_gui_database,
)


EXPECTED_TABLES = {
    "app_settings",
    "path_roots",
    "catalog_account_statuses",
    "batch_statuses",
    "batch_account_statuses",
    "batch_url_statuses",
    "batch_run_statuses",
    "publication_types",
    "url_sources",
    "media_types",
    "queue_statuses",
    "queue_item_statuses",
    "downloaded_file_statuses",
    "bot_errors",
    "catalog_folders",
    "catalog_accounts",
    "batches",
    "batch_accounts",
    "batch_runs",
    "batch_urls",
    "downloaded_files",
    "duplicate_urls",
    "batch_queues",
    "batch_queue_items",
}


def test_connect_enables_wal_and_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "wal.sqlite"
    with connect(db_path) as connection:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
        foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])

    assert journal_mode.lower() == "wal"
    assert synchronous == 1  # NORMAL
    assert foreign_keys == 1


def test_init_gui_database_is_idempotent_and_seeds_lookups(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"

    init_gui_database(db_path)
    init_gui_database(db_path)

    with connect(db_path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        table_names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        view_names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            )
        }
        catalog_status_codes = [
            str(row["code"])
            for row in connection.execute(
                "SELECT code FROM catalog_account_statuses ORDER BY sort_order, id"
            )
        ]
        bot_error_codes = [
            str(row["code"])
            for row in connection.execute(
                "SELECT code FROM bot_errors ORDER BY sort_order, id"
            )
        ]
        batch_count = int(
            connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        )
        account_count = int(
            connection.execute("SELECT COUNT(*) FROM catalog_accounts").fetchone()[0]
        )
        language = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'ui.language'"
        ).fetchone()[0]
        media_not_found = connection.execute(
            """
            SELECT is_retryable, max_retries_override, match_kind
            FROM bot_errors
            WHERE code = 'MEDIA_NOT_FOUND_OR_UNAVAILABLE'
            """
        ).fetchone()
        stories_not_found = connection.execute(
            "SELECT match_kind FROM bot_errors WHERE code = 'STORIES_NOT_FOUND'"
        ).fetchone()
        account_status_codes = {
            str(row["code"])
            for row in connection.execute("SELECT code FROM batch_account_statuses")
        }
        stories_first = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'processing.stories_first'"
        ).fetchone()[0]

    assert version == GUI_SCHEMA_USER_VERSION
    assert EXPECTED_TABLES.issubset(table_names)
    assert "v_all_statuses" in view_names
    assert catalog_status_codes == ["ENABLED", "INACTIVE", "DISABLED", "CHANGED"]
    assert "STORIES_NOT_FOUND" in bot_error_codes
    assert "MEDIA_NOT_FOUND_OR_UNAVAILABLE" in bot_error_codes
    assert batch_count == 0
    assert account_count == 0
    assert language == "es"
    assert "INCOMPLETE" in account_status_codes
    assert str(stories_first) == "1"
    assert int(media_not_found["is_retryable"]) == 1
    assert int(media_not_found["max_retries_override"]) == 1
    assert str(media_not_found["match_kind"]) == "CONTAINS"
    assert str(stories_not_found["match_kind"]) == "REGEX"


def test_gui_patch_restores_incomplete_status_and_stories_first_setting(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "DELETE FROM batch_account_statuses WHERE code = 'INCOMPLETE'"
        )
        connection.execute(
            "DELETE FROM app_settings WHERE key = 'processing.stories_first'"
        )
        connection.commit()

    init_gui_database(db_path)

    with connect(db_path) as connection:
        incomplete = connection.execute(
            "SELECT name FROM batch_account_statuses WHERE code = 'INCOMPLETE'"
        ).fetchone()
        stories_first = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'processing.stories_first'"
        ).fetchone()

    assert incomplete is not None
    assert str(stories_first["value"]) == "1"


def test_init_gui_database_refuses_v1_orchestrator_file(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.sqlite"
    init_database(db_path)

    try:
        init_gui_database(db_path)
    except RuntimeError as exc:
        assert "v1 orchestrator database" in str(exc)
        assert "SQLITE_GUI_DB_PATH" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for a v1 database file")


def test_init_gui_database_rejects_newer_user_version(tmp_path: Path) -> None:
    db_path = tmp_path / "future.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        connection.execute("PRAGMA user_version = 999")
        connection.commit()

    try:
        init_gui_database(db_path)
    except RuntimeError as exc:
        assert "newer than supported" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for a newer GUI schema")
