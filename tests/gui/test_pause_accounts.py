from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    DownloadRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_gui_database,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batch_resume_service import (
    PauseAccountsError,
    activate_draft_batch,
    load_batch_draft,
    pausable_usernames,
    pause_accounts_to_new_batch,
)
from ig_orchestrator.models import (
    AccountStatus,
    InputBatchStatus,
    RunStatus,
    RunSummary,
    UrlJobStatus,
)
from ig_orchestrator.orchestration import BatchOrchestrator, BatchOrchestratorConfig
from ig_orchestrator.orchestration.account_orchestrator import (
    AccountOrchestratorResult,
)


def _batch(connection, name="lote", usernames=("ana", "bea", "cris")):
    draft = BatchDraft(
        batch_name=name,
        default_start_now_date="2026-10-16",
        accounts=[
            AccountDraft(
                username=user,
                urls=[f"https://www.instagram.com/reel/{user}{n}/" for n in range(2)],
            )
            for user in usernames
        ],
    )
    result = save_batch_draft(draft, connection)
    activate_draft_batch(connection, result.batch.id)
    return result


def _by_name(result):
    return {account.username: account for account in result.accounts}


def _usernames(connection, batch_id):
    return [a.username for a in load_batch_draft(connection, batch_id).accounts]


def _gui_db(tmp_path: Path) -> Path:
    db = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db)
    return db


def test_pause_moves_pending_accounts_to_new_draft_batch(tmp_path: Path) -> None:
    with connect(_gui_db(tmp_path)) as connection:
        result = _batch(connection)

        paused = pause_accounts_to_new_batch(
            connection, batch_id=result.batch.id, usernames=["bea", "CRIS"]
        )

        assert paused.created and paused.target_batch_name == "lote_PAUSA"
        assert paused.url_count == 4
        target = BatchRepository(connection).get_by_id(paused.target_batch_id)
        assert target.status is InputBatchStatus.DRAFT
        assert _usernames(connection, result.batch.id) == ["ana"]
        moved = load_batch_draft(connection, paused.target_batch_id)
        assert [a.username for a in moved.accounts] == ["bea", "cris"]
        assert all(len(a.urls) == 2 for a in moved.accounts)


def test_second_pause_appends_and_taken_names_get_a_number(tmp_path: Path) -> None:
    with connect(_gui_db(tmp_path)) as connection:
        result = _batch(connection)
        first = pause_accounts_to_new_batch(
            connection, batch_id=result.batch.id, usernames=["cris"]
        )
        second = pause_accounts_to_new_batch(
            connection, batch_id=result.batch.id, usernames=["bea"]
        )
        assert not second.created
        assert second.target_batch_id == first.target_batch_id
        assert _usernames(connection, first.target_batch_id) == ["cris", "bea"]

        # Once lote_PAUSA is activated (no longer DRAFT) the next pause gets a number.
        activate_draft_batch(connection, first.target_batch_id)
        other = _batch(connection, name="lote2", usernames=("x1", "x2"))
        connection.execute(
            "UPDATE batches SET name = 'lote2_PAUSA' WHERE id = ?",
            (first.target_batch_id,),
        )
        connection.commit()
        third = pause_accounts_to_new_batch(
            connection, batch_id=other.batch.id, usernames=["x2"]
        )
        assert third.target_batch_name == "lote2_PAUSA2"


def test_pause_refuses_started_accounts_and_changes_nothing(tmp_path: Path) -> None:
    with connect(_gui_db(tmp_path)) as connection:
        result = _batch(connection)
        accounts = _by_name(result)
        jobs = UrlJobRepository(connection).list_by_account(accounts["bea"].id)
        UrlJobRepository(connection).update_status(jobs[0].id, UrlJobStatus.COMPLETED)
        AccountRepository(connection).update_status(
            accounts["cris"].id, AccountStatus.PROCESSING
        )

        assert pausable_usernames(connection, result.batch.id) == {"ana"}
        with pytest.raises(PauseAccountsError, match="bea"):
            pause_accounts_to_new_batch(
                connection, batch_id=result.batch.id, usernames=["ana", "bea", "cris"]
            )
        assert len(_usernames(connection, result.batch.id)) == 3
        count = connection.execute(
            "SELECT COUNT(*) FROM batches WHERE name LIKE '%_PAUSA%'"
        ).fetchone()[0]
        assert count == 0


def test_pause_refuses_all_accounts_and_draft_batches(tmp_path: Path) -> None:
    with connect(_gui_db(tmp_path)) as connection:
        result = _batch(connection, usernames=("ana", "bea"))
        with pytest.raises(PauseAccountsError, match="vac"):
            pause_accounts_to_new_batch(
                connection, batch_id=result.batch.id, usernames=["ana", "bea"]
            )
        draft = save_batch_draft(
            BatchDraft(
                batch_name="borrador",
                default_start_now_date="2026-10-16",
                accounts=[
                    AccountDraft(username="u1", urls=["https://www.instagram.com/reel/U1/"]),
                    AccountDraft(username="u2", urls=["https://www.instagram.com/reel/U2/"]),
                ],
            ),
            connection,
        )
        with pytest.raises(PauseAccountsError, match="DRAFT"):
            pause_accounts_to_new_batch(
                connection, batch_id=draft.batch.id, usernames=["u1"]
            )


class _FakeAccountOrchestrator:
    def __init__(self, connection, on_first=None):
        self.accounts = AccountRepository(connection)
        self.jobs = UrlJobRepository(connection)
        self.runs = RunRepository(connection)
        self.calls: list[int] = []
        self.on_first = on_first

    async def process_account(self, account_id, *, scope):
        self.calls.append(account_id)
        if self.on_first is not None and len(self.calls) == 1:
            self.on_first()
        for job in self.jobs.list_by_account(account_id):
            self.jobs.update_status(job.id, UrlJobStatus.COMPLETED)
        account = self.accounts.update_status(account_id, AccountStatus.COMPLETED)
        summary = RunSummary(status=RunStatus.COMPLETED, total_urls=2, completed_urls=2)
        return AccountOrchestratorResult(
            account=account,
            run=self.runs.create(summary, account_id=account_id),
            summary=summary,
        )


def test_running_batch_skips_account_paused_midway_and_finishes(tmp_path: Path) -> None:
    with connect(_gui_db(tmp_path)) as connection:
        result = _batch(connection)
        accounts = _by_name(result)

        # While "ana" is being processed the user pauses "cris" from the GUI.
        fake = _FakeAccountOrchestrator(
            connection,
            on_first=lambda: pause_accounts_to_new_batch(
                connection, batch_id=result.batch.id, usernames=["cris"]
            ),
        )
        orchestrator = BatchOrchestrator(
            batch_repository=BatchRepository(connection),
            account_repository=AccountRepository(connection),
            url_job_repository=UrlJobRepository(connection),
            download_repository=DownloadRepository(connection),
            run_repository=RunRepository(connection),
            account_orchestrator=fake,
            config=BatchOrchestratorConfig(stories_first=False),
        )

        outcome = asyncio.run(orchestrator.process_batch(result.batch.id))

        assert fake.calls == [accounts["ana"].id, accounts["bea"].id]
        assert outcome.batch.status is InputBatchStatus.AWAITING_RENAME
        paused = AccountRepository(connection).get_by_id(accounts["cris"].id)
        assert paused.status is AccountStatus.PENDING
        assert paused.batch_id != result.batch.id
