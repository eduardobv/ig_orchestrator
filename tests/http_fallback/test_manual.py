from __future__ import annotations

import threading
from types import SimpleNamespace

from ig_orchestrator.db import UrlJobRepository, init_database
from ig_orchestrator.db.connection import connect
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.http_fallback import manual
from ig_orchestrator.http_fallback.config import HttpFallbackConfig
from ig_orchestrator.models import UrlJobStatus


def _setup(tmp_path, monkeypatch):
    db_path = tmp_path / "gui.db"
    init_database(db_path)
    draft = BatchDraft(
        batch_name="manual_http",
        default_start_now_date="2026-08-08",
        accounts=[
            AccountDraft(
                username="u",
                urls=[
                    "https://www.instagram.com/p/AAA/",
                    "https://www.instagram.com/p/BBB/",
                    "https://www.instagram.com/stories/u/123/",
                ],
            )
        ],
    )
    with connect(db_path) as connection:
        account = save_batch_draft(draft, connection).accounts[0]
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        UrlJobRepository(connection).update_status(jobs[0].id, UrlJobStatus.WAITING_DOWNLOAD)
        ids = [job.id for job in jobs]

    seen: dict[str, object] = {"downloaded": []}

    class FakeCoordinator:
        def __init__(self, *, config, **_kwargs):
            seen["config"] = config
            self.disabled_reason = None

        async def download_job(self, job, account):
            seen["downloaded"].append(job.id)
            return "OK"

    monkeypatch.setattr(manual, "HttpFallbackCoordinator", FakeCoordinator)
    monkeypatch.setattr(manual, "load_run_settings", lambda *_a, **_k: object())
    monkeypatch.setattr(
        manual.HttpFallbackConfig,
        "from_run_settings",
        classmethod(lambda cls, _rs: HttpFallbackConfig(night_enabled=True, jitter_percent=20)),
    )
    settings = SimpleNamespace(
        sqlite_gui_db_path=db_path,
        working_folder=tmp_path / "work",
        telegram_download_target_folder=tmp_path / "tg",
    )
    return settings, ids, seen


def test_waiting_download_is_skipped_unless_no_run_is_active(tmp_path, monkeypatch) -> None:
    settings, ids, seen = _setup(tmp_path, monkeypatch)

    result = manual.run_manual_http_download(
        settings=settings, job_ids=ids, allow_completed=False,
        cancel=threading.Event(), report=lambda _p: None,
    )
    assert seen["downloaded"] == [ids[1]]  # WAITING_DOWNLOAD and the story are skipped
    assert result.skipped == 2

    seen["downloaded"].clear()
    manual.run_manual_http_download(
        settings=settings, job_ids=ids, allow_completed=False, allow_busy=True,
        cancel=threading.Event(), report=lambda _p: None,
    )
    assert seen["downloaded"] == [ids[0], ids[1]]


def test_interval_override_is_exact_and_not_stored(tmp_path, monkeypatch) -> None:
    settings, ids, seen = _setup(tmp_path, monkeypatch)

    manual.run_manual_http_download(
        settings=settings, job_ids=ids, allow_completed=False, interval_seconds=7,
        cancel=threading.Event(), report=lambda _p: None,
    )

    config = seen["config"]
    assert (config.interval_seconds, config.jitter_percent, config.night_enabled) == (7.0, 0, False)
