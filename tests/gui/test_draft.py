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


