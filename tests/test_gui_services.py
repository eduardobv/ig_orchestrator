from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from ig_orchestrator.db import (
    AccountHistoryRepository,
    AccountRepository,
    BatchRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.db.migrations import apply_migrations
from ig_orchestrator.gui.app import (
    InstagramOrchestratorApp,
    _half_screen_geometry,
    _instagram_profile_url,
    _open_chrome_tab,
    _set_ttk_enabled,
    _latest_executed_batch_name,
    _new_account_rename_parameters,
    _timestamp_console_text,
)
from ig_orchestrator.gui.account_catalog_service import AccountCatalogService
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    inspect_account_draft,
    normalize_url_lines,
    save_batch_draft,
    validate_batch_draft,
)
from ig_orchestrator.gui.batch_resume_service import (
    activate_draft_batch,
    complete_account_manually,
    delete_draft_batch,
    fail_account_manually,
    finish_batch,
    get_account_runtime_progress,
    is_batch_ready_for_rename,
    list_managed_batches,
    list_pending_batches,
    load_batch_draft,
    mark_batch_interrupted,
)
from ig_orchestrator.gui.process_runner import (
    NewAccountRenameParameters,
    build_manual_rename_command,
    build_run_continue_command,
)
from ig_orchestrator.input import DuplicateBatchNameError
from ig_orchestrator.models import (
    AccountStatus,
    InputBatchStatus,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJobStatus,
    UrlSource,
)


def test_gui_draft_is_persisted_as_sqlite_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    draft = BatchDraft(
        batch_name="gui_batch",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="@new_user",
                download_stories=True,
                urls=[
                    "https://www.instagram.com/reel/ABC123xyz/",
                    "https://www.instagram.com/p/DZPjwEjitxx/?img_index=1",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)

        assert result.batch.source_file is None
        assert result.batch.batch_name == "gui_batch"
        account = AccountRepository(connection).list_by_batch(result.batch.id)[0]
        assert account.username == "new_user"
        assert account.download_stories is True
        assert account.generated_story_url == "https://www.instagram.com/stories/new_user/"

        jobs = UrlJobRepository(connection).list_by_account(account.id)
        assert [(job.publication_type, job.source) for job in jobs] == [
            (PublicationType.STORY, UrlSource.GENERATED_STORY),
            (PublicationType.REEL, UrlSource.INPUT_URL),
            (PublicationType.POST, UrlSource.INPUT_URL),
        ]
        assert [row.user_name for row in AccountHistoryRepository(connection).list_all()] == [
            "new_user"
        ]


def test_account_catalog_reads_account_history(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        AccountHistoryRepository(connection).create_or_get("known_user")

        entries = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_entries()

    assert [entry.username for entry in entries] == ["known_user"]
    assert entries[0].source == "account_history"


def test_account_catalog_reads_config_batch_json(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_json_path = tmp_path / "batch.json"
    batch_json_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_name": "catalog",
                "defaults": {"start_now_date": "2026-07-06"},
                "accounts": [
                    {"username": "first_user", "start_now_date": "2026-06-21"},
                    {"username": ""},
                    {"username": "@second_user"},
                ],
            }
        ),
        encoding="utf-8",
    )
    init_database(db_path)

    with connect(db_path) as connection:
        entries = AccountCatalogService(
            connection,
            batch_json_path=batch_json_path,
        ).list_entries()

    assert [entry.username for entry in entries] == ["first_user", "second_user"]
    assert entries[0].start_now_date == "2026-06-21"
    assert all(entry.source == "batch.json" for entry in entries)


def test_account_catalog_is_sorted_alphabetically_case_insensitive(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        history = AccountHistoryRepository(connection)
        history.create_or_get("zeta_user")
        history.create_or_get("Alpha_user")
        history.create_or_get("middle_user")

        entries = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_entries()

    assert [entry.username for entry in entries] == [
        "Alpha_user",
        "middle_user",
        "zeta_user",
    ]


def test_catalog_disabled_account_is_hidden_even_if_json_contains_it(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    batch_json = tmp_path / "batch.json"
    batch_json.write_text(
        json.dumps({"accounts": [{"username": "hidden_user"}]}),
        encoding="utf-8",
    )
    init_database(db_path)

    with connect(db_path) as connection:
        service = AccountCatalogService(connection, batch_json_path=batch_json)
        assert [entry.username for entry in service.list_entries()] == ["hidden_user"]
        service.disable("hidden_user")
        assert service.list_entries() == []
        stored = AccountHistoryRepository(connection).get_by_user_name("hidden_user")

    assert stored is not None
    assert stored.status.value == "DISABLED"


def test_catalog_destination_paths_are_distinct_and_editable_source_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        history = AccountHistoryRepository(connection)
        for username, destination in (
            ("one", r"G:\Models"),
            ("two", r"G:\Models"),
            ("three", r"G:\Favorites"),
        ):
            history.update_rename_metadata(
                username,
                owner_id=username,
                destination_path=destination,
                start_init_date="2026-01-01",
            )
        paths = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_destination_paths()

    assert paths == [r"G:\Favorites", r"G:\Models"]


def test_gui_half_screen_geometry_and_instagram_profile_url() -> None:
    assert _half_screen_geometry(1920, 1080) == "960x1000+0+0"
    assert _instagram_profile_url(" @sample_user ") == (
        "https://www.instagram.com/sample_user/"
    )


def test_gui_open_catalog_prefers_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    class ChromeController:
        def open_new_tab(self, url: str) -> bool:
            opened.append(url)
            return True

    monkeypatch.setattr("ig_orchestrator.gui.app.webbrowser.get", lambda name: ChromeController())

    assert _open_chrome_tab("https://www.instagram.com/sample_user/") is True
    assert opened == ["https://www.instagram.com/sample_user/"]


def test_gui_catalog_double_click_loads_username_and_opens_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    applied_dates: list[bool] = []

    class FakeCatalogList:
        def curselection(self) -> tuple[int]:
            return (0,)

        def get(self, index: int) -> str:
            assert index == 0
            return "selected_user"

    class FakeStringVar:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    app = object.__new__(InstagramOrchestratorApp)
    app.catalog_list = FakeCatalogList()
    app.username_var = FakeStringVar()
    app._apply_catalog_date = lambda: applied_dates.append(True)
    monkeypatch.setattr(
        "ig_orchestrator.gui.app._open_chrome_tab",
        lambda url: opened.append(url) or True,
    )

    app._open_and_load_catalog_account()

    assert app.username_var.value == "selected_user"
    assert applied_dates == [True]
    assert opened == ["https://www.instagram.com/selected_user/"]


def test_gui_treeview_state_uses_ttk_state_api() -> None:
    state_calls: list[tuple[str, ...]] = []

    class FakeTtkWidget:
        def state(self, statespec: tuple[str, ...]) -> None:
            state_calls.append(statespec)

    widget = FakeTtkWidget()
    _set_ttk_enabled(widget, True)
    _set_ttk_enabled(widget, False)

    assert state_calls == [("!disabled",), ("disabled",)]


def test_gui_run_continue_command_uses_current_python_and_batch_id() -> None:
    command = build_run_continue_command(42)

    assert command[1:] == ["-m", "ig_orchestrator", "run_continue", "--batch-id", "42"]


def test_gui_dry_run_option_is_placed_before_subcommand() -> None:
    command = build_run_continue_command(42, dry_run=True)

    assert command[1:] == [
        "-m",
        "ig_orchestrator",
        "--dry-run",
        "run_continue",
        "--batch-id",
        "42",
    ]


def test_gui_manual_rename_command_uses_global_start_date() -> None:
    script_path = Path(r"D:\tools\ManualRenameFiles\main.py")

    command = build_manual_rename_command("2026-07-16", script_path=script_path)

    assert command[1:] == [
        str(script_path),
        "--newRename",
        "--startNowDate",
        "2026-07-16",
        "--no-duplicated",
        "--move-renamed",
    ]


def test_gui_manual_rename_command_adds_all_new_accounts_in_order() -> None:
    script_path = Path(r"D:\tools\ManualRenameFiles\main.py")

    command = build_manual_rename_command(
        "2026-07-16",
        script_path=script_path,
        new_accounts=(
            NewAccountRenameParameters(
                username="ddmarii",
                owner_id="436651863",
                start_init_date="2025-12-14",
                destination_path=r"G:\4K Stogram\00.MODELS-D",
            ),
            NewAccountRenameParameters(
                username="second_account",
                owner_id="987654321",
                start_init_date="2026-01-10",
                destination_path=r"G:\4K Stogram\00.MODELS-C",
            ),
        ),
    )

    assert command[1:] == [
        str(script_path),
        "--newRename",
        "--startNowDate",
        "2026-07-16",
        "--new-account",
        "ddmarii",
        "436651863",
        "2025-12-14",
        r"G:\4K Stogram\00.MODELS-D",
        "--new-account",
        "second_account",
        "987654321",
        "2026-01-10",
        r"G:\4K Stogram\00.MODELS-C",
        "--no-duplicated",
        "--move-renamed",
    ]


def test_gui_rename_parameters_only_include_checked_new_accounts() -> None:
    parameters = _new_account_rename_parameters(
        [
            AccountDraft(username="existing", is_new_account=False),
            AccountDraft(
                username="new_user",
                is_new_account=True,
                owner_id="123",
                start_init_date="2026-01-01",
                destination_path=r"G:\Models",
            ),
        ]
    )

    assert parameters == (
        NewAccountRenameParameters(
            username="new_user",
            owner_id="123",
            start_init_date="2026-01-01",
            destination_path=r"G:\Models",
        ),
    )


def test_gui_console_prefixes_every_line_with_millisecond_timestamp() -> None:
    formatted = _timestamp_console_text(
        "Primer evento\nSegundo evento\n",
        now=datetime(2026, 6, 21, 17, 48, 57, 983000),
    )

    assert formatted == (
        "2026-06-21 17:48:57.983 Primer evento\n"
        "2026-06-21 17:48:57.983 Segundo evento\n"
    )


def test_gui_draft_rejects_account_without_stories_or_urls(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="empty_account",
        default_start_now_date="2026-07-06",
        accounts=[AccountDraft(username="empty_user")],
    )

    with connect(db_path) as connection:
        with pytest.raises(BatchDraftValidationError, match="enable stories"):
            save_batch_draft(draft, connection)


@pytest.mark.parametrize(
    ("field_name", "field_value", "error"),
    [
        ("owner_id", "", "ownerId is required"),
        ("start_init_date", "", "startInitDate is required"),
        ("destination_path", "", "path is required"),
    ],
)
def test_gui_new_account_requires_rename_fields(
    field_name: str,
    field_value: str,
    error: str,
) -> None:
    values = {
        "owner_id": "436651863",
        "start_init_date": "2025-12-14",
        "destination_path": r"G:\4K Stogram\00.MODELS-D",
    }
    values[field_name] = field_value
    account = AccountDraft(
        username="ddmarii",
        is_new_account=True,
        download_stories=True,
        **values,
    )

    with pytest.raises(BatchDraftValidationError, match=error):
        validate_batch_draft(
            BatchDraft(
                batch_name="new_account_missing_field",
                default_start_now_date="2026-07-16",
                accounts=[account],
            )
        )


def test_gui_new_account_is_saved_to_batch_and_catalog(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="new_account_batch",
        default_start_now_date="2026-07-16",
        accounts=[
            AccountDraft(
                username="@ddmarii",
                download_stories=True,
                is_new_account=True,
                owner_id="436651863",
                start_init_date="2025-12-14",
                destination_path=r"G:\4K Stogram\00.MODELS-D",
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        assert [account.username for account in result.accounts] == ["ddmarii"]

        catalog_record = AccountHistoryRepository(connection).get_by_user_name("ddmarii")
        assert catalog_record is not None
        assert catalog_record.user_ig_id == "436651863"
        assert catalog_record.field1 == r"G:\4K Stogram\00.MODELS-D"
        assert catalog_record.field2 == "2025-12-14"

        catalog_entry = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_entries()[0]
        assert catalog_entry.owner_id == "436651863"
        assert catalog_entry.destination_path == r"G:\4K Stogram\00.MODELS-D"
        assert catalog_entry.start_init_date == "2025-12-14"

        stored = connection.execute(
            "SELECT * FROM accounts WHERE batch_id = ?",
            (result.batch.id,),
        ).fetchone()
        assert stored["is_new_account"] == 1
        assert stored["rename_owner_id"] == "436651863"
        assert stored["rename_start_init_date"] == "2025-12-14"
        assert stored["rename_destination_path"] == r"G:\4K Stogram\00.MODELS-D"


def test_gui_lists_and_recovers_pending_batch_from_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="recover_me",
        default_start_now_date="2026-07-18",
        accounts=[
            AccountDraft(
                username="new_recovered_user",
                download_stories=True,
                urls=["https://www.instagram.com/reel/RECOVER123/"],
                start_now_date="2026-07-17",
                is_new_account=True,
                owner_id="9988",
                start_init_date="2025-12-01",
                destination_path=r"G:\Models",
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        managed = list_managed_batches(connection)

        assert [(item.batch_id, item.batch_name) for item in managed] == [
            (result.batch.id, "recover_me")
        ]
        assert managed[0].status == "DRAFT"
        assert managed[0].total_accounts == 1
        assert list_pending_batches(connection) == []

        recovered = load_batch_draft(connection, result.batch.id)
        assert recovered == draft


def test_gui_saved_draft_can_be_updated_then_is_locked_when_executed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    original = BatchDraft(
        batch_name="night_batch",
        default_start_now_date="2026-07-22",
        accounts=[
            AccountDraft(
                username="large_account",
                urls=["https://www.instagram.com/reel/LARGE1/"],
            )
        ],
    )
    updated = BatchDraft(
        batch_name="night_batch_updated",
        default_start_now_date="2026-07-23",
        accounts=[
            AccountDraft(
                username="large_account",
                download_stories=True,
                urls=["https://www.instagram.com/reel/LARGE2/"],
                start_now_date="2026-07-23",
            )
        ],
    )

    with connect(db_path) as connection:
        created = save_batch_draft(original, connection)
        saved = save_batch_draft(updated, connection, batch_id=created.batch.id)

        assert saved.batch.id == created.batch.id
        assert saved.batch.status is InputBatchStatus.DRAFT
        assert load_batch_draft(connection, saved.batch.id) == updated

        activate_draft_batch(connection, saved.batch.id)
        assert BatchRepository(connection).get_by_id(saved.batch.id).status is InputBatchStatus.IMPORTED
        assert list_pending_batches(connection)[0].batch_id == saved.batch.id
        with pytest.raises(ValueError, match="Only saved DRAFT"):
            save_batch_draft(original, connection, batch_id=saved.batch.id)
        with pytest.raises(ValueError, match="Only saved DRAFT"):
            delete_draft_batch(connection, saved.batch.id)


def test_gui_can_delete_only_unexecuted_saved_draft(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="delete_later",
        default_start_now_date="2026-07-22",
        accounts=[AccountDraft(username="unused", download_stories=True)],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        delete_draft_batch(connection, result.batch.id)

        assert BatchRepository(connection).get_by_id(result.batch.id) is None
        assert list_managed_batches(connection) == []


def test_gui_recovered_batch_uses_persisted_processing_order(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="processing_order",
        default_start_now_date="2026-07-22",
        accounts=[
            AccountDraft(
                username="three_urls",
                urls=[
                    "https://www.instagram.com/reel/ORDER1/",
                    "https://www.instagram.com/reel/ORDER2/",
                    "https://www.instagram.com/reel/ORDER3/",
                ],
            ),
            AccountDraft(username="story_only", download_stories=True),
            AccountDraft(
                username="one_url",
                urls=["https://www.instagram.com/reel/ORDER4/"],
            ),
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        recovered = load_batch_draft(connection, result.batch.id)

    assert [account.username for account in recovered.accounts] == [
        "story_only",
        "one_url",
        "three_urls",
    ]


def test_gui_resume_columns_are_added_to_an_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE input_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                source_file TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE accounts (
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
                updated_at TEXT NOT NULL
            );
            """
        )

        apply_migrations(connection)

        batch_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(input_batches)")
        }
        account_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
        }
        assert "default_start_now_date" in batch_columns
        assert {
            "is_new_account",
            "rename_owner_id",
            "rename_start_init_date",
            "rename_destination_path",
        } <= account_columns


def test_gui_runtime_progress_and_manual_finish(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="runtime_batch",
        default_start_now_date="2026-07-18",
        accounts=[
            AccountDraft(
                username="runtime_user",
                urls=[
                    "https://www.instagram.com/reel/RUNTIME1/",
                    "https://www.instagram.com/reel/RUNTIME2/",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        UrlJobRepository(connection).update_status(jobs[0].id, UrlJobStatus.COMPLETED)
        UrlJobRepository(connection).update_error(
            jobs[1].id,
            status=UrlJobStatus.RETRY_PENDING,
            last_error="temporary",
            last_error_type="TEMPORARY",
            non_retryable=False,
        )
        AccountRepository(connection).update_status(account.id, AccountStatus.PARTIAL)

        progress = get_account_runtime_progress(connection, result.batch.id)
        assert progress[0].completed_items == 1
        assert progress[0].retry_items == 1

        mark_batch_interrupted(connection, result.batch.id)
        assert BatchRepository(connection).get_by_id(result.batch.id).status is InputBatchStatus.PARTIAL
        assert list_pending_batches(connection)

        finish_batch(connection, result.batch.id)
        assert BatchRepository(connection).get_by_id(result.batch.id).status is InputBatchStatus.COMPLETED
        assert list_pending_batches(connection) == []


def test_gui_manual_account_removal_marks_non_terminal_urls_and_account_failed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="remove_account",
        default_start_now_date="2026-07-22",
        accounts=[
            AccountDraft(
                username="blocked_user",
                urls=[
                    "https://www.instagram.com/reel/BLOCKED1/",
                    "https://www.instagram.com/reel/BLOCKED2/",
                ],
            )
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        UrlJobRepository(connection).update_status(jobs[0].id, UrlJobStatus.COMPLETED)

        affected = fail_account_manually(
            connection,
            batch_id=result.batch.id,
            account_id=account.id,
        )
        stored_account = AccountRepository(connection).get_by_id(account.id)
        stored_jobs = UrlJobRepository(connection).list_by_account(account.id)

    assert affected == 1
    assert stored_account.status is AccountStatus.FAILED
    assert stored_jobs[0].status is UrlJobStatus.COMPLETED
    assert stored_jobs[1].status is UrlJobStatus.FAILED_FINAL
    assert stored_jobs[1].last_error_type == "MANUAL_ACCOUNT_REMOVAL"
    assert stored_jobs[1].non_retryable is True


def test_gui_manual_completion_closes_stuck_account_and_enables_rename(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="stuck_account",
        default_start_now_date="2026-07-22",
        accounts=[
            AccountDraft(
                username="stuck_user",
                urls=["https://www.instagram.com/reel/STUCK1/"],
            )
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        activate_draft_batch(connection, result.batch.id)
        mark_batch_interrupted(connection, result.batch.id)
        RunRepository(connection).create(
            RunSummary(status=RunStatus.PROCESSING, total_urls=1, summary="Processing batch"),
            batch_id=result.batch.id,
        )
        account = result.accounts[0]

        affected = complete_account_manually(
            connection,
            batch_id=result.batch.id,
            account_id=account.id,
        )
        stored_job = UrlJobRepository(connection).list_by_account(account.id)[0]

        assert affected == 1
        assert AccountRepository(connection).get_by_id(account.id).status is AccountStatus.COMPLETED
        assert stored_job.status is UrlJobStatus.FAILED_FINAL
        assert stored_job.last_error_type == "MANUAL_ACCOUNT_COMPLETION"
        assert BatchRepository(connection).get_by_id(result.batch.id).status is InputBatchStatus.COMPLETED
        assert is_batch_ready_for_rename(connection, result.batch.id) is True


def test_gui_draft_rejects_duplicate_batch_name(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="duplicate_gui_batch",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="first_user",
                urls=["https://www.instagram.com/reel/ABC123xyz/"],
            )
        ],
    )

    with connect(db_path) as connection:
        save_batch_draft(draft, connection)
        assert BatchRepository(connection).get_by_name("duplicate_gui_batch") is not None

        with pytest.raises(DuplicateBatchNameError, match="already exists"):
            save_batch_draft(draft, connection)


def test_gui_url_normalization_accepts_quoted_comma_lists() -> None:
    assert normalize_url_lines(
        [
            '"https://www.instagram.com/p/DaGP2rHuY0P/",',
            '"https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",',
            '"https://www.instagram.com/p/DaO63b4t9_h/"',
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
        "https://www.instagram.com/p/DaO63b4t9_h/",
    ]


def test_gui_url_normalization_accepts_trailing_comma() -> None:
    assert normalize_url_lines(
        [
            '"https://www.instagram.com/p/DaGP2rHuY0P/",',
            '"https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",',
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
    ]


def test_gui_url_normalization_keeps_clean_line_lists() -> None:
    assert normalize_url_lines(
        [
            "https://www.instagram.com/p/DaGP2rHuY0P/",
            "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
    ]


def test_gui_url_normalization_removes_duplicate_clean_urls() -> None:
    assert normalize_url_lines(
        [
            "https://www.instagram.com/p/DaGP2rHuY0P/",
            '"https://www.instagram.com/p/DaGP2rHuY0P/",',
            "'https://www.instagram.com/p/DaGP2rHuY0P/'",
            "https://www.instagram.com/reel/ABC123xyz/",
        ]
    ) == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/reel/ABC123xyz/",
    ]


def test_gui_inspection_counts_duplicates_after_cleaning() -> None:
    summary = inspect_account_draft(
        AccountDraft(
            username="duplicate_user",
            urls=[
                "https://www.instagram.com/p/DaGP2rHuY0P/",
                '"https://www.instagram.com/p/DaGP2rHuY0P/",',
                "'https://www.instagram.com/p/DaGP2rHuY0P/'",
            ],
        ),
        default_start_now_date="2026-07-11",
    )

    assert summary.url_count == 1
    assert summary.duplicate_count == 2


def test_gui_normalization_treats_post_and_reel_with_same_shortcode_as_duplicate() -> None:
    assert normalize_url_lines(
        [
            "https://www.instagram.com/p/DWl1cUrD4gW/",
            "https://www.instagram.com/reel/DWl1cUrD4gW/",
            "https://www.instagram.com/reel/OTHER123/",
        ]
    ) == [
        "https://www.instagram.com/p/DWl1cUrD4gW/",
        "https://www.instagram.com/reel/OTHER123/",
    ]


def test_gui_inspection_counts_equivalent_post_and_reel_as_duplicate() -> None:
    summary = inspect_account_draft(
        AccountDraft(
            username="duplicate_format_user",
            urls=[
                "https://www.instagram.com/p/DWl1cUrD4gW/",
                "https://www.instagram.com/reel/DWl1cUrD4gW/",
            ],
        ),
        default_start_now_date="2026-07-11",
    )

    assert summary.url_count == 1
    assert summary.duplicate_count == 1


def test_gui_draft_validation_uses_comma_url_normalization(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="comma_urls",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="comma_user",
                urls=[
                    '"https://www.instagram.com/p/DaGP2rHuY0P/",',
                    '"https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",',
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = AccountRepository(connection).list_by_batch(result.batch.id)[0]

        jobs = UrlJobRepository(connection).list_by_account(account.id)

    assert [job.url for job in jobs] == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/p/DaLSvqrFK3P/?img_index=1",
    ]


def test_gui_draft_validation_removes_duplicate_clean_urls(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="duplicate_clean_urls",
        default_start_now_date="2026-07-06",
        accounts=[
            AccountDraft(
                username="duplicate_user",
                urls=[
                    "https://www.instagram.com/p/DaGP2rHuY0P/",
                    '"https://www.instagram.com/p/DaGP2rHuY0P/",',
                    "https://www.instagram.com/reel/ABC123xyz/",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = AccountRepository(connection).list_by_batch(result.batch.id)[0]

        jobs = UrlJobRepository(connection).list_by_account(account.id)

    assert [job.url for job in jobs] == [
        "https://www.instagram.com/p/DaGP2rHuY0P/",
        "https://www.instagram.com/reel/ABC123xyz/",
    ]


def test_gui_initial_batch_name_uses_latest_executed_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        older = save_batch_draft(
            BatchDraft(
                batch_name="older_batch",
                default_start_now_date="2026-07-06",
                accounts=[
                    AccountDraft(
                        username="older_user",
                        urls=["https://www.instagram.com/reel/ABC123xyz/"],
                    )
                ],
            ),
            connection,
        ).batch
        newer = save_batch_draft(
            BatchDraft(
                batch_name="newer_batch",
                default_start_now_date="2026-07-06",
                accounts=[
                    AccountDraft(
                        username="newer_user",
                        urls=["https://www.instagram.com/reel/DEF123xyz/"],
                    )
                ],
            ),
            connection,
        ).batch
        run_repository = RunRepository(connection)
        run_repository.create(
            RunSummary(status=RunStatus.COMPLETED),
            batch_id=newer.id,
            started_at=datetime(2026, 7, 7, 9, 0, tzinfo=timezone.utc),
        )
        run_repository.create(
            RunSummary(status=RunStatus.COMPLETED),
            batch_id=older.id,
            started_at=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
        )

        assert _latest_executed_batch_name(connection) == "older_batch"


def test_gui_initial_batch_name_falls_back_to_latest_saved_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        save_batch_draft(
            BatchDraft(
                batch_name="saved_batch",
                default_start_now_date="2026-07-06",
                accounts=[
                    AccountDraft(
                        username="saved_user",
                        urls=["https://www.instagram.com/reel/ABC123xyz/"],
                    )
                ],
            ),
            connection,
        )

        assert _latest_executed_batch_name(connection) == "saved_batch"
