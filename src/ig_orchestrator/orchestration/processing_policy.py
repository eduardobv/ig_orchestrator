from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from sqlite3 import Connection

from ig_orchestrator.models import (
    Account,
    AccountStatus,
    AppConfig,
    ConfigValueType,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)


class AccountJobScope(StrEnum):
    ALL = "ALL"
    STORIES = "STORIES"
    NON_STORIES = "NON_STORIES"


STORIES_FIRST_SETTING_KEY = "processing.stories_first"
STORIES_FIRST_DEFAULT = True

PROCESSABLE_ACCOUNT_STATUSES = frozenset(
    {
        AccountStatus.PENDING,
        AccountStatus.PROCESSING,
        AccountStatus.PARTIAL,
        AccountStatus.INCOMPLETE,
    }
)
PROCESSABLE_ACCOUNT_STATUS_VALUES = tuple(
    status.value for status in PROCESSABLE_ACCOUNT_STATUSES
)

OPEN_URL_STATUSES = frozenset(
    {
        UrlJobStatus.PENDING,
        UrlJobStatus.SENT_TO_BOT,
        UrlJobStatus.WAITING_DOWNLOAD,
        UrlJobStatus.RETRY_PENDING,
        UrlJobStatus.FAILED_TEMPORARY,
    }
)
TERMINAL_URL_STATUSES = frozenset(
    {
        UrlJobStatus.COMPLETED,
        UrlJobStatus.FAILED_FINAL,
    }
)
RETRYABLE_URL_STATUSES = frozenset(
    {
        UrlJobStatus.RETRY_PENDING,
        UrlJobStatus.FAILED_TEMPORARY,
    }
)
RESUMABLE_RETRY_URL_STATUSES = frozenset(
    {
        *RETRYABLE_URL_STATUSES,
        UrlJobStatus.SENT_TO_BOT,
        UrlJobStatus.WAITING_DOWNLOAD,
    }
)


def is_story_job(job: UrlJob) -> bool:
    return job.publication_type is PublicationType.STORY


def job_in_scope(job: UrlJob, scope: AccountJobScope) -> bool:
    if scope is AccountJobScope.ALL:
        return True
    if scope is AccountJobScope.STORIES:
        return is_story_job(job)
    return not is_story_job(job)


def is_open_job(job: UrlJob) -> bool:
    return job.status in OPEN_URL_STATUSES


def ordered_main_pass_jobs(
    jobs: list[UrlJob],
    scope: AccountJobScope = AccountJobScope.ALL,
) -> list[UrlJob]:
    pending = [
        job
        for job in jobs
        if job.status is UrlJobStatus.PENDING and job_in_scope(job, scope)
    ]
    generated_stories = [
        job for job in pending if job.source is UrlSource.GENERATED_STORY
    ]
    input_stories = [
        job
        for job in pending
        if is_story_job(job) and job.source is not UrlSource.GENERATED_STORY
    ]
    others = [job for job in pending if not is_story_job(job)]
    if scope is AccountJobScope.STORIES:
        return [*generated_stories, *input_stories]
    if scope is AccountJobScope.NON_STORIES:
        return others
    return [*generated_stories, *input_stories, *others]


def existing_retry_jobs(
    jobs: list[UrlJob],
    scope: AccountJobScope = AccountJobScope.ALL,
) -> list[UrlJob]:
    return [
        job
        for job in jobs
        if job.status in RESUMABLE_RETRY_URL_STATUSES and job_in_scope(job, scope)
    ]


def jobs_by_account_id(jobs_by_account: dict[int, list[UrlJob]], account_id: int) -> list[UrlJob]:
    return jobs_by_account.get(account_id, [])


@dataclass(frozen=True, slots=True)
class AccountOrderInfo:
    """Batch-account flags that influence sweep order (not part of ``Account``)."""

    priority: int = 0
    is_new_account: bool = False


def load_account_order_info(
    connection: Connection,
    account_ids: list[int],
) -> dict[int, AccountOrderInfo]:
    """Read priority / new-account flags; empty on the legacy (v1) schema."""

    if not account_ids:
        return {}
    placeholders = ",".join("?" for _ in account_ids)
    try:
        rows = connection.execute(
            f"SELECT id, priority, is_new_account FROM batch_accounts "
            f"WHERE id IN ({placeholders})",
            account_ids,
        ).fetchall()
    except Exception:
        return {}
    return {
        int(row["id"]): AccountOrderInfo(
            priority=int(row["priority"] or 0),
            is_new_account=bool(row["is_new_account"]),
        )
        for row in rows
    }


def stories_sweep_accounts(
    accounts: list[Account],
    jobs_by_account: dict[int, list[UrlJob]],
    order_info: dict[int, AccountOrderInfo] | None = None,
) -> list[Account]:
    """Accounts with open stories: ranked priority first, then batch order."""

    info = order_info or {}
    candidates: list[tuple[int, Account]] = []
    for index, account in enumerate(accounts):
        if account.id is None:
            continue
        jobs = jobs_by_account_id(jobs_by_account, account.id)
        if any(is_open_job(job) for job in jobs if is_story_job(job)):
            candidates.append((index, account))

    def key(item: tuple[int, Account]) -> tuple[int, int, int]:
        index, account = item
        priority = info.get(account.id, AccountOrderInfo()).priority
        return (0, priority, index) if priority > 0 else (1, 0, index)

    return [account for _index, account in sorted(candidates, key=key)]


def non_story_sweep_accounts(
    accounts: list[Account],
    jobs_by_account: dict[int, list[UrlJob]],
    order_info: dict[int, AccountOrderInfo] | None = None,
) -> list[Account]:
    """Accounts with open posts/reels/highlights, lightest workload first.

    Order: fewest open non-story URLs; then more reels; then fewer posts; then
    existing accounts before new ones; then batch order.
    """

    info = order_info or {}
    candidates: list[tuple[tuple[int, int, int, bool, int], Account]] = []
    for index, account in enumerate(accounts):
        if account.id is None:
            continue
        open_others = [
            job
            for job in jobs_by_account_id(jobs_by_account, account.id)
            if not is_story_job(job) and is_open_job(job)
        ]
        if not open_others:
            continue
        reels = sum(1 for job in open_others if job.publication_type is PublicationType.REEL)
        posts = sum(1 for job in open_others if job.publication_type is PublicationType.POST)
        is_new = info.get(account.id, AccountOrderInfo()).is_new_account
        candidates.append(((len(open_others), -reels, posts, is_new, index), account))
    candidates.sort(key=lambda item: item[0])
    return [account for _key, account in candidates]


def account_status_from_jobs(jobs: list[UrlJob]) -> AccountStatus:
    if not jobs:
        return AccountStatus.COMPLETED
    completed = sum(1 for job in jobs if job.status is UrlJobStatus.COMPLETED)
    failed = sum(1 for job in jobs if job.status is UrlJobStatus.FAILED_FINAL)
    if completed == len(jobs):
        return AccountStatus.COMPLETED
    if failed == len(jobs):
        return AccountStatus.FAILED
    return AccountStatus.PARTIAL


def account_status_after_scope(
    jobs: list[UrlJob],
    scope: AccountJobScope,
    summary_status: AccountStatus,
) -> AccountStatus:
    if scope is AccountJobScope.STORIES:
        remaining_open_others = [
            job
            for job in jobs
            if not is_story_job(job) and job.status not in TERMINAL_URL_STATUSES
        ]
        if remaining_open_others:
            return AccountStatus.INCOMPLETE
    return summary_status


def parse_bool_setting(value: str | None, *, default: bool = STORIES_FIRST_DEFAULT) -> bool:
    if value is None or not str(value).strip():
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def read_stories_first_enabled(connection: Connection) -> bool:
    from ig_orchestrator.db.schema_mode import is_gui_schema

    table = "app_settings" if is_gui_schema(connection) else "app_config"
    try:
        row = connection.execute(
            f"SELECT value FROM {table} WHERE key = ?",
            (STORIES_FIRST_SETTING_KEY,),
        ).fetchone()
    except Exception:
        return STORIES_FIRST_DEFAULT
    if row is None:
        return STORIES_FIRST_DEFAULT
    return parse_bool_setting(str(row["value"]))


def write_stories_first_enabled(connection: Connection, enabled: bool) -> None:
    from ig_orchestrator.db.schema_mode import is_gui_schema

    value = "1" if enabled else "0"
    if is_gui_schema(connection):
        connection.execute(
            """
            INSERT INTO app_settings (key, value, value_type, updated_at)
            VALUES (?, ?, 'BOOLEAN', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (STORIES_FIRST_SETTING_KEY, value),
        )
    else:
        from ig_orchestrator.db.config_repository import ConfigRepository

        ConfigRepository(connection).upsert(
            AppConfig(
                key=STORIES_FIRST_SETTING_KEY,
                value=value,
                value_type=ConfigValueType.BOOLEAN,
            )
        )
        return
    connection.commit()


__all__ = [
    "AccountJobScope",
    "AccountOrderInfo",
    "OPEN_URL_STATUSES",
    "PROCESSABLE_ACCOUNT_STATUSES",
    "PROCESSABLE_ACCOUNT_STATUS_VALUES",
    "RESUMABLE_RETRY_URL_STATUSES",
    "RETRYABLE_URL_STATUSES",
    "STORIES_FIRST_DEFAULT",
    "STORIES_FIRST_SETTING_KEY",
    "TERMINAL_URL_STATUSES",
    "account_status_after_scope",
    "account_status_from_jobs",
    "existing_retry_jobs",
    "is_open_job",
    "is_story_job",
    "job_in_scope",
    "load_account_order_info",
    "non_story_sweep_accounts",
    "ordered_main_pass_jobs",
    "parse_bool_setting",
    "read_stories_first_enabled",
    "stories_sweep_accounts",
    "write_stories_first_enabled",
]
