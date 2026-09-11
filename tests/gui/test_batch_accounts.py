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
            "ig_orchestrator.gui.batch_accounts.panel.messagebox.askyesno",
            lambda *_args, **_kwargs: True,
        )
        monkeypatch.setattr(
            "ig_orchestrator.gui.batch_accounts.panel.messagebox.showinfo",
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
        "ig_orchestrator.gui.batch_accounts.panel.messagebox.askyesno",
        lambda title, message: prompts.append((title, message)) or True,
    )

    app._delete_all_accounts()

    assert app.accounts == []
    assert "Nombre: registered_batch" in prompts[0][1]
    assert "ID: 44" in prompts[0][1]
    assert "Actualizar lote" in prompts[0][1]


