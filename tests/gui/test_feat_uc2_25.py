"""feat-uc2-25: private accounts, path suggestions, account card, G: warning and small GUI tweaks."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from ig_orchestrator.db import AccountHistoryRepository, connect, init_gui_database
from ig_orchestrator.gui.account_catalog_service import AccountCatalogEntry, AccountCatalogService
from ig_orchestrator.gui.catalog.colors import DEFAULT_CATALOG_COLORS, colors_for_entry
from ig_orchestrator.gui.editor.panel import EditorPanelMixin
from ig_orchestrator.gui.editor.path_suggest import PathSuggestEntry, rank_destination_paths
from ig_orchestrator.gui.i18n import load_language, locale_keys
from ig_orchestrator.gui.run.integrated_rename import IntegratedRenameMixin
from ig_orchestrator.gui.shared.treeview_sort import bind_treeview_sort
from ig_orchestrator.input.url_classifier import find_private_post_urls, is_private_post_url
from ig_orchestrator.library.account_card import (
    card_summary_text,
    list_private_usernames,
    load_card,
    save_card,
    set_account_private,
)

PRIVATE_URL = "https://www.instagram.com/p/Deh0qN5ttVEyvPscCYJ-17mfc4agkbIQxnNcOM0/"


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


# ------------------------------------------------------------------ 1. private URLs
def test_private_url_detection() -> None:
    assert is_private_post_url(PRIVATE_URL)
    assert is_private_post_url("https://www.instagram.com/reel/" + "A" * 30 + "/")
    assert not is_private_post_url("https://www.instagram.com/p/DXu5WA5jYJs/")
    assert not is_private_post_url("https://www.instagram.com/p/DXu5WA5jYJs/?img_index=2")
    assert not is_private_post_url("https://www.instagram.com/reel/DXu5WA5jYJs/")
    assert not is_private_post_url("https://www.instagram.com/stories/someone/123456789012345678/")
    assert not is_private_post_url("https://example.com/p/" + "A" * 30)
    assert find_private_post_urls(["", "https://www.instagram.com/p/DXu5WA5jYJs/", PRIVATE_URL]) == [PRIVATE_URL]


def _catalog(tmp_path: Path):
    db = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db)
    connection = connect(db)
    AccountHistoryRepository(connection).create_or_get("secret_user")
    return connection, AccountCatalogService(connection)


def test_private_flag_roundtrip_in_service_and_card(tmp_path: Path) -> None:
    connection, service = _catalog(tmp_path)
    with connection:
        assert list_private_usernames(connection) == set()
        assert service.set_private("Secret_User", private=True)
        assert list_private_usernames(connection) == {"secret_user"}
        entry = next(e for e in service.list_entries() if e.username == "secret_user")
        assert entry.is_private
        assert service.find_entry("secret_user").is_private
        account_id = int(connection.execute("SELECT id FROM catalog_accounts").fetchone()[0])
        card = load_card(connection, account_id)
        assert card.is_private
        save_card(connection, account_id, owner_id="", start_date="", notes="", favorite=False, private=False)
        assert not load_card(connection, account_id).is_private
        assert not set_account_private(connection, "nobody", True)


def test_private_accounts_get_a_distinct_text_colour() -> None:
    normal = AccountCatalogEntry(username="a")
    private = AccountCatalogEntry(username="a", is_private=True)
    assert "foreground" not in colors_for_entry(normal, DEFAULT_CATALOG_COLORS)
    assert colors_for_entry(private, DEFAULT_CATALOG_COLORS)["foreground"] == DEFAULT_CATALOG_COLORS["private_fg"]


class FakeEditor(EditorPanelMixin):
    def __init__(self, service, urls: list[str], username: str) -> None:
        self.catalog_service = service
        self.reloaded = False
        self.account = SimpleNamespace(urls=urls, username=username)

    def _reload_catalog(self) -> None:
        self.reloaded = True


def test_private_urls_block_the_account_and_offer_to_mark_it(tmp_path: Path, monkeypatch) -> None:
    from ig_orchestrator.gui.editor import panel

    connection, service = _catalog(tmp_path)
    with connection:
        asked: list[str] = []
        monkeypatch.setattr(panel.messagebox, "askyesno", lambda title, text, **kw: asked.append(text) or True)
        monkeypatch.setattr(panel.messagebox, "showwarning", lambda *a, **k: asked.append("warn"))
        editor = FakeEditor(service, [PRIVATE_URL], "secret_user")
        assert editor._block_private_urls(editor.account) is True
        assert editor.reloaded and service.find_entry("secret_user").is_private
        assert "secret_user" in asked[0]
        # unknown account: only a warning
        asked.clear()
        editor = FakeEditor(service, [PRIVATE_URL], "unknown")
        assert editor._block_private_urls(editor.account) is True
        assert asked == ["warn"]
        # public URLs: nothing blocks
        editor = FakeEditor(service, ["https://www.instagram.com/p/DXu5WA5jYJs/"], "secret_user")
        assert editor._block_private_urls(editor.account) is False


# ------------------------------------------------------------------ 2. owner id label
def test_owner_display_prefers_editor_value_then_catalog() -> None:
    entry = AccountCatalogEntry(username="Ann", owner_id="555")
    editor = FakeEditor(None, [], "")
    editor.owner_display_var = FakeVar()
    editor.owner_id_var = FakeVar("")
    editor.username_var = FakeVar("ann")
    editor.catalog_entries = [entry]
    editor._refresh_owner_display()
    assert editor.owner_display_var.get() == "555"
    editor.owner_id_var.set("999")
    editor._refresh_owner_display()
    assert editor.owner_display_var.get() == "999"
    editor.owner_id_var.set("")
    editor.username_var.set("nobody")
    editor._refresh_owner_display()
    assert editor.owner_display_var.get() == ""


# ------------------------------------------------------------------ 3. G: offline rename
def test_rename_asks_for_confirmation_when_the_library_is_offline(monkeypatch) -> None:
    from ig_orchestrator.gui.run import integrated_rename

    class App(IntegratedRenameMixin):
        online = False
        status = ""

        def _fsops_online(self) -> bool:
            return self.online

        def _set_status(self, text: str) -> None:
            self.status = text

        root = None

    app = App()
    calls: list[str] = []
    monkeypatch.setattr(integrated_rename.messagebox, "askokcancel", lambda title, text, **kw: calls.append(text) or False)
    assert app._confirm_rename_without_library() is False
    assert "G:" in calls[0]
    app._start_integrated_rename("2026-01-01", ())  # cancelled: returns before touching anything
    assert app.status
    monkeypatch.setattr(integrated_rename.messagebox, "askokcancel", lambda *a, **k: True)
    assert app._confirm_rename_without_library() is True
    app.online = True
    monkeypatch.setattr(integrated_rename.messagebox, "askokcancel", lambda *a, **k: pytest.fail("must not ask"))
    assert app._confirm_rename_without_library() is True


# ------------------------------------------------------------------ 4. sortable columns
def _tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk is not available")
    root.withdraw()
    return root


def test_batch_detail_table_sorts_every_column() -> None:
    from tkinter import ttk

    root = _tk_root()
    try:
        columns = ("username", "prio", "urls", "stories", "start")
        tree = ttk.Treeview(root, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
        rows = [("bob", "", 10, "x", "2026-02-01"), ("amy", "1", 2, "", "2026-01-01"), ("cat", "2", 33, "x", "2026-03-01")]
        for index, values in enumerate(rows):
            tree.insert("", tk.END, iid=str(index), values=values)
        bind_treeview_sort(tree, columns, title_for=lambda c: c)
        for col, expected in (("username", ["amy", "bob", "cat"]), ("urls", ["amy", "bob", "cat"]), ("start", ["amy", "bob", "cat"])):
            root.tk.call(tree.heading(col, "command"))  # run the sort command bound by bind_treeview_sort
            assert [tree.set(i, "username") for i in tree.get_children()] == expected, col
    finally:
        root.destroy()


# ------------------------------------------------------------------ 7. path suggestions
LIB = "G:\\4K Stogram"
PATHS = [
    f"{LIB}\\00.MODELS-D",
    f"{LIB}\\00.MODELS-D\\Zoe-Zed",
    f"{LIB}\\00.MODELS-D\\Ana-Ant",
    f"{LIB}\\00.MODELS-A\\Sophi-Fox",
    f"{LIB}\\00.FAVORITES\\Models-Fan",
    f"{LIB}\\01.OTHER\\Dina",
]
CONTAINERS = [f"{LIB}\\00.MODELS-D", f"{LIB}\\00.MODELS-A", f"{LIB}\\00.FAVORITES", f"{LIB}\\01.OTHER"]


def test_empty_query_lists_containers_first_then_the_rest_alphabetically() -> None:
    ranked = rank_destination_paths(PATHS, "", CONTAINERS)
    assert ranked[:4] == [f"{LIB}\\00.FAVORITES", f"{LIB}\\00.MODELS-A", f"{LIB}\\00.MODELS-D", f"{LIB}\\01.OTHER"]
    assert ranked[4:] == [
        f"{LIB}\\00.FAVORITES\\Models-Fan",
        f"{LIB}\\00.MODELS-A\\Sophi-Fox",
        f"{LIB}\\00.MODELS-D\\Ana-Ant",
        f"{LIB}\\00.MODELS-D\\Zoe-Zed",
        f"{LIB}\\01.OTHER\\Dina",
    ]


def test_typing_models_d_lists_that_folder_first_then_its_contents() -> None:
    ranked = rank_destination_paths(PATHS, "models-d", CONTAINERS)
    assert ranked == [
        f"{LIB}\\00.MODELS-D",
        f"{LIB}\\00.MODELS-D\\Ana-Ant",
        f"{LIB}\\00.MODELS-D\\Zoe-Zed",
    ]
    loose = rank_destination_paths(PATHS, "models", CONTAINERS)
    assert loose[0] == f"{LIB}\\00.FAVORITES\\Models-Fan" or loose[0].endswith("MODELS-A")
    assert all("models" in p.casefold() for p in loose)
    assert rank_destination_paths(PATHS, "zzz", CONTAINERS) == []


def test_path_suggest_widget_filters_and_chooses() -> None:
    root = _tk_root()
    try:
        var = tk.StringVar()
        widget = PathSuggestEntry(root, textvariable=var, values=PATHS, containers=CONTAINERS)
        widget.pack()
        var.set("models-d")
        assert widget.suggestions()[0].endswith("00.MODELS-D")
        widget._open(widget.suggestions())
        assert widget._listbox is not None and widget._listbox.size() == 3
        widget._move(1)
        widget._on_return(None)
        assert var.get().endswith("00.MODELS-D")
        assert widget._popup is None
        widget.set_values(["X:\\only"], [])
        var.set("")
        assert widget.suggestions() == ["X:\\only"]
    finally:
        root.destroy()


# ------------------------------------------------------------------ 6. account card text / containers
def test_card_summary_and_container_paths(tmp_path: Path) -> None:
    connection, service = _catalog(tmp_path)
    with connection:
        connection.execute("INSERT INTO catalog_folders (name, full_path, rel_path, parent_id, depth, created_at, updated_at)"
                           " VALUES ('4K', 'G:\\4K', '', NULL, 0, 'x', 'x')")
        root_id = int(connection.execute("SELECT id FROM catalog_folders WHERE parent_id IS NULL").fetchone()[0])
        for name in ("00.B", "00.A"):
            connection.execute("INSERT INTO catalog_folders (name, full_path, rel_path, parent_id, depth, created_at, updated_at)"
                               " VALUES (?, ?, ?, ?, 1, 'x', 'x')", (name, f"G:\\4K\\{name}", name, root_id))
        connection.commit()
        assert service.list_container_paths() == ["G:\\4K\\00.A", "G:\\4K\\00.B"]
        account_id = int(connection.execute("SELECT id FROM catalog_accounts").fetchone()[0])
        text = card_summary_text(load_card(connection, account_id), "G:\\4K\\00.A\\secret_user")
        assert "Username: secret_user" in text and "G:\\4K\\00.A\\secret_user" in text


# ------------------------------------------------------------------ locales
def test_new_locale_keys_exist_in_both_languages() -> None:
    assert locale_keys("es") == locale_keys("en")
    load_language("es")
    for key in ("private.urls_warning", "card.full_path", "fsops.copy_path", "rename.offline_confirm"):
        assert key in locale_keys("es")
