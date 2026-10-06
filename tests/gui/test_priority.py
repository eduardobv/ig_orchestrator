from __future__ import annotations

from datetime import date
from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.gui.app import InstagramOrchestratorApp, priority_cell_text
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batch_resume_service import load_batch_draft
from ig_orchestrator.gui.draft.priority import (
    PRIORITY_HIGHEST,
    PRIORITY_NONE,
    assign_exclusive_priority,
    ordered_accounts_for_display,
)
from ig_orchestrator.input.batch_creation_service import (
    BatchCreationAccount,
    BatchCreationRequest,
    _ordered_accounts_for_creation,
)


def _account(username: str, *, priority: int = 0, urls: int = 1, stories: bool = False) -> AccountDraft:
    return AccountDraft(
        username=username,
        download_stories=stories,
        urls=[f"https://www.instagram.com/reel/{username.upper()}{index}/" for index in range(urls)]
        if not stories or urls
        else [],
        priority=priority,
    )


def test_priority_cell_text() -> None:
    assert priority_cell_text(0) == ""
    assert priority_cell_text(1) == "1"
    assert priority_cell_text(3) == "3"


def test_assign_exclusive_priority_clears_previous_rank_one() -> None:
    accounts = [
        _account("first", priority=1),
        _account("second"),
        _account("third"),
    ]

    updated = assign_exclusive_priority(accounts, "third")

    assert [item.username for item in updated] == ["third", "first", "second"]
    assert [item.priority for item in updated] == [1, 0, 0]


def test_ordered_accounts_for_display_keeps_relative_order_of_unranked() -> None:
    accounts = [
        _account("zeta"),
        _account("alpha", priority=1),
        _account("beta"),
    ]

    assert [item.username for item in ordered_accounts_for_display(accounts)] == [
        "alpha",
        "zeta",
        "beta",
    ]


def test_future_ranks_sort_before_unranked() -> None:
    accounts = [
        _account("c"),
        _account("b", priority=2),
        _account("a", priority=1),
    ]

    assert [item.username for item in ordered_accounts_for_display(accounts)] == [
        "a",
        "b",
        "c",
    ]


def test_creation_order_puts_ranked_accounts_before_legacy_sort() -> None:
    request = BatchCreationRequest(
        schema_version="1.0",
        batch_name="prio_batch",
        accounts=(
            BatchCreationAccount(
                username="many_urls",
                start_now_date=date(2026, 9, 13),
                download_stories=False,
                urls=("https://www.instagram.com/reel/A/", "https://www.instagram.com/reel/B/"),
            ),
            BatchCreationAccount(
                username="story_only",
                start_now_date=date(2026, 9, 13),
                download_stories=True,
                urls=(),
            ),
            BatchCreationAccount(
                username="vip",
                start_now_date=date(2026, 9, 13),
                download_stories=False,
                urls=("https://www.instagram.com/reel/C/",),
                priority=1,
            ),
        ),
    )

    ordered = _ordered_accounts_for_creation(request)
    assert [account.username for account in ordered] == [
        "vip",
        "story_only",
        "many_urls",
    ]


def test_upsert_with_priority_moves_account_first_and_clears_previous() -> None:
    class Flag:
        def __init__(self, value=False) -> None:
            self.value = value

        def get(self):
            return self.value

        def set(self, value) -> None:
            self.value = value

    app = object.__new__(InstagramOrchestratorApp)
    app.accounts = [
        AccountDraft(username="keep", urls=["https://www.instagram.com/reel/KEEP/"], priority=1),
        AccountDraft(username="other", urls=["https://www.instagram.com/reel/OTHR/"]),
    ]
    app.selected_index = None
    stored = AccountDraft(
        username="vip",
        urls=["https://www.instagram.com/reel/VIP1/"],
        priority=PRIORITY_HIGHEST,
    )
    app.accounts.append(stored)
    app.accounts = assign_exclusive_priority(app.accounts, stored.username)

    assert [item.username for item in app.accounts] == ["vip", "keep", "other"]
    assert app.accounts[0].priority == PRIORITY_HIGHEST
    assert all(item.priority == PRIORITY_NONE for item in app.accounts[1:])


def test_priority_round_trips_through_gui_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    draft = BatchDraft(
        batch_name="prio_roundtrip",
        default_start_now_date="2026-09-13",
        accounts=[
            AccountDraft(
                username="second",
                download_stories=True,
                urls=[],
                start_now_date="2026-09-13",
            ),
            AccountDraft(
                username="first",
                download_stories=True,
                urls=["https://www.instagram.com/reel/PRIO/"],
                start_now_date="2026-09-13",
                priority=1,
            ),
        ],
    )
    with connect(db_path) as connection:
        result = save_batch_draft(draft, connection)
        loaded = load_batch_draft(connection, result.batch.id)
        row = connection.execute(
            "SELECT username, priority, sort_order FROM accounts ORDER BY sort_order, id"
        ).fetchall()

    assert [account.username for account in loaded.accounts] == ["first", "second"]
    assert loaded.accounts[0].priority == 1
    assert loaded.accounts[1].priority == 0
    assert [item["username"] for item in row] == ["first", "second"]
    assert [int(item["priority"]) for item in row] == [1, 0]
