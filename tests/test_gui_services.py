from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk

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
    _BATCH_COLUMNS,
    InstagramOrchestratorApp,
    _account_display_status,
    _batch_column_samples,
    _batch_mode_details,
    batch_username_matches_filter,
    catalog_focus_username,
    _catalog_entry_colors,
    _catalog_width_chars,
    filter_batch_accounts,
    _half_screen_geometry,
    _instagram_profile_url,
    _open_chrome_tab,
    _play_completion_sound,
    _set_ttk_enabled,
    _latest_executed_batch_name,
    _new_account_rename_parameters,
    _sort_accounts_by_username,
    stories_cell_text,
    _timestamp_console_text,
    _username_heading_title,
)
from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogEntry,
    AccountCatalogService,
    filter_catalog_entries,
    list_usernames_active_on_date,
)
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
    list_account_problem_urls,
    list_historical_batches,
    list_managed_batches,
    list_pending_batches,
    load_batch_draft,
    mark_batch_executed_elsewhere,
    mark_batch_interrupted,
    resolve_account_download_folder,
)
from ig_orchestrator.gui.batch_transfer_service import (
    BatchTransferError,
    export_batch_payload,
    import_batch_from_payload,
)
from ig_orchestrator.gui.process_runner import (
    NewAccountRenameParameters,
    build_manual_rename_command,
    build_run_continue_command,
    format_command_for_shell,
    format_manual_rename_command_preview,
)
from ig_orchestrator.gui.rename_folder_status import (
    decide_rename_completion,
    has_unmoved_account_folders,
    list_unmoved_account_folders,
)
from ig_orchestrator.input import DuplicateBatchNameError
from ig_orchestrator.models import (
    AccountHistoryStatus,
    AccountStatus,
    InputBatchStatus,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.settings import Settings


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


def test_catalog_disabled_account_is_shown_last_even_if_json_contains_it(
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
        entries = service.list_entries()
        stored = AccountHistoryRepository(connection).get_by_user_name("hidden_user")

    assert [entry.username for entry in entries] == ["hidden_user"]
    assert entries[0].status is AccountHistoryStatus.DISABLED
    assert stored is not None
    assert stored.status.value == "DISABLED"


def test_catalog_orders_favorites_paths_normal_inactive_and_disabled(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        history = AccountHistoryRepository(connection)
        for username, destination in (
            ("normal_z", r"G:\\Z"),
            ("normal_a2", r"G:\\A"),
            ("normal_a1", r"G:\\A"),
            ("ungrouped", ""),
            ("favorite_z", r"G:\\Z"),
            ("favorite_a", r"G:\\A"),
            ("inactive_b", ""),
            ("inactive_a", r"G:\\A"),
            ("disabled_b", r"G:\\A"),
            ("disabled_a", ""),
        ):
            history.update_rename_metadata(
                username,
                owner_id=username,
                destination_path=destination,
                start_init_date="2026-01-01",
            )
        history.set_favorite("favorite_z", favorite=True)
        history.set_favorite("favorite_a", favorite=True)
        history.set_inactive("inactive_b")
        history.set_inactive("inactive_a")
        history.update_status("disabled_b", AccountHistoryStatus.DISABLED)
        history.update_status("disabled_a", AccountHistoryStatus.DISABLED)

        entries = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        ).list_entries()

    assert [entry.username for entry in entries] == [
        "favorite_a",
        "favorite_z",
        "normal_a1",
        "normal_a2",
        "normal_z",
        "ungrouped",
        "inactive_a",
        "inactive_b",
        "disabled_a",
        "disabled_b",
    ]


def test_catalog_colors_follow_favorite_and_account_status() -> None:
    assert _catalog_entry_colors(AccountCatalogEntry("normal")) == {}
    assert _catalog_entry_colors(
        AccountCatalogEntry("favorite", is_favorite=True)
    ) == {"background": "#d9ead3"}
    assert _catalog_entry_colors(
        AccountCatalogEntry("inactive", status=AccountHistoryStatus.INACTIVE)
    ) == {"background": "#fff2cc"}
    assert _catalog_entry_colors(
        AccountCatalogEntry("in_batch_favorite", is_favorite=True),
        in_batch=True,
    ) == {"background": "#f5c08c"}
    assert _catalog_entry_colors(
        AccountCatalogEntry(
            "disabled",
            status=AccountHistoryStatus.DISABLED,
            is_favorite=True,
        ),
        in_batch=True,
    ) == {"background": "#f4cccc"}
    assert _catalog_entry_colors(
        AccountCatalogEntry("today_user", is_favorite=True),
        today=True,
    ) == {"background": "#fff59d"}
    assert _catalog_entry_colors(
        AccountCatalogEntry("today_in_batch"),
        in_batch=True,
        today=True,
    ) == {"background": "#f5c08c"}
    assert _catalog_entry_colors(
        AccountCatalogEntry("today_inactive", status=AccountHistoryStatus.INACTIVE),
        today=True,
    ) == {"background": "#fff59d"}


def test_list_usernames_active_on_date_includes_added_or_downloaded_today(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    today = date.today()
    yesterday = today - timedelta(days=1)
    yesterday_dt = datetime(
        yesterday.year, yesterday.month, yesterday.day, 15, 0, tzinfo=timezone.utc
    )

    with connect(db_path) as connection:
        added_today = save_batch_draft(
            BatchDraft(
                batch_name="added_today",
                default_start_now_date=today.isoformat(),
                accounts=[
                    AccountDraft(
                        username="AddedToday",
                        urls=["https://www.instagram.com/reel/TODAY1/"],
                    )
                ],
            ),
            connection,
        )
        added_yesterday = save_batch_draft(
            BatchDraft(
                batch_name="added_yesterday",
                default_start_now_date=yesterday.isoformat(),
                accounts=[
                    AccountDraft(
                        username="added_yesterday",
                        urls=["https://www.instagram.com/reel/YDAY1/"],
                    ),
                    AccountDraft(
                        username="downloaded_today",
                        urls=["https://www.instagram.com/reel/RUN1/"],
                    ),
                    AccountDraft(
                        username="dry_run_today",
                        urls=["https://www.instagram.com/reel/DRY1/"],
                    ),
                ],
            ),
            connection,
        )
        yesterday_accounts = {
            account.username: account.id for account in added_yesterday.accounts
        }
        connection.execute(
            "UPDATE accounts SET created_at = ?, updated_at = ? WHERE batch_id = ?",
            (
                yesterday_dt.isoformat(),
                yesterday_dt.isoformat(),
                added_yesterday.batch.id,
            ),
        )
        RunRepository(connection).create(
            RunSummary(
                status=RunStatus.COMPLETED,
                total_urls=1,
                completed_urls=1,
                summary="Processed downloaded_today",
            ),
            batch_id=added_yesterday.batch.id,
            account_id=yesterday_accounts["downloaded_today"],
        )
        RunRepository(connection).create(
            RunSummary(
                status=RunStatus.COMPLETED,
                total_urls=1,
                completed_urls=1,
                summary="Dry-run batch added_yesterday: would process 1 accounts",
            ),
            batch_id=added_yesterday.batch.id,
            account_id=yesterday_accounts["dry_run_today"],
        )
        connection.commit()

        active = list_usernames_active_on_date(connection, today)

    assert "addedtoday" in active
    assert "downloaded_today" in active
    assert "added_yesterday" not in active
    assert "dry_run_today" not in active
    assert added_today.batch.id is not None


def test_catalog_filter_exact_match_returns_same_folder_peers() -> None:
    folder = r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva"
    other_folder = r"G:\4K Stogram\00.MODELS-A"
    entries = [
        AccountCatalogEntry("alpha_peer", destination_path=folder),
        AccountCatalogEntry("lerabuns", destination_path=folder),
        AccountCatalogEntry("zeta_peer", destination_path=folder),
        AccountCatalogEntry("outsider", destination_path=other_folder),
        AccountCatalogEntry("lerabuns_extra", destination_path=other_folder),
    ]

    filtered = filter_catalog_entries(entries, "lerabuns")

    # Exact match first, then remaining folder peers in original order.
    assert [entry.username for entry in filtered] == [
        "lerabuns",
        "alpha_peer",
        "zeta_peer",
    ]


def test_catalog_filter_exact_match_is_case_insensitive() -> None:
    folder = r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva"
    entries = [
        AccountCatalogEntry("leraBuns", destination_path=folder),
        AccountCatalogEntry("peer_one", destination_path=folder),
    ]

    filtered = filter_catalog_entries(entries, "LERABUNS")

    assert [entry.username for entry in filtered] == ["leraBuns", "peer_one"]


def test_catalog_filter_exact_match_without_path_returns_only_match() -> None:
    entries = [
        AccountCatalogEntry("solo_user"),
        AccountCatalogEntry("solo_user_extra", destination_path=r"G:\Other"),
        AccountCatalogEntry("other"),
    ]

    filtered = filter_catalog_entries(entries, "solo_user")

    assert [entry.username for entry in filtered] == ["solo_user"]


def test_catalog_filter_substring_without_exact_match() -> None:
    entries = [
        AccountCatalogEntry("lera", destination_path=r"G:\A"),
        AccountCatalogEntry("lerabuns", destination_path=r"G:\B"),
        AccountCatalogEntry("leraferal", destination_path=r"G:\C"),
        AccountCatalogEntry("other"),
    ]

    filtered = filter_catalog_entries(entries, "lera")

    # "lera" is an exact match of the first username, so folder peers of G:\A
    # would apply; only "lera" shares that path here.
    assert [entry.username for entry in filtered] == ["lera"]

    partial = filter_catalog_entries(entries, "bun")
    assert [entry.username for entry in partial] == ["lerabuns"]


def test_catalog_filter_empty_query_returns_all() -> None:
    entries = [
        AccountCatalogEntry("a"),
        AccountCatalogEntry("b"),
    ]
    assert filter_catalog_entries(entries, "") == entries
    assert filter_catalog_entries(entries, "   ") == entries


def test_catalog_focus_username_selects_exact_match_among_folder_peers() -> None:
    folder = r"G:\4K Stogram\00.FAVORITES\Valeria-Makusheva"
    filtered = [
        AccountCatalogEntry("lerabuns", destination_path=folder),
        AccountCatalogEntry("alpha_peer", destination_path=folder),
        AccountCatalogEntry("zeta_peer", destination_path=folder),
    ]

    assert catalog_focus_username("lerabuns", filtered, previous="zeta_peer") == "lerabuns"
    assert catalog_focus_username("LERABUNS", filtered, previous=None) == "lerabuns"


def test_catalog_focus_username_keeps_previous_when_query_empty() -> None:
    filtered = [
        AccountCatalogEntry("alpha"),
        AccountCatalogEntry("beta"),
    ]
    assert catalog_focus_username("", filtered, previous="beta") == "beta"
    assert catalog_focus_username("   ", filtered, previous="missing") is None
    assert catalog_focus_username("zz", [], previous="alpha") is None


def test_catalog_focus_username_selects_single_substring_match() -> None:
    filtered = [AccountCatalogEntry("lerabuns")]
    assert catalog_focus_username("bun", filtered, previous=None) == "lerabuns"


def test_filter_batch_accounts_matches_username_substring() -> None:
    accounts = [
        AccountDraft(username="alpha", download_stories=True),
        AccountDraft(username="lerabuns", download_stories=False),
        AccountDraft(username="beta", download_stories=True),
    ]

    visible = filter_batch_accounts(accounts, "lera")
    assert [(index, account.username) for index, account in visible] == [
        (1, "lerabuns")
    ]
    assert filter_batch_accounts(accounts, "") == list(enumerate(accounts))
    assert filter_batch_accounts(accounts, "   ") == list(enumerate(accounts))
    assert batch_username_matches_filter("lerabuns", "BUNS")
    assert not batch_username_matches_filter("alpha", "lera")


def test_stories_cell_text_uses_icons() -> None:
    assert stories_cell_text(True) == "✅"
    assert stories_cell_text(False) == "❌"


def test_catalog_enable_reactivates_disabled_account(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        service = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        )
        service.disable("paused_user")
        disabled = next(
            entry for entry in service.list_entries() if entry.username == "paused_user"
        )
        service.enable("paused_user")
        enabled = next(
            entry for entry in service.list_entries() if entry.username == "paused_user"
        )

    assert disabled.status is AccountHistoryStatus.DISABLED
    assert enabled.status is AccountHistoryStatus.ENABLED


def test_catalog_favorite_tag_can_be_added_and_removed(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        service = AccountCatalogService(
            connection,
            batch_json_path=tmp_path / "missing.json",
        )
        service.set_favorite("toggle_user", favorite=True)
        favorite = service.list_entries()[0]
        service.set_favorite("toggle_user", favorite=False)
        normal = service.list_entries()[0]

    assert favorite.is_favorite is True
    assert favorite.status is AccountHistoryStatus.ENABLED
    assert normal.is_favorite is False
    assert normal.status is AccountHistoryStatus.ENABLED


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


def test_gui_catalog_single_selection_only_loads_username() -> None:
    applied_dates: list[bool] = []

    class FakeCatalogList:
        @staticmethod
        def curselection() -> tuple[int]:
            return (0,)

        @staticmethod
        def get(index: int) -> str:
            assert index == 0
            return "single_click_user"

    class FakeStringVar:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    app = object.__new__(InstagramOrchestratorApp)
    app.catalog_list = FakeCatalogList()
    app.username_var = FakeStringVar()
    app._apply_catalog_date = lambda: applied_dates.append(True)

    app._load_catalog()

    assert app.username_var.value == "single_click_user"
    assert applied_dates == [True]


def test_gui_catalog_silent_tree_select_does_not_load_editor() -> None:
    applied_dates: list[bool] = []

    class FakeCatalogList:
        @staticmethod
        def curselection() -> tuple[int]:
            return (0,)

        @staticmethod
        def get(index: int) -> str:
            return "silent_user"

    class FakeStringVar:
        value = "kept"

        def set(self, value: str) -> None:
            self.value = value

    app = object.__new__(InstagramOrchestratorApp)
    app.catalog_list = FakeCatalogList()
    app.username_var = FakeStringVar()
    app._catalog_silent_token = 1
    app._apply_catalog_date = lambda: applied_dates.append(True)

    app._load_catalog()

    assert app.username_var.value == "kept"
    assert applied_dates == []


def test_gui_treeview_state_uses_ttk_state_api() -> None:
    state_calls: list[tuple[str, ...]] = []

    class FakeTtkWidget:
        def state(self, statespec: tuple[str, ...]) -> None:
            state_calls.append(statespec)

    widget = FakeTtkWidget()
    _set_ttk_enabled(widget, True)
    _set_ttk_enabled(widget, False)

    assert state_calls == [("!disabled",), ("disabled",)]


def test_gui_batch_columns_follow_compact_requested_order_and_catalog_width() -> None:
    usernames = ["short", "the_longest_catalog_account"]

    assert _BATCH_COLUMNS == (
        ("username", "Username"),
        ("urls", "URLs"),
        ("status", "Estado"),
        ("stories", "Stories"),
        ("start_date", "Start date"),
    )
    assert _catalog_width_chars(usernames) == len("the_longest_catalog_account")
    assert _batch_column_samples(usernames) == {
        "username": "the_longest_catalog_account",
        "urls": "9999",
        "status": "Completada 9999/9999",
        "stories": "Stories",
        "start_date": "0000-00-00",
    }


def test_gui_username_heading_and_sort_helpers() -> None:
    accounts = [
        AccountDraft(username="zeta", download_stories=False),
        AccountDraft(username="Alpha", download_stories=True),
        AccountDraft(username="beta", download_stories=False),
    ]

    assert _username_heading_title(None) == "Username"
    assert _username_heading_title(True) == "Username ▲"
    assert _username_heading_title(False) == "Username ▼"
    assert [
        item.username
        for item in _sort_accounts_by_username(accounts, ascending=True)
    ] == ["Alpha", "beta", "zeta"]
    assert [
        item.username
        for item in _sort_accounts_by_username(accounts, ascending=False)
    ] == ["zeta", "beta", "Alpha"]


def test_gui_save_selection_persists_subset_and_leaves_remainder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    class FakeVar:
        def __init__(self, value: str = "") -> None:
            self.value = value

        def get(self) -> str:
            return self.value

        def set(self, value: str) -> None:
            self.value = value

    class FakeRunner:
        @staticmethod
        def is_running() -> bool:
            return False

    class FakeTree:
        def __init__(self) -> None:
            self._selection = ("0", "2")
            self.heading_calls: list[tuple[object, ...]] = []

        def selection(self) -> tuple[str, ...]:
            return self._selection

        def selection_remove(self, *items: str) -> None:
            return None

        def heading(self, *_args, **_kwargs) -> None:
            self.heading_calls.append((_args, _kwargs))

    with connect(db_path) as connection:
        app = object.__new__(InstagramOrchestratorApp)
        app.process_runner = FakeRunner()
        app.connection = connection
        app.settings = None
        app.batch_name_var = FakeVar("lote_seleccion")
        app.default_date_var = FakeVar("2026-08-05")
        app.accounts = [
            AccountDraft(
                username="one",
                download_stories=True,
                urls=["https://www.instagram.com/p/AAA/"],
                start_now_date="2026-08-05",
            ),
            AccountDraft(
                username="two",
                download_stories=False,
                urls=["https://www.instagram.com/p/BBB/"],
                start_now_date="2026-08-05",
            ),
            AccountDraft(
                username="three",
                download_stories=False,
                urls=["https://www.instagram.com/p/CCC/"],
                start_now_date="2026-08-05",
            ),
        ]
        app.saved_batch_id = None
        app.saved_draft_signature = None
        app.active_batch_id = 99
        app.runtime_progress = {"x": object()}
        app.selected_index = 0
        app._username_sort_ascending = True
        app.tree = FakeTree()
        app._clear_editor = lambda: None
        app._refresh_table = lambda: None
        app._refresh_catalog = lambda: None
        app._update_batch_context = lambda: None
        app._update_pending_button_label = lambda: None
        app._write_console = lambda _text: None
        app._set_status = lambda _text: None
        monkeypatch.setattr(
            "ig_orchestrator.gui.app.messagebox.askyesno",
            lambda *_args, **_kwargs: True,
        )
        monkeypatch.setattr(
            "ig_orchestrator.gui.app.messagebox.showinfo",
            lambda *_args, **_kwargs: None,
        )

        app._save_selected_accounts_as_batch()

        batches = connection.execute(
            "SELECT id, batch_name, status FROM input_batches"
        ).fetchall()
        usernames = {
            str(row["username"])
            for row in connection.execute("SELECT username FROM accounts").fetchall()
        }

    assert len(batches) == 1
    assert batches[0]["batch_name"] == "lote_seleccion"
    assert batches[0]["status"] == "DRAFT"
    assert usernames == {"one", "three"}
    assert [account.username for account in app.accounts] == ["two"]
    assert app.saved_batch_id is None
    assert app.active_batch_id is None
    assert app.runtime_progress == {}
    assert app.batch_name_var.value.startswith("descargas_")


def test_gui_clear_editor_deselects_the_batch_account() -> None:
    removed: list[tuple[str, ...]] = []

    class FakeTree:
        @staticmethod
        def selection() -> tuple[str, ...]:
            return ("3",)

        @staticmethod
        def selection_remove(*items: str) -> None:
            removed.append(items)

    class FakeVar:
        def set(self, _value) -> None:
            pass

    class FakeText:
        def __init__(self) -> None:
            self._state = "normal"

        def cget(self, key: str) -> str:
            if key == "state":
                return self._state
            raise KeyError(key)

        def configure(self, **kwargs) -> None:
            if "state" in kwargs:
                self._state = str(kwargs["state"])

        def delete(self, _start: str, _end: str) -> None:
            pass

    app = object.__new__(InstagramOrchestratorApp)
    app.selected_index = 3
    app.history_readonly = False
    app.tree = FakeTree()
    app.username_var = FakeVar()
    app.account_date_var = FakeVar()
    app.stories_var = FakeVar()
    app.new_account_var = FakeVar()
    app.catalog_update_var = FakeVar()
    app.owner_id_var = FakeVar()
    app.start_init_date_var = FakeVar()
    app.destination_path_var = FakeVar()
    app.urls_text = FakeText()
    app._toggle_catalog_metadata_fields = lambda: None
    app._update_indicators = lambda: None

    app._clear_editor()

    assert app.selected_index is None
    assert removed == [("3",)]


def test_gui_paste_username_uses_first_clipboard_line() -> None:
    class FakeRoot:
        @staticmethod
        def clipboard_get() -> str:
            return "  amberlure_\nignored\n"

    class FakeCombo:
        def __init__(self) -> None:
            self.cursor = None
            self.focused = False

        def icursor(self, index: str) -> None:
            self.cursor = index

        def focus_set(self) -> None:
            self.focused = True

    class FakeVar:
        def __init__(self) -> None:
            self.value = "old"

        def set(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    app = object.__new__(InstagramOrchestratorApp)
    app.root = FakeRoot()
    app.username_var = FakeVar()
    app.username_combo = FakeCombo()

    assert app._paste_username() is True
    assert app.username_var.value == "amberlure_"
    assert app.username_combo.cursor == "end"
    assert app.username_combo.focused is True


def test_gui_paste_username_returns_false_when_clipboard_empty() -> None:
    class FakeRoot:
        @staticmethod
        def clipboard_get() -> str:
            raise tk.TclError("CLIPBOARD")

    class FakeVar:
        def __init__(self) -> None:
            self.value = "keep"

        def set(self, value: str) -> None:
            self.value = value

    app = object.__new__(InstagramOrchestratorApp)
    app.root = FakeRoot()
    app.username_var = FakeVar()
    app.username_combo = object()

    assert app._paste_username() is False
    assert app.username_var.value == "keep"


def test_gui_clear_username_only_clears_the_username_field() -> None:
    class FakeVar:
        def __init__(self, value: str = "") -> None:
            self.value = value

        def set(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    class FakeCombo:
        def __init__(self) -> None:
            self.focused = False

        def focus_set(self) -> None:
            self.focused = True

    app = object.__new__(InstagramOrchestratorApp)
    app.username_var = FakeVar("amberlure_")
    app.username_combo = FakeCombo()
    app.stories_var = FakeVar("1")

    app._clear_username()

    assert app.username_var.value == ""
    assert app.username_combo.focused is True
    assert app.stories_var.value == "1"


def test_gui_paste_and_add_only_upserts_after_a_successful_paste() -> None:
    app = object.__new__(InstagramOrchestratorApp)
    calls: list[str] = []
    app._paste_urls = lambda: True
    app._upsert_account = lambda: calls.append("upsert")

    app._paste_and_upsert()

    assert calls == ["upsert"]
    app._paste_urls = lambda: False
    app._paste_and_upsert()
    assert calls == ["upsert"]


def test_gui_paste_urls_focuses_end_of_text() -> None:
    class FakeRoot:
        @staticmethod
        def clipboard_get() -> str:
            return "https://www.instagram.com/p/ABC/\n"

    class FakeText:
        def __init__(self) -> None:
            self.content = ""
            self.marks: list[tuple[str, str]] = []
            self.seen: list[str] = []
            self.focused = False

        def insert(self, index: str, text: str) -> None:
            self.content += text

        def mark_set(self, name: str, index: str) -> None:
            self.marks.append((name, index))

        def see(self, index: str) -> None:
            self.seen.append(index)

        def focus_set(self) -> None:
            self.focused = True

    app = object.__new__(InstagramOrchestratorApp)
    app.root = FakeRoot()
    app.urls_text = FakeText()
    app._update_indicators = lambda: None

    assert app._paste_urls() is True
    assert "instagram.com/p/ABC" in app.urls_text.content
    assert app.urls_text.marks[-1][1] == "end"
    assert app.urls_text.seen == ["end"]
    assert app.urls_text.focused is True


def test_gui_normalize_urls_focuses_end_of_text() -> None:
    class FakeText:
        def __init__(self) -> None:
            self.content = "https://www.instagram.com/p/ONE/\n"
            self.marks: list[tuple[str, str]] = []
            self.seen: list[str] = []
            self.focused = False

        def get(self, _start: str, _end: str) -> str:
            return self.content

        def delete(self, _start: str, _end: str) -> None:
            self.content = ""

        def insert(self, _index: str, text: str) -> None:
            self.content = text

        def mark_set(self, name: str, index: str) -> None:
            self.marks.append((name, index))

        def see(self, index: str) -> None:
            self.seen.append(index)

        def focus_set(self) -> None:
            self.focused = True

    app = object.__new__(InstagramOrchestratorApp)
    app.urls_text = FakeText()
    app._update_indicators = lambda: None

    app._normalize_urls()

    assert app.urls_text.marks[-1][1] == "end"
    assert app.urls_text.seen == ["end"]
    assert app.urls_text.focused is True


def test_gui_plays_native_completion_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    beeps: list[int] = []
    bells: list[bool] = []
    fake_winsound = SimpleNamespace(
        MB_OK=0,
        MessageBeep=lambda sound: beeps.append(sound),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    root = SimpleNamespace(bell=lambda: bells.append(True))

    _play_completion_sound(root)

    assert beeps == [0]
    assert bells == []


def test_gui_batch_mode_distinguishes_new_and_registered_drafts() -> None:
    assert _batch_mode_details(
        saved_batch_id=None,
        active_batch_id=None,
        batch_name="new_batch",
    ) == (
        "Modo: NUEVO LOTE (sin registrar y sin ID)",
        "Registrar lote nuevo",
        "Ejecutar lote nuevo",
        True,
    )

    context, register_text, execute_text, enabled = _batch_mode_details(
        saved_batch_id=37,
        active_batch_id=37,
        batch_name="saved_batch",
    )

    assert context == (
        "Modo: EDITANDO LOTE REGISTRADO — saved_batch (ID: 37)"
    )
    assert register_text == "Actualizar lote"
    assert execute_text == "Ejecutar lote ID 37"
    assert enabled is True


def test_gui_batch_mode_locks_an_already_started_batch() -> None:
    context, register_text, execute_text, enabled = _batch_mode_details(
        saved_batch_id=None,
        active_batch_id=91,
        batch_name="running_batch",
    )

    assert context == (
        "Modo: LOTE YA INICIADO — running_batch (ID: 91). "
        "Pulsa «Nuevo lote» para registrar otro."
    )
    assert register_text == "Lote no editable"
    assert execute_text == "Ejecución iniciada"
    assert enabled is False


def test_gui_new_batch_detaches_registered_id_and_clears_editors() -> None:
    class FakeRunner:
        @staticmethod
        def is_running() -> bool:
            return False

    class FakeVar:
        def __init__(self, value=None) -> None:
            self.value = value

        def set(self, value) -> None:
            self.value = value

    class FakeTree:
        @staticmethod
        def selection() -> tuple[str, ...]:
            return ("0",)

        @staticmethod
        def selection_remove(*_items: str) -> None:
            return None

    app = object.__new__(InstagramOrchestratorApp)
    app.process_runner = FakeRunner()
    app.saved_batch_id = 12
    app.saved_draft_signature = ("old",)
    app.active_batch_id = 12
    app.runtime_progress = {"old": object()}
    app.batch_ready_for_rename = True
    app.rename_new_accounts = (object(),)
    app.last_run_was_dry_run = True
    app.cancel_requested = True
    app.active_process_kind = "batch"
    app.batch_name_var = FakeVar("old_batch")
    app.default_date_var = FakeVar("2026-07-01")
    app.accounts = [AccountDraft(username="old", download_stories=True)]
    app.selected_index = 0
    app.tree = FakeTree()
    app.account_progress_var = FakeVar()
    app.item_progress_var = FakeVar()
    app.rename_button = type(
        "FakeButton",
        (),
        {"configure": lambda self, **_kwargs: None},
    )()
    calls: list[str] = []
    app._clear_editor = lambda: calls.append("editor")
    app._refresh_table = lambda: calls.append("table")
    app._refresh_catalog = lambda: calls.append("catalog")
    app._update_batch_context = lambda: calls.append("context")
    app._set_status = lambda text: calls.append(text)
    app._write_console = lambda text: calls.append(text)

    app._start_new_batch()

    assert app.saved_batch_id is None
    assert app.active_batch_id is None
    assert app.accounts == []
    assert app.runtime_progress == {}
    assert app.batch_name_var.value.startswith("descargas_")
    assert calls[:4] == ["editor", "table", "catalog", "context"]
    assert "Nuevo lote sin registrar" in calls


def test_gui_delete_all_warns_with_registered_batch_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[tuple[str, str]] = []

    class FakeVar:
        @staticmethod
        def get() -> str:
            return "registered_batch"

    app = object.__new__(InstagramOrchestratorApp)
    app.saved_batch_id = 44
    app.batch_name_var = FakeVar()
    app.accounts = [AccountDraft(username="one", download_stories=True)]
    app.selected_index = 0
    app._refresh_table = lambda: None
    app._refresh_catalog = lambda: None
    app._clear_editor = lambda: None
    app._set_status = lambda _text: None
    monkeypatch.setattr(
        "ig_orchestrator.gui.app.messagebox.askyesno",
        lambda title, message: prompts.append((title, message)) or True,
    )

    app._delete_all_accounts()

    assert app.accounts == []
    assert "Nombre: registered_batch" in prompts[0][1]
    assert "ID: 44" in prompts[0][1]
    assert "Actualizar lote" in prompts[0][1]


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


def test_gui_manual_rename_command_preview_includes_shell_line_and_params() -> None:
    script_path = Path(r"D:\tools\ManualRenameFiles\main.py")
    new_accounts = (
        NewAccountRenameParameters(
            username="ddmarii",
            owner_id="436651863",
            start_init_date="2025-12-14",
            destination_path=r"G:\4K Stogram\00.MODELS-D",
        ),
    )
    command = build_manual_rename_command(
        "2026-07-16",
        script_path=script_path,
        new_accounts=new_accounts,
    )
    preview = format_manual_rename_command_preview(
        "2026-07-16",
        script_path=script_path,
        new_accounts=new_accounts,
    )

    assert format_command_for_shell(command) in preview
    assert "--newRename" in preview
    assert "--startNowDate 2026-07-16" in preview
    assert "ddmarii" in preview
    assert r"G:\4K Stogram\00.MODELS-D" in preview
    assert "--no-duplicated" in preview
    assert "--move-renamed" in preview
    assert "[0]" in preview


def test_list_unmoved_account_folders_ignores_files_and_hidden_dirs(tmp_path: Path) -> None:
    working = tmp_path / "working"
    working.mkdir()
    (working / "readme.txt").write_text("x", encoding="utf-8")
    (working / ".hidden").mkdir()
    leftover = working / "Some-Renamed-Account"
    leftover.mkdir()
    (working / "another_user").mkdir()

    leftovers = list_unmoved_account_folders(working)

    assert [path.name for path in leftovers] == ["another_user", "Some-Renamed-Account"]
    assert has_unmoved_account_folders(working) is True
    assert list_unmoved_account_folders(tmp_path / "missing") == []
    assert has_unmoved_account_folders(None) is False


def test_list_unmoved_account_folders_empty_when_only_files(tmp_path: Path) -> None:
    working = tmp_path / "working"
    working.mkdir()
    (working / "telegram_media.jpg").write_bytes(b"x")

    assert list_unmoved_account_folders(working) == []
    assert has_unmoved_account_folders(working) is False


def test_decide_rename_completion_keeps_button_when_folders_remain(tmp_path: Path) -> None:
    leftover = tmp_path / "still_here"
    leftover.mkdir()

    with_leftovers = decide_rename_completion(
        exit_code=0,
        leftover_folders=[leftover],
    )
    assert with_leftovers.mark_completed is False
    assert with_leftovers.keep_rename_enabled is True
    assert with_leftovers.leftover_folders == (leftover,)

    clean_success = decide_rename_completion(exit_code=0, leftover_folders=[])
    assert clean_success.mark_completed is True
    assert clean_success.keep_rename_enabled is False

    failed = decide_rename_completion(exit_code=1, leftover_folders=[])
    assert failed.mark_completed is False
    assert failed.keep_rename_enabled is True


def test_gui_rename_parameters_only_include_checked_new_accounts() -> None:
    parameters = _new_account_rename_parameters(
        [
            AccountDraft(username="existing", is_new_account=False),
            AccountDraft(
                username="update_user",
                is_catalog_update=True,
                owner_id="999",
                destination_path=r"G:\Models\Existing",
            ),
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


@pytest.mark.parametrize(
    ("field_name", "field_value", "error"),
    [
        ("owner_id", "", "ownerId is required"),
        ("destination_path", "", "path is required"),
    ],
)
def test_gui_catalog_update_requires_owner_and_path(
    field_name: str,
    field_value: str,
    error: str,
) -> None:
    values = {
        "owner_id": "111222333",
        "destination_path": r"G:\4K Stogram\00.MODELS-D",
    }
    values[field_name] = field_value
    account = AccountDraft(
        username="existing_master_user",
        is_catalog_update=True,
        download_stories=True,
        **values,
    )

    with pytest.raises(BatchDraftValidationError, match=error):
        validate_batch_draft(
            BatchDraft(
                batch_name="catalog_update_missing_field",
                default_start_now_date="2026-08-11",
                accounts=[account],
            )
        )


def test_gui_catalog_update_saves_metadata_without_new_account_flag(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    # Pre-existing catalog row with startInitDate that Update must preserve.
    with connect(db_path) as connection:
        AccountHistoryRepository(connection).update_rename_metadata(
            "master_user",
            owner_id="old-id",
            destination_path=r"G:\OldPath",
            start_init_date="2024-01-01",
        )
        draft = BatchDraft(
            batch_name="catalog_update_batch",
            default_start_now_date="2026-08-11",
            accounts=[
                AccountDraft(
                    username="@master_user",
                    download_stories=True,
                    is_catalog_update=True,
                    owner_id="555666777",
                    destination_path=r"G:\4K Stogram\00.MODELS-M",
                )
            ],
        )
        result = save_batch_draft(draft, connection)

        catalog = AccountHistoryRepository(connection).get_by_user_name("master_user")
        assert catalog is not None
        assert catalog.user_ig_id == "555666777"
        assert catalog.field1 == r"G:\4K Stogram\00.MODELS-M"
        assert catalog.field2 == "2024-01-01"

        stored = connection.execute(
            "SELECT * FROM accounts WHERE batch_id = ?",
            (result.batch.id,),
        ).fetchone()
        assert stored["is_new_account"] == 0
        assert stored["rename_owner_id"] == "555666777"
        assert stored["rename_start_init_date"] is None
        assert stored["rename_destination_path"] == r"G:\4K Stogram\00.MODELS-M"

        loaded = load_batch_draft(connection, result.batch.id)
        assert loaded.accounts[0].is_new_account is False
        assert loaded.accounts[0].is_catalog_update is True
        assert loaded.accounts[0].owner_id == "555666777"
        assert loaded.accounts[0].destination_path == r"G:\4K Stogram\00.MODELS-M"
        assert _account_display_status(loaded.accounts[0], None) == ("Catálogo", "pending")


def test_gui_export_import_preserves_catalog_update(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="export_update",
        default_start_now_date="2026-08-11",
        accounts=[
            AccountDraft(
                username="portable_user",
                download_stories=True,
                is_catalog_update=True,
                owner_id="424242",
                destination_path=r"G:\Models\Portable",
            )
        ],
    )
    with connect(db_path) as connection:
        saved = save_batch_draft(draft, connection)
        payload = export_batch_payload(connection, saved.batch.id)
        assert payload["batch"]["accounts"][0]["is_catalog_update"] is True
        assert payload["batch"]["accounts"][0]["is_new_account"] is False
        assert payload["batch"]["accounts"][0]["owner_id"] == "424242"

        imported = import_batch_from_payload(connection, payload)
        loaded = load_batch_draft(connection, imported.batch.id)
        assert loaded.accounts[0].is_catalog_update is True
        assert loaded.accounts[0].is_new_account is False
        assert loaded.accounts[0].owner_id == "424242"
        assert loaded.accounts[0].destination_path == r"G:\Models\Portable"

        catalog = AccountHistoryRepository(connection).get_by_user_name("portable_user")
        assert catalog is not None
        assert catalog.user_ig_id == "424242"
        assert catalog.field1 == r"G:\Models\Portable"

        rename_params = _new_account_rename_parameters(loaded.accounts)
        assert rename_params == ()


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
        assert managed[0].url_count == 1
        assert list_pending_batches(connection) == []

        recovered = load_batch_draft(connection, result.batch.id)
        assert recovered == draft


def test_gui_managed_batches_report_total_url_count(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="two_accounts_urls",
        default_start_now_date="2026-08-08",
        accounts=[
            AccountDraft(
                username="account_a",
                urls=[
                    f"https://www.instagram.com/reel/AAAA{i:02d}/"
                    for i in range(50)
                ],
            ),
            AccountDraft(
                username="account_b",
                urls=[
                    f"https://www.instagram.com/reel/BBBB{i:02d}/"
                    for i in range(50)
                ],
            ),
        ],
    )
    empty = BatchDraft(
        batch_name="empty_urls_batch",
        default_start_now_date="2026-08-08",
        accounts=[AccountDraft(username="no_urls_yet", download_stories=True)],
    )

    with connect(db_path) as connection:
        save_batch_draft(draft, connection)
        save_batch_draft(empty, connection)
        managed = {
            item.batch_name: item for item in list_managed_batches(connection)
        }

        assert managed["two_accounts_urls"].url_count == 100
        assert managed["two_accounts_urls"].total_accounts == 2
        assert managed["empty_urls_batch"].url_count == 0


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


def test_gui_registered_draft_can_remove_all_accounts_and_be_recovered(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    original = BatchDraft(
        batch_name="empty_after_update",
        default_start_now_date="2026-07-23",
        accounts=[AccountDraft(username="remove_me", download_stories=True)],
    )
    empty = BatchDraft(
        batch_name="empty_after_update",
        default_start_now_date="2026-07-23",
        accounts=[],
    )

    with connect(db_path) as connection:
        created = save_batch_draft(original, connection)
        updated = save_batch_draft(empty, connection, batch_id=created.batch.id)

        assert updated.accounts == ()
        assert AccountRepository(connection).list_by_batch(created.batch.id) == []
        assert load_batch_draft(connection, created.batch.id) == empty


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


def test_list_account_problem_urls_filters_retry_and_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="problem_urls",
        default_start_now_date="2026-08-08",
        accounts=[
            AccountDraft(
                username="problem_user",
                urls=[
                    "https://www.instagram.com/reel/OKDONE01/",
                    "https://www.instagram.com/reel/RETRYME01/",
                    "https://www.instagram.com/reel/RETRYME02/",
                    "https://www.instagram.com/reel/FAILME01/",
                    "https://www.instagram.com/p/STILLPENDING/",
                ],
            )
        ],
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        account = result.accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        repo = UrlJobRepository(connection)
        repo.update_status(jobs[0].id, UrlJobStatus.COMPLETED)
        repo.update_error(
            jobs[1].id,
            status=UrlJobStatus.RETRY_PENDING,
            last_error="timeout",
            last_error_type="TEMPORARY",
            non_retryable=False,
        )
        repo.update_error(
            jobs[2].id,
            status=UrlJobStatus.FAILED_TEMPORARY,
            last_error="Media not found or unavailable",
            last_error_type="TEMPORARY",
            non_retryable=False,
        )
        repo.update_error(
            jobs[3].id,
            status=UrlJobStatus.FAILED_FINAL,
            last_error="We're sorry, we couldn't find that.",
            last_error_type="NOT_FOUND",
            non_retryable=True,
        )
        # jobs[4] stays PENDING

        retry_rows = list_account_problem_urls(
            connection,
            account_id=account.id,
            kind="retry",
        )
        failed_rows = list_account_problem_urls(
            connection,
            account_id=account.id,
            kind="failed",
        )
        completed_rows = list_account_problem_urls(
            connection,
            account_id=account.id,
            kind="completed",
        )

        assert [row.url for row in retry_rows] == [
            "https://www.instagram.com/reel/RETRYME01/",
            "https://www.instagram.com/reel/RETRYME02/",
        ]
        assert retry_rows[0].last_error == "timeout"
        assert [row.url for row in failed_rows] == [
            "https://www.instagram.com/reel/FAILME01/",
        ]
        assert failed_rows[0].status == UrlJobStatus.FAILED_FINAL.value
        assert [row.url for row in completed_rows] == [
            "https://www.instagram.com/reel/OKDONE01/",
        ]
        assert completed_rows[0].status == UrlJobStatus.COMPLETED.value

        progress = get_account_runtime_progress(connection, result.batch.id)[0]
        status_label, status_tag = _account_display_status(
            draft.accounts[0],
            progress,
        )
        assert status_tag == "retry"
        assert "Reintento" in status_label
        assert progress.retry_items == 2
        assert progress.failed_items == 1
        assert progress.completed_items == 1


def test_list_historical_batches_only_completed(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft_active = BatchDraft(
        batch_name="still_active",
        default_start_now_date="2026-08-11",
        accounts=[
            AccountDraft(
                username="active_user",
                urls=["https://www.instagram.com/reel/ACTIVE01/"],
            )
        ],
    )
    draft_done = BatchDraft(
        batch_name="already_done",
        default_start_now_date="2026-08-10",
        accounts=[
            AccountDraft(
                username="done_user",
                urls=["https://www.instagram.com/reel/DONE01/"],
            )
        ],
    )
    with connect(db_path) as connection:
        active = save_batch_draft(draft_active, connection)
        done = save_batch_draft(draft_done, connection)
        finish_batch(connection, done.batch.id)

        historical = list_historical_batches(connection)
        managed = list_managed_batches(connection)

        assert [item.batch_id for item in historical] == [done.batch.id]
        assert historical[0].display_status == "COMPLETADO"
        assert historical[0].url_count == 1
        assert all(item.batch_id != done.batch.id for item in managed)
        assert any(item.batch_id == active.batch.id for item in managed)


def test_resolve_account_download_folder_prefers_stored_path(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    working_root = tmp_path / "working"
    stored_folder = working_root / "folder_user"
    stored_folder.mkdir(parents=True)
    fallback_folder = working_root / "fallback_user"
    fallback_folder.mkdir()
    draft = BatchDraft(
        batch_name="folder_resolve",
        default_start_now_date="2026-08-11",
        accounts=[
            AccountDraft(
                username="folder_user",
                urls=["https://www.instagram.com/reel/FOLDER01/"],
            ),
            AccountDraft(
                username="fallback_user",
                urls=["https://www.instagram.com/reel/FOLDER02/"],
            ),
            AccountDraft(
                username="missing_user",
                urls=["https://www.instagram.com/reel/FOLDER03/"],
            ),
        ],
    )
    settings = Settings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telethon_session_name="session",
        telegram_download_bot_username="@bot",
        telegram_desktop_download_folder=tmp_path / "tg",
        working_folder=working_root,
        reports_folder=tmp_path / "reports",
        sqlite_db_path=db_path,
        max_retries=3,
        retry_base_seconds=90,
        retry_max_seconds=900,
        download_wait_timeout_seconds=300,
        download_stable_seconds=10,
    )

    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection, settings=settings)
        by_name = {account.username: account for account in result.accounts}
        stored = by_name["folder_user"]
        connection.execute(
            "UPDATE accounts SET working_folder = ? WHERE id = ?",
            (str(stored_folder), stored.id),
        )
        connection.commit()

        assert resolve_account_download_folder(
            connection,
            account_id=stored.id,
            username="folder_user",
            working_folder_setting=working_root,
        ) == stored_folder

        fallback = by_name["fallback_user"]
        connection.execute(
            "UPDATE accounts SET working_folder = NULL WHERE id = ?",
            (fallback.id,),
        )
        connection.commit()
        assert resolve_account_download_folder(
            connection,
            account_id=fallback.id,
            username="fallback_user",
            working_folder_setting=working_root,
        ) == fallback_folder

        missing = by_name["missing_user"]
        assert (
            resolve_account_download_folder(
                connection,
                account_id=missing.id,
                username="missing_user",
                working_folder_setting=working_root,
            )
            is None
        )


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
        assert (
            BatchRepository(connection).get_by_id(result.batch.id).status
            is InputBatchStatus.AWAITING_RENAME
        )
        assert is_batch_ready_for_rename(connection, result.batch.id) is True
        managed = list_managed_batches(connection)
        assert any(
            item.batch_id == result.batch.id and item.is_awaiting_rename
            for item in managed
        )


def test_gui_mark_executed_elsewhere_moves_to_awaiting_rename(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="elsewhere_batch",
        default_start_now_date="2026-08-05",
        accounts=[
            AccountDraft(
                username="elsewhere_user",
                urls=["https://www.instagram.com/reel/ELSE1/"],
                start_now_date="2026-08-05",
            )
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        mark_batch_executed_elsewhere(connection, result.batch.id)
        stored = BatchRepository(connection).get_by_id(result.batch.id)
        account = AccountRepository(connection).get_by_id(result.accounts[0].id)
        jobs = UrlJobRepository(connection).list_by_account(result.accounts[0].id)

        assert stored.status is InputBatchStatus.AWAITING_RENAME
        assert account.status is AccountStatus.COMPLETED
        assert jobs[0].status is UrlJobStatus.FAILED_FINAL
        assert jobs[0].last_error_type == "EXECUTED_ELSEWHERE"
        assert is_batch_ready_for_rename(connection, result.batch.id) is True
        assert list_pending_batches(connection) == []
        assert any(
            item.batch_id == result.batch.id and item.display_status == "POR RENOMBRAR"
            for item in list_managed_batches(connection)
        )


def test_gui_export_import_roundtrip_creates_new_draft(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="transfer_source",
        default_start_now_date="2026-08-05",
        accounts=[
            AccountDraft(
                username="transfer_user",
                download_stories=True,
                urls=["https://www.instagram.com/reel/TR1/"],
                start_now_date="2026-08-05",
                is_new_account=True,
                owner_id="111",
                start_init_date="2026-01-01",
                destination_path=r"G:\Models",
            )
        ],
    )
    with connect(db_path) as connection:
        saved = save_batch_draft(draft, connection)
        payload = export_batch_payload(connection, saved.batch.id)
        imported = import_batch_from_payload(connection, payload)
        loaded = load_batch_draft(connection, imported.batch.id)

        assert payload["format"] == "ig_orchestrator.batch_export"
        assert imported.batch.status is InputBatchStatus.DRAFT
        assert imported.batch.batch_name.startswith("transfer_source")
        assert imported.batch.id != saved.batch.id
        assert loaded.accounts[0].username == "transfer_user"
        assert loaded.accounts[0].download_stories is True
        assert loaded.accounts[0].urls == ["https://www.instagram.com/reel/TR1/"]
        assert loaded.accounts[0].is_new_account is True
        assert loaded.accounts[0].owner_id == "111"

        with pytest.raises(BatchTransferError):
            import_batch_from_payload(connection, {"format": "other"})


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


def _draft_with_name(name: str, username: str, *, new_account: bool = False) -> BatchDraft:
    return BatchDraft(
        batch_name=name,
        default_start_now_date="2026-08-15",
        accounts=[
            AccountDraft(
                username=username,
                urls=["https://www.instagram.com/reel/QUEUE1/"],
                is_new_account=new_account,
                owner_id="111" if new_account else "",
                start_init_date="2025-01-01" if new_account else "",
                destination_path=r"G:\4K Stogram\00.MODELS-A" if new_account else "",
            )
        ],
    )


def test_batch_queue_add_remove_and_reject_running_removal(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        BatchQueueError,
        QueueItemStatus,
        add_batches_to_open_queue,
        get_queue,
        remove_pending_item,
        start_or_resume_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("q1", "user_one"), connection)
        second = save_batch_draft(_draft_with_name("q2", "user_two"), connection)
        third = save_batch_draft(_draft_with_name("q3", "user_three"), connection)
        queue = add_batches_to_open_queue(
            connection,
            [first.batch.id, second.batch.id, third.batch.id],
        )
        assert [item.batch_id for item in queue.items] == [
            first.batch.id,
            second.batch.id,
            third.batch.id,
        ]
        start_or_resume_queue(connection, queue.id)
        running = get_queue(connection, queue.id).running_item
        assert running is not None
        with pytest.raises(BatchQueueError, match="se está ejecutando"):
            remove_pending_item(connection, running.id)
        pending_third = next(
            item for item in get_queue(connection, queue.id).items
            if item.batch_id == third.batch.id
        )
        updated = remove_pending_item(connection, pending_third.id)
        assert updated.items[-1].status == QueueItemStatus.REMOVED.value
        assert updated.pending_items[0].batch_id == second.batch.id


def test_batch_queue_advance_then_awaiting_rename_after_last_pending_removed(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueStatus,
        add_batches_to_open_queue,
        get_queue,
        mark_current_item_completed,
        remove_pending_item,
        start_or_resume_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("seq1", "alpha"), connection)
        second = save_batch_draft(_draft_with_name("seq2", "beta"), connection)
        third = save_batch_draft(_draft_with_name("seq3", "gamma"), connection)
        queue = add_batches_to_open_queue(
            connection,
            [first.batch.id, second.batch.id, third.batch.id],
        )
        start_or_resume_queue(connection, queue.id)
        next_item = mark_current_item_completed(connection, queue.id)
        assert next_item is not None
        assert next_item.batch_id == second.batch.id
        start_or_resume_queue(connection, queue.id)
        third_item = next(
            item for item in get_queue(connection, queue.id).items
            if item.batch_id == third.batch.id
        )
        remove_pending_item(connection, third_item.id)
        assert mark_current_item_completed(connection, queue.id) is None
        closed = get_queue(connection, queue.id)
        assert closed.status == QueueStatus.AWAITING_RENAME.value
        assert closed.rename_batch_ids == (first.batch.id, second.batch.id)


def test_collect_rename_parameters_merges_new_accounts_and_latest_date(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import collect_rename_parameters
    from ig_orchestrator.gui.process_runner import build_manual_rename_command

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    earlier = BatchDraft(
        batch_name="rename_a",
        default_start_now_date="2026-08-14",
        accounts=[
            AccountDraft(
                username="new_a",
                urls=["https://www.instagram.com/reel/A1/"],
                is_new_account=True,
                owner_id="10",
                start_init_date="2025-01-01",
                destination_path=r"G:\4K Stogram\00.MODELS-A",
            )
        ],
    )
    later = BatchDraft(
        batch_name="rename_b",
        default_start_now_date="2026-08-15",
        accounts=[
            AccountDraft(
                username="new_b",
                urls=["https://www.instagram.com/reel/B1/"],
                is_new_account=True,
                owner_id="20",
                start_init_date="2025-02-02",
                destination_path=r"G:\4K Stogram\00.MODELS-B",
            )
        ],
    )
    with connect(db_path) as connection:
        first = save_batch_draft(earlier, connection)
        second = save_batch_draft(later, connection)
        params = collect_rename_parameters(
            connection, [first.batch.id, second.batch.id]
        )

    assert params.start_now_date == "2026-08-15"
    assert params.has_mixed_dates is True
    assert [account.username for account in params.new_accounts] == ["new_a", "new_b"]
    command = build_manual_rename_command(
        params.start_now_date,
        new_accounts=params.new_accounts,
    )
    assert command.count("--new-account") == 2
    assert "--move-renamed" in command


def test_finish_queue_after_rename_respects_leftovers_decision(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueStatus,
        add_batches_to_open_queue,
        finish_queue_after_rename,
        get_queue,
        mark_current_item_completed,
        start_or_resume_queue,
    )
    from ig_orchestrator.gui.rename_folder_status import decide_rename_completion
    from ig_orchestrator.models import InputBatchStatus

    leftover = tmp_path / "still_here"
    leftover.mkdir()
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("fin1", "one"), connection)
        second = save_batch_draft(_draft_with_name("fin2", "two"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, second.batch.id]
        )
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)

        blocked = decide_rename_completion(
            exit_code=0, leftover_folders=[leftover]
        )
        assert blocked.mark_completed is False
        assert get_queue(connection, queue.id).status == QueueStatus.AWAITING_RENAME.value

        finish_queue_after_rename(connection, queue.id)
        assert get_queue(connection, queue.id).status == QueueStatus.COMPLETED.value
        assert (
            BatchRepository(connection).get_by_id(first.batch.id).status
            is InputBatchStatus.COMPLETED
        )
        assert (
            BatchRepository(connection).get_by_id(second.batch.id).status
            is InputBatchStatus.COMPLETED
        )


def test_removing_all_queue_items_cancels_zombie_sequence(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        QueueStatus,
        add_batches_to_open_queue,
        get_open_queue,
        get_queue,
        remove_queue_item,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("z1", "zeta_one"), connection)
        second = save_batch_draft(_draft_with_name("z2", "zeta_two"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, second.batch.id]
        )
        for item in list(queue.items):
            remove_queue_item(connection, item.id)
        closed = get_queue(connection, queue.id)
        assert closed.status == QueueStatus.CANCELLED.value
        assert all(
            item.status == QueueItemStatus.REMOVED.value for item in closed.items
        )
        assert get_open_queue(connection) is None


def test_completed_queue_items_can_be_removed_and_do_not_block_rename(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueStatus,
        add_batches_to_open_queue,
        collect_rename_parameters,
        get_open_queue,
        get_queue,
        mark_current_item_completed,
        remove_queue_item,
        start_or_resume_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("done1", "done_one"), connection)
        second = save_batch_draft(_draft_with_name("done2", "done_two"), connection)
        amber = save_batch_draft(_draft_with_name("amber", "amber_user"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, second.batch.id]
        )
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)
        waiting = get_queue(connection, queue.id)
        assert waiting.status == QueueStatus.AWAITING_RENAME.value
        for item in waiting.items:
            remove_queue_item(connection, item.id)
        assert get_queue(connection, queue.id).status == QueueStatus.CANCELLED.value
        assert get_open_queue(connection) is None
        params = collect_rename_parameters(connection, [amber.batch.id])
        assert params.batch_ids == (amber.batch.id,)


def test_finish_elsewhere_and_delete_detach_batch_from_sequence(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        QueueStatus,
        add_batches_to_open_queue,
        get_open_queue,
        get_queue,
    )
    from ig_orchestrator.gui.batch_resume_service import (
        delete_draft_batch,
        finish_batch,
        mark_batch_executed_elsewhere,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("seq_a", "seq_alpha"), connection)
        second = save_batch_draft(_draft_with_name("seq_b", "seq_beta"), connection)
        third = save_batch_draft(_draft_with_name("seq_c", "seq_gamma"), connection)
        queue = add_batches_to_open_queue(
            connection,
            [first.batch.id, second.batch.id, third.batch.id],
        )

        finish_batch(connection, first.batch.id)
        after_finish = get_queue(connection, queue.id)
        by_batch = {item.batch_id: item for item in after_finish.items}
        assert by_batch[first.batch.id].status == QueueItemStatus.REMOVED.value
        assert [item.batch_id for item in after_finish.pending_items] == [
            second.batch.id,
            third.batch.id,
        ]

        mark_batch_executed_elsewhere(connection, second.batch.id)
        after_elsewhere = get_queue(connection, queue.id)
        by_batch = {item.batch_id: item for item in after_elsewhere.items}
        assert by_batch[second.batch.id].status == QueueItemStatus.REMOVED.value
        assert [item.batch_id for item in after_elsewhere.pending_items] == [
            third.batch.id
        ]
        stored_second = BatchRepository(connection).get_by_id(second.batch.id)
        assert stored_second.status is InputBatchStatus.AWAITING_RENAME

        delete_draft_batch(connection, third.batch.id)
        remaining = get_queue(connection, queue.id)
        assert remaining.status == QueueStatus.CANCELLED.value
        assert get_open_queue(connection) is None
        assert BatchRepository(connection).get_by_id(third.batch.id) is None


def test_get_open_queue_cancels_awaiting_rename_with_only_removed_items(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        QueueStatus,
        add_batches_to_open_queue,
        get_open_queue,
        get_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("ghost1", "ghost_one"), connection)
        queue = add_batches_to_open_queue(connection, [first.batch.id])
        now = "2026-08-31T06:55:07+00:00"
        connection.execute(
            """
            UPDATE batch_run_queue_items
            SET status = ?, updated_at = ?
            WHERE queue_id = ?
            """,
            (QueueItemStatus.REMOVED.value, now, queue.id),
        )
        connection.execute(
            """
            UPDATE batch_run_queues
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (QueueStatus.AWAITING_RENAME.value, now, queue.id),
        )
        connection.commit()
        assert get_open_queue(connection) is None
        assert get_queue(connection, queue.id).status == QueueStatus.CANCELLED.value


def test_add_batches_reactivates_removed_queue_item(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        add_batches_to_open_queue,
        get_queue,
        remove_queue_item,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("readd", "readd_user"), connection)
        keeper = save_batch_draft(_draft_with_name("keep", "keep_user"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, keeper.batch.id]
        )
        remove_queue_item(connection, queue.items[0].id)
        restored = add_batches_to_open_queue(connection, [first.batch.id])
        assert restored.id == queue.id
        by_batch = {item.batch_id: item for item in restored.items}
        assert by_batch[first.batch.id].status == QueueItemStatus.PENDING.value
        assert by_batch[keeper.batch.id].status == QueueItemStatus.PENDING.value
        assert get_queue(connection, restored.id).id == restored.id

