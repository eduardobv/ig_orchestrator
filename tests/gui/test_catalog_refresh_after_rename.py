from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ig_orchestrator.gui.draft.models import AccountDraft
from ig_orchestrator.gui.library.rename_actions import AccountRenameActionsMixin

LOCALES = Path(__file__).resolve().parents[2] / "src" / "ig_orchestrator" / "gui" / "shared" / "locales"


class FakeVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeApp(AccountRenameActionsMixin):
    def __init__(self) -> None:
        self.accounts = [AccountDraft("OldName"), AccountDraft("someone")]
        self.username_var = FakeVar("oldname")
        self.calls: list[str] = []

    def _after_fsops_change(self) -> None:
        self.calls.append("reload_catalog_and_editor")

    def _refresh_table(self) -> None:
        self.calls.append("refresh_table")

    def _update_batch_context(self) -> None:
        self.calls.append("batch_context")


def test_rename_updates_open_batch_rows_and_editor_without_restart() -> None:
    app = FakeApp()

    app._after_account_rename("oldname", "brandnew")

    assert [a.username for a in app.accounts] == ["brandnew", "someone"]
    assert app.username_var.get() == "brandnew"
    assert app.calls == ["reload_catalog_and_editor", "refresh_table", "batch_context"]


def test_editor_name_of_another_account_is_left_alone() -> None:
    app = FakeApp()
    app.username_var.set("someone")

    app._after_account_rename("oldname", "brandnew")

    assert app.username_var.get() == "someone"


def test_rename_locale_keys_in_both_languages() -> None:
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    keys = {k for k in es if k.startswith(("rename.", "owners."))}
    assert len(keys) >= 35 and keys <= set(en)
    _ = SimpleNamespace
