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


def test_editor_panel_binds_batch_username_filter_helper() -> None:
    from ig_orchestrator.gui.editor import panel as editor_panel

    assert callable(editor_panel.batch_username_matches_filter)
    assert editor_panel.batch_username_matches_filter("alice", "ali") is True


