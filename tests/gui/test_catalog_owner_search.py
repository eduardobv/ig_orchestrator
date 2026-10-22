from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ig_orchestrator.db import AccountHistoryRepository, connect, init_gui_database
from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogService,
    filter_catalog_entries,
    parse_owner_id,
)
from ig_orchestrator.gui.catalog.panel import CatalogPanelMixin
from ig_orchestrator.models import AccountHistoryStatus


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _service(tmp_path: Path):
    db = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db)
    connection = connect(db)
    history = AccountHistoryRepository(connection)
    for name, owner, status in (
        ("visible", "1111111111", AccountHistoryStatus.ENABLED),
        ("old_one", "2222222222", AccountHistoryStatus.ARCHIVED),
        ("gone", "3333333333", AccountHistoryStatus.DELETED),
        ("noid", "", AccountHistoryStatus.ENABLED),
    ):
        history.create_or_get(name)
        if owner:
            history.update_rename_metadata(
                name, owner_id=owner, destination_path=r"G:\x\A", start_init_date="2026-01-01"
            )
        if status is not AccountHistoryStatus.ENABLED:
            history.update_status(name, status)
    return connection, AccountCatalogService(connection)


def test_parse_owner_id() -> None:
    assert parse_owner_id(" 1234567890 ") == "1234567890"
    assert parse_owner_id('"1234567890"') == "1234567890"
    assert parse_owner_id("1234") is None  # too short: treated as a username search
    assert parse_owner_id("user123456") is None
    assert parse_owner_id("") is None


def test_owner_id_search_covers_archived_and_deleted_accounts(tmp_path: Path) -> None:
    connection, service = _service(tmp_path)
    with connection:
        shown = {e.username for e in service.list_entries()}
        assert "old_one" not in shown and "gone" not in shown  # hidden by default

        assert [e.username for e in service.find_entries_by_owner_id("1111111111")] == ["visible"]
        archived = service.find_entries_by_owner_id("2222222222")
        assert [(e.username, e.status) for e in archived] == [
            ("old_one", AccountHistoryStatus.ARCHIVED)
        ]
        assert [e.username for e in service.find_entries_by_owner_id("3333333333")] == ["gone"]
        assert service.find_entries_by_owner_id("9999999999") == []
        # Partial ids do not match: ids are compared exactly.
        assert service.find_entries_by_owner_id("111111") == []
        # The username filter keeps working as before.
        assert [e.username for e in filter_catalog_entries(service.list_entries(), "visib")] == ["visible"]


class FakeApp(CatalogPanelMixin):
    def __init__(self, service) -> None:
        self.catalog_service = service
        self.catalog_filter_var = FakeVar()
        self.username_var = FakeVar()
        self.identity: list[str] = []
        self.root = SimpleNamespace()

    def _apply_username_identity(self, username: str) -> None:
        self.identity.append(username)


def test_pasting_an_owner_id_filters_by_id_and_binds_the_found_account(tmp_path: Path) -> None:
    connection, service = _service(tmp_path)
    with connection:
        app = FakeApp(service)
        app._apply_catalog_pasted_text("  2222222222\r\nsecond line")
        assert app.catalog_filter_var.get() == "2222222222"
        assert app.username_var.get() == "old_one"
        assert app.identity == ["old_one"]

        unknown = FakeApp(service)
        unknown._apply_catalog_pasted_text("8888888888")
        assert unknown.catalog_filter_var.get() == "8888888888"
        assert unknown.username_var.get() == ""  # digits never become the username

        plain = FakeApp(service)
        plain._apply_catalog_pasted_text("@Visible")
        assert plain.catalog_filter_var.get() == "Visible"
