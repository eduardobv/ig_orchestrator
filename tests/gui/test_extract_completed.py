from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    UrlJobRepository,
    connect,
    init_gui_database,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batch_resume_service import activate_draft_batch, load_batch_draft
from ig_orchestrator.gui.batches.extract import (
    ExtractCompletedError,
    extract_completed_accounts,
    list_completed_usernames,
    suggest_extract_name,
)
from ig_orchestrator.models import AccountStatus, InputBatchStatus, UrlJobStatus


def _batch(connection, usernames=("ana", "bea", "cris")):
    draft = BatchDraft(
        batch_name="lote",
        default_start_now_date="2026-10-16",
        accounts=[
            AccountDraft(
                username=u,
                urls=[f"https://www.instagram.com/reel/{u}{n}/" for n in range(2)],
                is_new_account=(u == "ana"),
                owner_id="123" if u == "ana" else "",
                start_init_date="2026-01-01" if u == "ana" else "",
                destination_path="G:/x/ana" if u == "ana" else "",
            )
            for u in usernames
        ],
    )
    result = save_batch_draft(draft, connection)
    activate_draft_batch(connection, result.batch.id)
    BatchRepository(connection).update_status(result.batch.id, InputBatchStatus.PARTIAL)
    return result


def _complete(connection, account):
    for job in UrlJobRepository(connection).list_by_account(account.id):
        UrlJobRepository(connection).update_status(job.id, UrlJobStatus.COMPLETED)
    AccountRepository(connection).update_status(account.id, AccountStatus.COMPLETED)


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "g.sqlite"
    init_gui_database(db)
    return db


def test_extract_moves_completed_accounts_keeping_flags(tmp_path: Path) -> None:
    with connect(_db(tmp_path)) as connection:
        result = _batch(connection)
        by_name = {a.username: a for a in result.accounts}
        _complete(connection, by_name["ana"])
        _complete(connection, by_name["bea"])

        assert list_completed_usernames(connection, result.batch.id) == ["ana", "bea"]
        assert suggest_extract_name(connection, result.batch.id) == "lote_LISTAS"
        out = extract_completed_accounts(
            connection, batch_id=result.batch.id, target_name="lote_LISTAS"
        )

        assert out.usernames == ("ana", "bea") and out.url_count == 4
        target = BatchRepository(connection).get_by_id(out.target_batch_id)
        assert target.status is InputBatchStatus.AWAITING_RENAME
        moved = load_batch_draft(connection, out.target_batch_id)
        assert [a.username for a in moved.accounts] == ["ana", "bea"]
        assert moved.accounts[0].is_new_account
        source = BatchRepository(connection).get_by_id(result.batch.id)
        assert source.status is InputBatchStatus.PARTIAL
        assert [a.username for a in load_batch_draft(connection, result.batch.id).accounts] == ["cris"]
        statuses = {
            a.username: a.status
            for a in AccountRepository(connection).list_by_batch(out.target_batch_id)
        }
        assert set(statuses.values()) == {AccountStatus.COMPLETED}
        assert suggest_extract_name(connection, result.batch.id) == "lote_LISTAS2"


def test_extract_refuses_invalid_cases_and_changes_nothing(tmp_path: Path) -> None:
    with connect(_db(tmp_path)) as connection:
        result = _batch(connection, usernames=("ana", "bea"))
        with pytest.raises(ExtractCompletedError, match="completadas"):
            extract_completed_accounts(connection, batch_id=result.batch.id, target_name="x")
        for account in result.accounts:
            _complete(connection, account)
        with pytest.raises(ExtractCompletedError, match="Renombrar"):
            extract_completed_accounts(connection, batch_id=result.batch.id, target_name="x")
        with pytest.raises(ExtractCompletedError, match="vac"):
            extract_completed_accounts(connection, batch_id=result.batch.id, target_name=" ")
        BatchRepository(connection).update_status(result.batch.id, InputBatchStatus.PROCESSING)
        with pytest.raises(ExtractCompletedError, match="detenido"):
            extract_completed_accounts(connection, batch_id=result.batch.id, target_name="x")
        assert connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
