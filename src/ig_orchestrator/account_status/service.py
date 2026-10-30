"""Persistence and execution of «check account status» analyses (feat-uc7-1).

A run lists the catalog accounts under a folder, stores one row per account and keeps it across
sessions, so a stopped or rate-limited analysis can be resumed and its results used to move folders.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection

from ig_orchestrator.account_status.checker import (
    AccountStatus,
    CheckOutcome,
    Fetcher,
    check_account,
    default_fetcher,
)
from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.paths import rel_key

RUN_RUNNING = "RUNNING"
RUN_STOPPED = "STOPPED"
RUN_RATE_LIMITED = "RATE_LIMITED"
RUN_COMPLETED = "COMPLETED"

REUSE_SETTING = "accountcheck.reuse_hours"
DEFAULT_REUSE_HOURS = 48  # 2 days

STOP_MANUAL = "MANUAL"
STOP_RATE_LIMIT = "RATE_LIMIT"


@dataclass(frozen=True, slots=True)
class CheckRun:
    id: int
    folder_id: int | None
    folder_rel: str
    state: str
    stop_reason: str | None
    total: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    id: int
    run_id: int
    account_id: int | None
    username: str
    rel_path: str
    status: str
    http_status: int | None
    detail: str
    checked_at: str | None
    current_path: str | None = None  # where the catalog has the account now (None: unknown)
    source_run_id: int | None = None  # answer copied from this earlier analysis (not asked again)

    @property
    def reused(self) -> bool:
        return self.source_run_id is not None

    @property
    def moved(self) -> bool:
        """The account is no longer where the analysis found it."""

        return bool(self.current_path) and rel_key(self.current_path) != rel_key(self.rel_path)

    @property
    def destination(self) -> str:
        return (self.current_path or "") if self.moved else ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(row) -> CheckRun:
    return CheckRun(
        int(row["id"]), row["folder_id"], str(row["folder_rel"]), str(row["state"]),
        row["stop_reason"], int(row["total"]), str(row["created_at"]), str(row["updated_at"]),
    )


def _result(row) -> CheckResult:
    return CheckResult(
        int(row["id"]), int(row["run_id"]), row["account_id"], str(row["username"]),
        str(row["rel_path"] or ""), str(row["status"]), row["http_status"],
        str(row["detail"] or ""), row["checked_at"],
        row["current_rel"] if "current_rel" in row.keys() else None,
        row["source_run_id"] if "source_run_id" in row.keys() else None,
    )


def reuse_hours(connection: Connection) -> int:
    """How recent an earlier answer must be to be reused (hours; 0 = never reuse)."""

    try:
        row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (REUSE_SETTING,)).fetchone()
    except Exception:  # v1 database without app_settings
        return DEFAULT_REUSE_HOURS
    if row is None:
        return DEFAULT_REUSE_HOURS
    try:
        return max(0, int(str(row[0]).strip()))
    except ValueError:
        return DEFAULT_REUSE_HOURS


class AccountStatusService:
    def __init__(self, connection: Connection) -> None:
        self.conn = connection

    # ----------------------------------------------------------------- runs
    def create_run(self, folder_id: int, reuse_hours: int = 0) -> CheckRun:
        """Snapshot the accounts under ``folder_id`` (descendants included) as a new run.

        With ``reuse_hours`` > 0, an account already answered (exists / gone) by another analysis in that
        window keeps that answer (``source_run_id``) instead of being asked again.
        """

        fs = FsOperationService(self.conn)
        folder = fs.folder(folder_id)
        accounts = fs.accounts_under(folder.rel_path)
        now = _now()
        cursor = self.conn.execute(
            "INSERT INTO account_check_runs (folder_id, folder_rel, state, total, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (folder_id, folder.rel_path, RUN_STOPPED, len(accounts), now, now),
        )
        run_id = int(cursor.lastrowid)
        self.conn.executemany(
            "INSERT OR IGNORE INTO account_check_results (run_id, account_id, username, rel_path)"
            " VALUES (?, ?, ?, ?)",
            [(run_id, int(a["id"]), str(a["username"]), str(a["rel_path"])) for a in accounts],
        )
        self.conn.execute(
            "UPDATE account_check_runs SET total = (SELECT COUNT(*) FROM account_check_results WHERE run_id = ?)"
            " WHERE id = ?", (run_id, run_id),
        )
        if reuse_hours > 0:
            self._reuse_recent(run_id, reuse_hours)
        if not self.pending(run_id):
            self.conn.execute("UPDATE account_check_runs SET state = ? WHERE id = ?", (RUN_COMPLETED, run_id))
        self.conn.commit()
        return self.run(run_id)

    def _reuse_recent(self, run_id: int, hours: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        reused = 0
        for row in self.conn.execute("SELECT id, username FROM account_check_results WHERE run_id = ?", (run_id,)).fetchall():
            earlier = self.conn.execute(
                "SELECT run_id, status, http_status, detail, checked_at FROM account_check_results"
                " WHERE username = ? AND run_id <> ? AND status IN ('AVAILABLE', 'UNAVAILABLE') AND checked_at >= ?"
                " ORDER BY checked_at DESC LIMIT 1", (row["username"], run_id, cutoff),
            ).fetchone()
            if earlier is None:
                continue
            self.conn.execute(
                "UPDATE account_check_results SET status = ?, http_status = ?, detail = ?, checked_at = ?,"
                " source_run_id = ? WHERE id = ?",
                (earlier["status"], earlier["http_status"], earlier["detail"], earlier["checked_at"],
                 earlier["run_id"], row["id"]),
            )
            reused += 1
        return reused

    def force_reanalysis(self, run_id: int) -> int:
        """Forget the answers copied from other analyses so this run asks for them again."""

        cursor = self.conn.execute(
            "UPDATE account_check_results SET status = 'PENDING', http_status = NULL, detail = NULL,"
            " checked_at = NULL, source_run_id = NULL WHERE run_id = ? AND source_run_id IS NOT NULL", (run_id,),
        )
        self.conn.execute(
            "UPDATE account_check_runs SET state = ?, stop_reason = NULL, updated_at = ? WHERE id = ?",
            (RUN_STOPPED, _now(), run_id),
        )
        self.conn.commit()
        return cursor.rowcount

    def run(self, run_id: int) -> CheckRun:
        row = self.conn.execute("SELECT * FROM account_check_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _run(row)

    def runs(self, folder_id: int | None = None) -> list[CheckRun]:
        sql = "SELECT * FROM account_check_runs"
        params: tuple = ()
        if folder_id is not None:
            sql += " WHERE folder_id = ?"
            params = (folder_id,)
        return [_run(r) for r in self.conn.execute(sql + " ORDER BY id DESC", params)]

    def delete_run(self, run_id: int) -> None:
        self.conn.execute("DELETE FROM account_check_results WHERE run_id = ?", (run_id,))
        self.conn.execute("DELETE FROM account_check_runs WHERE id = ?", (run_id,))
        self.conn.commit()

    def set_state(self, run_id: int, state: str, reason: str | None = None) -> None:
        self.conn.execute(
            "UPDATE account_check_runs SET state = ?, stop_reason = ?, updated_at = ? WHERE id = ?",
            (state, reason, _now(), run_id),
        )
        self.conn.commit()

    def recover_interrupted(self) -> int:
        """A run left RUNNING by a crash is shown as stopped (it can be resumed)."""

        cursor = self.conn.execute(
            "UPDATE account_check_runs SET state = ?, stop_reason = ? WHERE state = ?",
            (RUN_STOPPED, STOP_MANUAL, RUN_RUNNING),
        )
        self.conn.commit()
        return cursor.rowcount

    # -------------------------------------------------------------- results
    def results(self, run_id: int) -> list[CheckResult]:
        return [
            _result(r)
            for r in self.conn.execute(
                "SELECT r.*, a.rel_path AS current_rel FROM account_check_results r"
                " LEFT JOIN catalog_accounts a ON a.id = r.account_id WHERE r.run_id = ? ORDER BY r.username",
                (run_id,),
            )
        ]

    def pending(self, run_id: int) -> list[CheckResult]:
        """Accounts without a conclusive answer (never checked, or unknown) in catalog order."""

        return [
            _result(r)
            for r in self.conn.execute(
                "SELECT * FROM account_check_results WHERE run_id = ? AND status IN ('PENDING', 'UNKNOWN')"
                " ORDER BY id", (run_id,),
            )
        ]

    def record(self, result_id: int, outcome: CheckOutcome) -> None:
        self.conn.execute(
            "UPDATE account_check_results SET status = ?, http_status = ?, detail = ?, checked_at = ?"
            " WHERE id = ?",
            (outcome.status.value, outcome.http_status, outcome.detail, _now(), result_id),
        )
        self.conn.execute(
            "UPDATE account_check_runs SET updated_at = ? WHERE id = (SELECT run_id FROM account_check_results WHERE id = ?)",
            (_now(), result_id),
        )
        self.conn.commit()

    def summary(self, run_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM account_check_results WHERE run_id = ? GROUP BY status", (run_id,)
        )
        return {str(r["status"]): int(r["n"]) for r in rows}


def run_checks(
    service: AccountStatusService,
    run_id: int,
    *,
    interval_seconds: float,
    timeout_seconds: float,
    stop: threading.Event,
    on_result: Callable[[CheckResult], None] | None = None,
    fetcher: Fetcher = default_fetcher,
    sleep: Callable[[float], None] | None = None,
) -> str:
    """Check the pending accounts one by one, ``interval_seconds`` apart.

    Stops at the first HTTP 429 (``RATE_LIMITED``) or when ``stop`` is set (``STOPPED``); the state is
    saved either way so the run can be resumed. Returns the final run state.
    """

    wait = sleep or (lambda seconds: stop.wait(seconds))
    service.set_state(run_id, RUN_RUNNING)
    first = True
    state = RUN_COMPLETED
    reason: str | None = None
    for item in service.pending(run_id):
        if stop.is_set():
            state, reason = RUN_STOPPED, STOP_MANUAL
            break
        if not first:
            wait(interval_seconds)
            if stop.is_set():
                state, reason = RUN_STOPPED, STOP_MANUAL
                break
        first = False
        outcome = check_account(item.username, timeout=timeout_seconds, fetcher=fetcher)
        if outcome.rate_limited:
            service.record(item.id, outcome)
            state, reason = RUN_RATE_LIMITED, STOP_RATE_LIMIT
            break
        service.record(item.id, outcome)
        if on_result is not None:
            on_result(_refetch(service, item.id))
    else:
        if service.pending(run_id):  # accounts left UNKNOWN stay pending: not a completed analysis
            state = RUN_STOPPED
            reason = "UNKNOWN_LEFT"
    service.set_state(run_id, state, reason)
    return state


def _refetch(service: AccountStatusService, result_id: int) -> CheckResult:
    row = service.conn.execute(
        "SELECT r.*, a.rel_path AS current_rel FROM account_check_results r"
        " LEFT JOIN catalog_accounts a ON a.id = r.account_id WHERE r.id = ?", (result_id,)
    ).fetchone()
    return _result(row)


__all__ = [
    "AccountStatus",
    "AccountStatusService",
    "CheckResult",
    "CheckRun",
    "RUN_COMPLETED",
    "RUN_RATE_LIMITED",
    "RUN_RUNNING",
    "RUN_STOPPED",
    "REUSE_SETTING",
    "reuse_hours",
    "run_checks",
]
