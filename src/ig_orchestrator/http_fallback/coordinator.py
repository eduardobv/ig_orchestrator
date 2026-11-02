"""Decides when a silent post/reel is downloaded over HTTP instead of the bot.

Rules (all values come from Settings > Ejecución):

* a post/reel the bot leaves unanswered ``bot_attempts`` times is downloaded
  over HTTP (one request every ``interval`` s, longer inside the night window);
* at most ``max_consecutive`` HTTP downloads in a row per account; then the
  account is *parked* (no more questions to the bot) and the batch moves on;
* when only parked accounts are left, the final mode downloads their URLs over
  HTTP and asks the bot again every ``recheck_every`` downloads;
* ``botdown_silences`` silent URLs in a row trigger a probe with a URL that
  always works; if the bot does not answer it either, it is down: HTTP every
  ``botdown_interval`` s in blocks, probing again after each block, until the
  bot answers or the accounts are marked FAILED;
* 401/403 disable HTTP for the rest of the run (with a clear explanation).
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Protocol

from ig_orchestrator.db import AccountRepository, UrlJobRepository
from ig_orchestrator.http_fallback.client import (
    KIND_NOT_FOUND,
    KIND_NO_SESSION,
    KIND_RATE_LIMIT,
    KIND_SESSION,
    KIND_TRANSIENT,
    HttpFallbackError,
    InstagramHttpClient,
    MediaFile,
)
from ig_orchestrator.http_fallback.config import HttpFallbackConfig
from ig_orchestrator.http_fallback.schedule import base_interval, with_jitter
from ig_orchestrator.http_fallback.store import record_http_download
from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
)
from ig_orchestrator.orchestration.processing_policy import (
    PROCESSABLE_ACCOUNT_STATUSES,
    TERMINAL_URL_STATUSES,
)
from ig_orchestrator.orchestration.retry_policy import (
    MEDIA_NOT_FOUND_ERROR_TYPE,
    NO_BOT_RESPONSE_ERROR_TYPE,
)
from ig_orchestrator.orchestration.url_job_processor import UrlJobProcessorResult

logger = get_logger()

# Errors that say nothing about whether the bot is alive.
_NOT_AN_ANSWER = frozenset(
    {
        NO_BOT_RESPONSE_ERROR_TYPE,
        "SEND_MESSAGE_FAILED",
        "MOVE_FILES_FAILED",
        "NO_FILES_DETECTED",
    }
)
_OPEN_STATUSES = frozenset(
    {
        UrlJobStatus.PENDING,
        UrlJobStatus.SENT_TO_BOT,
        UrlJobStatus.WAITING_DOWNLOAD,
        UrlJobStatus.RETRY_PENDING,
        UrlJobStatus.FAILED_TEMPORARY,
    }
)
_SLEEP_SLICE_SECONDS = 30.0
_BOT_SETTLE_SECONDS = 15.0


class _Processor(Protocol):
    async def process(self, url_job_id: int) -> UrlJobProcessorResult: ...

    async def process_http(
        self, url_job_id: int, paths: list[Path]
    ) -> UrlJobProcessorResult: ...


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    result: UrlJobProcessorResult
    park_account: bool = False


def is_silent(job: UrlJob) -> bool:
    return (
        job.last_error_type == NO_BOT_RESPONSE_ERROR_TYPE
        and job.status not in TERMINAL_URL_STATUSES
    )


def bot_answered(job: UrlJob) -> bool:
    if job.status in (UrlJobStatus.COMPLETED, UrlJobStatus.DOWNLOADED):
        return True
    return bool(job.last_error_type) and job.last_error_type not in _NOT_AN_ANSWER


class HttpFallbackCoordinator:
    def __init__(
        self,
        *,
        config: HttpFallbackConfig,
        client: InstagramHttpClient,
        url_job_repository: UrlJobRepository,
        account_repository: AccountRepository,
        processor: _Processor,
        download_folder: Path,
        probe: Callable[[], Awaitable[bool]] | None = None,
        connection: Connection | None = None,
        status_callback: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._jobs = url_job_repository
        self._accounts = account_repository
        self._processor = processor
        self._download_folder = download_folder
        self._probe = probe
        self._connection = connection
        self._status_callback = status_callback
        self._clock = clock
        self._now = now
        self._sleeper = sleeper
        self._rng = rng
        self._batch_id: int | None = None
        self._consecutive: dict[int, int] = {}
        self._parked: set[int] = set()
        self._silent_streak = 0
        self._last_probe: float | None = None
        self._last_http: float | None = None
        self._http_total = 0
        self._rate_hits = 0
        self._disabled_reason: str | None = None
        self._aborted = False
        self._abort_reason: str | None = None
        self._announced_no_session = False

    # -- public state ---------------------------------------------------
    @property
    def config(self) -> HttpFallbackConfig:
        return self._config

    @property
    def aborted(self) -> bool:
        return self._aborted

    @property
    def abort_reason(self) -> str | None:
        return self._abort_reason

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    @property
    def http_total(self) -> int:
        return self._http_total

    def parked_account_ids(self) -> list[int]:
        return sorted(self._parked)

    def is_parked(self, account_id: int | None) -> bool:
        return account_id is not None and account_id in self._parked

    def unpark_all(self) -> None:
        self._parked.clear()
        self._consecutive.clear()
        self._silent_streak = 0

    def applies(self, job: UrlJob) -> bool:
        if job.publication_type is PublicationType.POST:
            return self._config.posts
        if job.publication_type is PublicationType.REEL:
            return self._config.reels
        return False

    def http_available(self) -> bool:
        if not self._config.enabled or self._disabled_reason is not None:
            return False
        if not self._config.has_session:
            if not self._announced_no_session:
                self._announced_no_session = True
                from ig_orchestrator.http_fallback.client import NO_SESSION_ADVICE

                self._notify(f"Descarga HTTP desactivada: {NO_SESSION_ADVICE}")
            return False
        return self._http_total < self._config.max_per_run

    async def download_job(self, job: UrlJob, account: Account | None) -> str:
        """Download one job over HTTP now (manual use); returns the outcome code."""

        return await self._http_download(job, account)

    # -- hook used by the account loop ----------------------------------
    async def after_attempt(
        self, result: UrlJobProcessorResult, account: Account
    ) -> AttemptOutcome:
        """Called after every bot attempt of the main pass."""

        job = result.job
        if account.batch_id is not None:
            self._batch_id = account.batch_id
        if not is_silent(job):
            if bot_answered(job):
                self._note_answer(account.id)
            return AttemptOutcome(result)
        if not self._config.active or not self.applies(job):
            return AttemptOutcome(result)
        return await self._handle_silent(result, account)

    def _note_answer(self, account_id: int | None) -> None:
        self._silent_streak = 0
        if account_id is not None:
            self._consecutive[account_id] = 0

    async def _handle_silent(
        self, result: UrlJobProcessorResult, account: Account
    ) -> AttemptOutcome:
        job = result.job
        job_id = _job_id(job)
        for _ in range(max(0, self._config.bot_attempts - 1)):
            await self._sleep(self._config.retry_delay_seconds)
            result = await self._processor.process(job_id)
            if not is_silent(result.job):
                if bot_answered(result.job):
                    self._note_answer(account.id)
                return AttemptOutcome(result)
        self._silent_streak += 1
        logger.warning(
            "Bot silent after {} attempt(s): job_id={} silent_streak={}",
            self._config.bot_attempts,
            job_id,
            self._silent_streak,
        )

        if (
            self._config.botdown_enabled
            and self._probe is not None
            and self._silent_streak >= self._config.botdown_silences
            and self._probe_allowed()
        ):
            if await self._probe_bot():
                self._silent_streak = 0  # the bot lives: the problem is the URLs
            else:
                await self._bot_down_mode()
                return AttemptOutcome(self._fresh(result), park_account=self._aborted)

        if not self.http_available():
            return AttemptOutcome(result)
        account_id = _account_id(account)
        if self._consecutive.get(account_id, 0) >= self._config.max_consecutive:
            self._park(account)
            return AttemptOutcome(result, park_account=True)

        code = await self._http_download(job, account)
        if code in ("OK", "NOT_FOUND"):
            self._consecutive[account_id] = self._consecutive.get(account_id, 0) + 1
        fresh = self._fresh(result)
        park = (
            self._consecutive.get(account_id, 0) >= self._config.max_consecutive
            and self.http_available()
        )
        if park:
            self._park(account)
        return AttemptOutcome(fresh, park_account=park or self._aborted)

    def _park(self, account: Account) -> None:
        if account.id is None or account.id in self._parked:
            return
        self._parked.add(account.id)
        logger.warning(
            "Account parked after {} consecutive HTTP downloads: {}",
            self._config.max_consecutive,
            account.username,
        )
        self._notify(
            f"@{account.username}: el bot no responde en esta cuenta; se pasa a la "
            "siguiente y se terminará por HTTP al final."
        )

    # -- final mode -----------------------------------------------------
    async def run_final_mode(self, batch_id: int) -> str:
        """HTTP-only pass over the parked accounts; returns what happened."""

        self._batch_id = batch_id
        if self._aborted or not self._parked:
            return "NOTHING"
        candidates = self._parked_candidates()
        if not candidates:
            self.unpark_all()
            return "NOTHING"
        self._notify(
            f"Modo final: {len(candidates)} URL(s) pendientes en cuentas sin respuesta "
            "del bot; se descargan por HTTP."
        )
        since_check = 0
        for job in candidates:
            if self._aborted or not self.http_available():
                break
            current = self._jobs.get_by_id(_job_id(job))
            if current is None or current.status not in _OPEN_STATUSES:
                continue
            account = self._accounts.get_by_id(current.account_id)
            if account is None:
                continue
            if since_check >= self._config.recheck_every:
                since_check = 0
                result = await self._processor.process(_job_id(current))
                if not is_silent(result.job):
                    self._note_answer(account.id)
                    self._notify("El bot vuelve a responder; se retoma el flujo normal.")
                    self.unpark_all()
                    return "RECOVERED"
                current = result.job
            await self._http_download(current, account)
            since_check += 1
        # HTTP finished or became unavailable: leftovers go through the bot again.
        self.unpark_all()
        return "DONE"

    def _parked_candidates(self) -> list[UrlJob]:
        jobs: list[UrlJob] = []
        for account_id in sorted(self._parked):
            for job in self._jobs.list_by_account(account_id):
                if self._is_http_candidate(job):
                    jobs.append(job)
        return jobs

    def _is_http_candidate(self, job: UrlJob) -> bool:
        if not self.applies(job) or job.non_retryable or job.status not in _OPEN_STATUSES:
            return False
        if job.status is UrlJobStatus.RETRY_PENDING:
            return job.last_error_type == NO_BOT_RESPONSE_ERROR_TYPE
        return True

    # -- bot down -------------------------------------------------------
    def _probe_allowed(self) -> bool:
        if self._last_probe is None:
            return True
        return self._clock() - self._last_probe >= self._config.probe_gap_minutes * 60

    async def _probe_bot(self) -> bool:
        assert self._probe is not None
        self._last_probe = self._clock()
        self._notify("Comprobando si el bot responde (URL de prueba)…")
        alive = await self._probe()
        logger.info("Bot probe result: alive={}", alive)
        return alive

    async def _bot_down_mode(self) -> None:
        cfg = self._config
        self._notify(
            "El bot no responde ni a la URL de prueba: se considera caído."
            + (" Se descarga por HTTP mientras tanto." if self.http_available() else "")
        )
        blocks = 0
        waits = 0
        while True:
            if self.http_available():
                blocks += 1
                nothing_left = await self._http_block(
                    cfg.botdown_interval_seconds, cfg.botdown_block_minutes * 60
                )
                if nothing_left:
                    self._notify("No quedan URLs por descargar.")
                    return
            else:
                waits += 1
                pending = self._count_open_jobs()
                self._notify(
                    f"Bot caído y sin descarga HTTP disponible: espera de "
                    f"{cfg.botdown_wait_minutes} min ({pending} URL(s) pendientes)."
                )
                await self._sleep(cfg.botdown_wait_minutes * 60)
            if await self._probe_bot():
                self._notify("El bot vuelve a responder; se retoma el flujo normal.")
                await self._sleep(_BOT_SETTLE_SECONDS)
                self.unpark_all()
                return
            if self.http_available():
                if blocks >= cfg.botdown_max_blocks:
                    self._abort(
                        f"El bot sigue caído tras {blocks} bloque(s) de "
                        f"{cfg.botdown_block_minutes} min."
                    )
                    return
            elif self._count_open_jobs() > cfg.botdown_wait_threshold and waits >= cfg.botdown_wait_attempts:
                self._abort(
                    f"El bot sigue caído tras esperar {waits * cfg.botdown_wait_minutes} min "
                    "y no hay descarga HTTP disponible."
                )
                return

    async def _http_block(self, interval: float, duration: float) -> bool:
        """HTTP downloads for ``duration`` s; True when no open job is left."""

        deadline = self._clock() + duration
        tried: set[int] = set()
        while self._clock() < deadline and self.http_available():
            job = self._next_open_job(tried)
            if job is None:
                return True
            tried.add(_job_id(job))
            account = self._accounts.get_by_id(job.account_id)
            if account is None:
                continue
            await self._http_download(job, account, normal_interval=interval)
        return self._count_open_jobs() == 0

    def _batch_accounts(self) -> list[Account]:
        if self._batch_id is None:
            return []
        return [
            account
            for account in self._accounts.list_by_batch(self._batch_id)
            if account.id is not None and account.status in PROCESSABLE_ACCOUNT_STATUSES
        ]

    def _next_open_job(self, tried: set[int]) -> UrlJob | None:
        for account in self._batch_accounts():
            for job in self._jobs.list_by_account(account.id):
                if job.id not in tried and self._is_http_candidate(job):
                    return job
        return None

    def _count_open_jobs(self) -> int:
        return sum(
            1
            for account in self._batch_accounts()
            for job in self._jobs.list_by_account(account.id)
            if self._is_http_candidate(job)
        )

    def _abort(self, reason: str) -> None:
        self._aborted = True
        self._abort_reason = reason
        failed: list[str] = []
        for account in self._batch_accounts():
            if any(
                self._is_http_candidate(job) or job.status in _OPEN_STATUSES
                for job in self._jobs.list_by_account(account.id)
            ):
                self._accounts.update_status(account.id, AccountStatus.FAILED)
                failed.append(account.username)
        logger.error("Run stopped by the bot-down guard: {} accounts={}", reason, failed)
        self._notify(
            f"{reason} Se detiene la ejecución; las cuentas pendientes quedan en FAILED "
            "para que decidas (revisa el bot y reanuda el lote)."
        )

    # -- one HTTP download ----------------------------------------------
    async def _http_download(
        self,
        job: UrlJob,
        account: Account | None,
        *,
        normal_interval: float | None = None,
    ) -> str:
        """Returns OK, NOT_FOUND, FAILED or DISABLED."""

        await self._wait_slot(normal_interval)
        if not self.http_available():
            return "DISABLED"
        job_id = _job_id(job)
        self._last_http = self._clock()
        paths: list[Path] | None = None
        for attempt in (1, 2):
            try:
                files = await asyncio.to_thread(self._client.fetch_media_files, job.url)
                paths = await self._download_all(files)
                break
            except HttpFallbackError as exc:
                outcome = await self._on_error(exc, job, attempt)
                if outcome != "RETRY":
                    return outcome
        if paths is None:
            return "FAILED"
        try:
            result = await self._processor.process_http(job_id, paths)
        except Exception:
            logger.exception("Finishing the HTTP download failed: job_id={}", job_id)
            return "FAILED"
        self._http_total += 1
        self._rate_hits = 0
        if self._connection is not None:
            record_http_download(self._connection, job_id, len(paths))
        logger.info(
            "HTTP download finished: job_id={} account={} files={} status={} total={}",
            job_id,
            account.username if account else "-",
            len(paths),
            result.job.status.value,
            self._http_total,
        )
        self._notify(
            f"Descargado por HTTP: {job.url} ({len(paths)} archivo(s), "
            f"{self._http_total} en esta ejecución)"
        )
        return "OK" if result.job.status is UrlJobStatus.COMPLETED else "FAILED"

    async def _download_all(self, files: list[MediaFile]) -> list[Path]:
        paths: list[Path] = []
        try:
            for media in files:
                destination = _unique(self._download_folder, media.name, media.extension)
                await asyncio.to_thread(self._client.download, media, destination)
                paths.append(destination)
        except HttpFallbackError:
            for path in paths:
                path.unlink(missing_ok=True)
            raise
        return paths

    async def _on_error(self, exc: HttpFallbackError, job: UrlJob, attempt: int) -> str:
        job_id = _job_id(job)
        if exc.kind in (KIND_SESSION, KIND_NO_SESSION):
            self._disable(str(exc))
            return "DISABLED"
        if exc.kind == KIND_RATE_LIMIT:
            self._rate_hits += 1
            cfg = self._config
            if self._rate_hits >= cfg.max_429:
                self._disable(
                    f"Instagram devolvió 429 (demasiadas peticiones) {self._rate_hits} veces "
                    "seguidas. Espera un buen rato (horas) antes de volver a usar la descarga "
                    "HTTP o usa otra cuenta en Sesión HTTP."
                )
                return "DISABLED"
            minutes = cfg.pause_429_minutes * (2 ** (self._rate_hits - 1))
            self._notify(f"Instagram pide ir más despacio (429): pausa de {minutes} min.")
            await self._sleep(minutes * 60)
            return "FAILED"
        if exc.kind == KIND_NOT_FOUND:
            self._jobs.update_error(
                job_id,
                status=UrlJobStatus.RETRY_PENDING,
                last_error=f"Media not found or unavailable [HTTP: {exc}]",
                last_error_type=MEDIA_NOT_FOUND_ERROR_TYPE,
                non_retryable=False,
                retries=job.retries,
            )
            logger.warning("HTTP: media not found: job_id={} url={}", job_id, job.url)
            return "NOT_FOUND"
        if exc.kind == KIND_TRANSIENT and attempt == 1:
            logger.warning("HTTP transient error, retrying once: job_id={} error={}", job_id, exc)
            await self._sleep(5.0)
            return "RETRY"
        logger.warning("HTTP download failed: job_id={} kind={} error={}", job_id, exc.kind, exc)
        return "FAILED"

    def _disable(self, reason: str) -> None:
        if self._disabled_reason is not None:
            return
        self._disabled_reason = reason
        logger.error("HTTP fallback disabled for this run: {}", reason)
        self._notify(f"Descarga HTTP desactivada en esta ejecución. {reason}")

    # -- timing ---------------------------------------------------------
    async def _wait_slot(self, normal_interval: float | None) -> None:
        if self._last_http is None:
            return
        cfg = self._config
        interval = base_interval(
            self._now(),
            interval_seconds=normal_interval if normal_interval is not None else cfg.interval_seconds,
            night_enabled=cfg.night_enabled,
            night_start=cfg.night_start,
            night_end=cfg.night_end,
            night_interval_seconds=cfg.night_interval_seconds,
        )
        wait = with_jitter(interval, cfg.jitter_percent, self._rng) - (
            self._clock() - self._last_http
        )
        if wait > 0:
            self._notify(f"Siguiente petición HTTP en {int(wait)} s.")
            await self._sleep(wait)

    async def _sleep(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0:
            step = min(remaining, _SLEEP_SLICE_SECONDS)
            await self._sleeper(step)
            remaining -= step

    def _fresh(self, result: UrlJobProcessorResult) -> UrlJobProcessorResult:
        job = self._jobs.get_by_id(_job_id(result.job))
        return UrlJobProcessorResult(job=job or result.job, files=result.files)

    def _notify(self, text: str) -> None:
        logger.info("HTTP fallback: {}", text)
        if self._status_callback is None:
            return
        try:
            self._status_callback(text)
        except Exception:
            logger.warning("HTTP status callback failed", exc_info=True)


def _unique(folder: Path, name: str, extension: str) -> Path:
    candidate = folder / f"{name}{extension}"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{name}_{counter}{extension}"
        counter += 1
    return candidate


def _job_id(job: UrlJob) -> int:
    if job.id is None:
        raise ValueError("UrlJob.id is required")
    return job.id


def _account_id(account: Account) -> int:
    if account.id is None:
        raise ValueError("Account.id is required")
    return account.id


__all__ = [
    "AttemptOutcome",
    "HttpFallbackCoordinator",
    "bot_answered",
    "is_silent",
]
