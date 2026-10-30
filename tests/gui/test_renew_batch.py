from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import AccountHistoryRepository, connect, init_database, init_gui_database
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import BatchDraftValidationError, save_batch_draft, validate_batch_draft
from ig_orchestrator.gui.batch_queue_service import collect_rename_parameters
from ig_orchestrator.gui.batch_resume_service import load_batch_draft
from ig_orchestrator.gui.batch_transfer_service import export_batch_payload, import_batch_from_payload
from ig_orchestrator.gui.process_runner import build_manual_rename_command
from ig_orchestrator.gui.shared.helpers import _account_display_status, _new_account_rename_parameters


def renew_draft(**overrides) -> BatchDraft:
    account = AccountDraft(
        username="@alice",
        urls=["https://www.instagram.com/reel/A1/"],
        is_renew=True,
        start_init_date="2025-03-01",
        **overrides,
    )
    return BatchDraft(batch_name="renew_batch", default_start_now_date="2026-10-10", accounts=[account])


def test_renew_only_needs_the_first_post_date(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        result = save_batch_draft(renew_draft(), connection)

        stored = connection.execute("SELECT * FROM accounts WHERE batch_id = ?", (result.batch.id,)).fetchone()
        assert stored["is_new_account"] == 0
        assert stored["rename_start_init_date"] == "2025-03-01"
        assert stored["rename_owner_id"] is None and stored["rename_destination_path"] is None

        loaded = load_batch_draft(connection, result.batch.id).accounts[0]
        assert (loaded.is_renew, loaded.is_new_account, loaded.is_catalog_update) == (True, False, False)
        assert loaded.start_init_date == "2025-03-01"


def test_renew_keeps_owner_id_and_path_of_the_catalog(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        AccountHistoryRepository(connection).update_rename_metadata(
            "alice", owner_id="777", destination_path=r"G:\Models\A", start_init_date="2020-01-01"
        )
        save_batch_draft(renew_draft(), connection)
        record = AccountHistoryRepository(connection).get_by_user_name("alice")
    assert (record.user_ig_id, record.field1, record.field2) == ("777", r"G:\Models\A", "2025-03-01")


def test_renew_requires_a_valid_first_post_date() -> None:
    draft = renew_draft()
    draft.accounts[0].start_init_date = ""
    with pytest.raises(BatchDraftValidationError, match="startInitDate is required for Renew"):
        validate_batch_draft(draft)
    draft.accounts[0].start_init_date = "01/03/2025"
    with pytest.raises(BatchDraftValidationError, match="YYYY-MM-DD"):
        validate_batch_draft(draft)


@pytest.mark.parametrize("other", ["is_new_account", "is_catalog_update"])
def test_renew_is_exclusive_with_new_account_and_update(other: str) -> None:
    draft = renew_draft()
    setattr(draft.accounts[0], other, True)
    draft.accounts[0].owner_id = "1"
    draft.accounts[0].destination_path = r"G:\x"
    with pytest.raises(BatchDraftValidationError, match="cannot be enabled at the same time"):
        validate_batch_draft(draft)


def test_renew_roundtrips_through_export_and_import(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        saved = save_batch_draft(renew_draft(), connection)
        payload = export_batch_payload(connection, saved.batch.id)
        assert payload["batch"]["accounts"][0]["is_renew"] is True
        imported = import_batch_from_payload(connection, payload)
        loaded = load_batch_draft(connection, imported.batch.id).accounts[0]
        assert (loaded.is_renew, loaded.is_new_account, loaded.start_init_date) == (True, False, "2025-03-01")


def test_renew_reaches_the_integrated_renamer_but_not_the_legacy_command(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        saved = save_batch_draft(renew_draft(), connection)
        params = collect_rename_parameters(connection, [saved.batch.id])
        drafts = [load_batch_draft(connection, saved.batch.id).accounts[0]]
    (account,) = params.new_accounts
    assert (account.username, account.renew, account.start_init_date, account.owner_id) == ("alice", True, "2025-03-01", "")
    assert _new_account_rename_parameters(drafts)[0].renew is True
    assert "--new-account" not in build_manual_rename_command(params.start_now_date, new_accounts=params.new_accounts)


def test_renew_in_the_gui_database(tmp_path: Path) -> None:
    db_path = tmp_path / "gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        AccountHistoryRepository(connection).update_rename_metadata(
            "alice", owner_id="777", destination_path="00.MODELS", start_init_date="2020-01-01"
        )
        saved = save_batch_draft(renew_draft(), connection)
        loaded = load_batch_draft(connection, saved.batch.id).accounts[0]
        row = connection.execute(
            "SELECT instagram_user_id, start_init_date FROM catalog_accounts WHERE username = 'alice'"
        ).fetchone()
    assert loaded.is_renew is True
    assert (row["instagram_user_id"], row["start_init_date"]) == ("777", "2025-03-01")


def test_renew_status_label() -> None:
    assert _account_display_status(renew_draft().accounts[0], None) == ("Renew", "pending")


def _editor_app():
    from ig_orchestrator.gui.app import InstagramOrchestratorApp

    class Var:
        def __init__(self, value="") -> None:
            self.value = value

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    app = object.__new__(InstagramOrchestratorApp)
    app.username_var = Var("alice")
    app.stories_var = Var(False)
    app.new_account_var = Var(False)
    app.catalog_update_var = Var(False)
    app.renew_var = Var(False)
    app.owner_id_var = Var("")
    app.start_init_date_var = Var("2025-03-01")
    app.destination_path_var = Var("")
    app.account_date_var = Var("2026-10-10")
    app._toggle_catalog_metadata_fields = lambda: None
    app._editor_bound_username = "alice"

    class Text:
        @staticmethod
        def get(*_args):
            return "https://www.instagram.com/reel/A1/\n"

    app.urls_text = Text()
    return app


def test_editor_renew_excludes_new_account_and_update_and_resets_with_the_account() -> None:
    app = _editor_app()
    app.new_account_var.set(True)
    app.catalog_update_var.set(True)
    app.renew_var.set(True)
    app._on_renew_toggle()
    assert (app.new_account_var.value, app.catalog_update_var.value, app.renew_var.value) == (False, False, True)
    assert app._editor_account().is_renew is True

    app.new_account_var.set(True)
    app._on_new_account_toggle()
    assert app.renew_var.value is False

    app.renew_var.set(True)
    app._on_catalog_update_toggle()  # Update is off, so Renew stays
    assert app.renew_var.value is True
    app.catalog_update_var.set(True)
    app._on_catalog_update_toggle()
    assert app.renew_var.value is False

    app.renew_var.set(True)
    app._apply_username_identity("bob")
    assert app.renew_var.value is False
