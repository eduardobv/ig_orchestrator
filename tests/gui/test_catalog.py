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


def test_gui_open_catalog_prefers_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    class ChromeController:
        def open_new_tab(self, url: str) -> bool:
            opened.append(url)
            return True

    monkeypatch.setattr(
        "ig_orchestrator.gui.shared.helpers.webbrowser.get",
        lambda name: ChromeController(),
    )

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
        "ig_orchestrator.gui.catalog.panel._open_chrome_tab",
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


