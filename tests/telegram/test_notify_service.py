import asyncio
from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.db import connect, init_gui_database
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    InputBatch,
    InputBatchStatus,
    RunStatus,
    RunSummary,
    UrlJob,
    UrlJobStatus,
    UrlSource,
    PublicationType,
)
from ig_orchestrator.orchestration.account_orchestrator import AccountOrchestratorResult
from ig_orchestrator.orchestration.batch_orchestrator import BatchOrchestratorResult
from ig_orchestrator.db.run_repository import RunRecord
from ig_orchestrator.telegram.notify_service import (
    format_template,
    notify_batch_complete,
    notify_bot_error,
)
from ig_orchestrator.telegram.telegram_client import (
    TelegramClientConfig,
    TelethonTelegramClient,
)


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def start(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def send_message(self, entity: str, message: str) -> None:
        self.sent.append((entity, message))


def _client() -> tuple[TelethonTelegramClient, FakeClient]:
    inner = FakeClient()
    wrapper = TelethonTelegramClient(
        TelegramClientConfig(
            api_id=1,
            api_hash="hash",
            session_name="session",
            bot_username="@bot",
        ),
        client_factory=lambda *_args: inner,
    )
    wrapper._client = inner
    return wrapper, inner


def test_format_template_fills_placeholders() -> None:
    text = format_template("Lote {batch_name} {urls_ok}", batch_name="a", urls_ok=3)
    assert text == "Lote a 3"


def test_notify_batch_complete_sends_to_me(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE app_settings SET value = '1' WHERE key = 'notify.enabled'"
        )
        connection.commit()
        wrapper, inner = _client()
        now = datetime.now(timezone.utc)
        result = BatchOrchestratorResult(
            batch=InputBatch(
                id=9,
                batch_name="demo",
                schema_version="1.0",
                status=InputBatchStatus.COMPLETED,
            ),
            run=RunRecord(
                id=1,
                status=RunStatus.COMPLETED,
                started_at=now,
            ),
            summary=RunSummary(
                status=RunStatus.COMPLETED,
                total_urls=4,
                completed_urls=3,
                failed_urls=1,
            ),
            account_results=(
                AccountOrchestratorResult(
                    account=Account(
                        username="u1",
                        start_now_date=now.date(),
                        download_stories=False,
                        status=AccountStatus.COMPLETED,
                    ),
                    run=RunRecord(id=2, status=RunStatus.COMPLETED, started_at=now),
                    summary=RunSummary(status=RunStatus.COMPLETED),
                ),
            ),
        )
        asyncio.run(notify_batch_complete(connection, wrapper, result))
        assert inner.sent
        assert inner.sent[0][0] == "me"
        assert "demo" in inner.sent[0][1]


def test_notify_bot_error_respects_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE app_settings SET value = '1' WHERE key = 'notify.enabled'"
        )
        connection.execute(
            "UPDATE bot_errors SET notify_on_match = 1 WHERE code = 'NOT_FOUND'"
        )
        connection.commit()
        wrapper, inner = _client()
        job = UrlJob(
            account_id=1,
            url="https://www.instagram.com/p/x/",
            publication_type=PublicationType.POST,
            source=UrlSource.INPUT_URL,
            status=UrlJobStatus.FAILED_FINAL,
            last_error="We're sorry, we couldn't find that.",
            last_error_type="NOT_FOUND",
        )
        asyncio.run(
            notify_bot_error(connection, wrapper, job, username="demo")
        )
        assert inner.sent
        assert "demo" in inner.sent[0][1]
