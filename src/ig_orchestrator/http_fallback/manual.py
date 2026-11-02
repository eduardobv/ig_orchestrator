"""Manual HTTP downloads started from the GUI, and the «Probar sesión» check.

Both run in a worker thread with their own SQLite connection: the Tk thread
never touches the network or the disk.
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ig_orchestrator.db import AccountRepository, DownloadRepository, UrlJobRepository
from ig_orchestrator.db.connection import connect
from ig_orchestrator.http_fallback.client import (
    HttpFallbackError,
    InstagramHttpClient,
)
from ig_orchestrator.http_fallback.config import HttpFallbackConfig
from ig_orchestrator.http_fallback.coordinator import HttpFallbackCoordinator
from ig_orchestrator.http_fallback.store import ensure_http_fallback_schema
from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.models import PublicationType, UrlJobStatus
from ig_orchestrator.orchestration.run_settings import load_run_settings
from ig_orchestrator.orchestration.url_job_processor import (
    UrlJobProcessor,
    UrlJobProcessorConfig,
)
from ig_orchestrator.settings import Settings

logger = get_logger()

DEFAULT_TEST_URL = "https://www.instagram.com/p/DeO6TtQMqY9/"
# A job in flight in a running batch must not be touched from here.
_BUSY_STATUSES = frozenset({UrlJobStatus.SENT_TO_BOT, UrlJobStatus.WAITING_DOWNLOAD})


@dataclass(slots=True)
class ManualProgress:
    done: int = 0
    total: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    text: str = ""
    finished: bool = False
    error: str | None = None


def check_session(config: HttpFallbackConfig) -> int:
    """Ask Instagram for a known post with the session; returns the file count.

    Raises ``HttpFallbackError`` whose message already says what to do.
    """

    url = config.probe_urls[0] if config.probe_urls else DEFAULT_TEST_URL
    return len(InstagramHttpClient(config).fetch_media_files(url))


class _NoConversation:
    async def process_url_job(self, job):  # pragma: no cover - never used
        raise RuntimeError("manual HTTP downloads never talk to the bot")


def run_manual_http_download(
    *,
    settings: Settings,
    job_ids: list[int],
    allow_completed: bool,
    cancel: threading.Event,
    report: Callable[[ManualProgress], None],
    now: Callable[[], datetime] = datetime.now,
) -> ManualProgress:
    """Download ``job_ids`` over HTTP one by one, with the configured pauses."""

    progress = ManualProgress(total=len(job_ids))
    connection = connect(Path(settings.sqlite_gui_db_path))
    try:
        run_settings = load_run_settings(connection, settings)
        config = dataclasses.replace(
            HttpFallbackConfig.from_run_settings(run_settings),
            enabled=True,
            max_per_run=1_000_000,
            max_429=1,  # manual: stop at the first 429 instead of pausing for minutes
        )
        ensure_http_fallback_schema(connection)
        jobs = UrlJobRepository(connection)
        accounts = AccountRepository(connection)
        processor = UrlJobProcessor(
            url_job_repository=jobs,
            account_repository=accounts,
            download_repository=DownloadRepository(connection),
            conversation_service=_NoConversation(),
            config=UrlJobProcessorConfig(default_working_folder=settings.working_folder),
        )

        def status(text: str) -> None:
            progress.text = text
            report(progress)

        async def cancellable_sleep(seconds: float) -> None:
            remaining = seconds
            while remaining > 0 and not cancel.is_set():
                step = min(0.5, remaining)
                await asyncio.sleep(step)
                remaining -= step

        coordinator = HttpFallbackCoordinator(
            config=config,
            client=InstagramHttpClient(config),
            url_job_repository=jobs,
            account_repository=accounts,
            processor=processor,
            download_folder=settings.telegram_download_target_folder,
            connection=connection,
            status_callback=status,
            now=now,
            sleeper=cancellable_sleep,
        )

        async def main() -> None:
            for job_id in job_ids:
                if cancel.is_set():
                    break
                job = jobs.get_by_id(job_id)
                if (
                    job is None
                    or job.publication_type not in (PublicationType.POST, PublicationType.REEL)
                    or job.status in _BUSY_STATUSES
                    or (job.status is UrlJobStatus.COMPLETED and not allow_completed)
                ):
                    progress.skipped += 1
                    progress.done += 1
                    report(progress)
                    continue
                account = accounts.get_by_id(job.account_id)
                code = await coordinator.download_job(job, account)
                progress.done += 1
                if code == "OK":
                    progress.ok += 1
                else:
                    progress.failed += 1
                if code == "DISABLED":
                    progress.error = coordinator.disabled_reason
                    break
                report(progress)

        asyncio.run(main())
    except Exception as exc:  # report instead of dying silently in the thread
        logger.exception("Manual HTTP download failed")
        progress.error = progress.error or str(exc)
    finally:
        connection.close()
        progress.finished = True
        report(progress)
    return progress


__all__ = [
    "DEFAULT_TEST_URL",
    "HttpFallbackError",
    "ManualProgress",
    "run_manual_http_download",
    "check_session",
]
