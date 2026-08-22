from __future__ import annotations

import logging
from sqlite3 import Connection
from typing import TYPE_CHECKING, Any

from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.models import UrlJob
from ig_orchestrator.settings import Settings
from ig_orchestrator.telegram.telegram_client import (
    TelegramClientConfig,
    TelethonTelegramClient,
)

if TYPE_CHECKING:
    from ig_orchestrator.orchestration.batch_orchestrator import BatchOrchestratorResult


logger = logging.getLogger(__name__)

DEFAULT_BATCH_TEMPLATE = (
    "Instagram Orchestrator\n"
    "Lote {batch_name} (id={batch_id}) completado\n"
    "Cuentas: {accounts_done}/{accounts_total} · URLs ok: {urls_ok} · fallidas: {urls_failed}"
)
DEFAULT_ERROR_TEMPLATE = "{username} {url} {error}"


def _setting(connection: Connection, key: str, default: str) -> str:
    if not is_gui_schema(connection):
        return default
    row = connection.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None or not str(row["value"]).strip():
        return default
    return str(row["value"])


def notifications_enabled(connection: Connection) -> bool:
    return _setting(connection, "notify.enabled", "0") in {"1", "true", "yes"}


def notification_target(connection: Connection) -> str:
    return _setting(connection, "notify.target", "me")


def format_template(template: str, **values: object) -> str:
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


async def send_user_notification(
    client: TelethonTelegramClient,
    text: str,
    *,
    target: str = "me",
) -> None:
    await client.send_message_to(target, text)


async def send_ephemeral_notification(
    settings: Settings,
    text: str,
    *,
    target: str = "me",
    client_factory: Any = None,
) -> None:
    config = TelegramClientConfig.from_settings(settings)
    async with TelethonTelegramClient(config, client_factory=client_factory) as client:
        await send_user_notification(client, text, target=target)


async def notify_batch_complete(
    connection: Connection,
    client: TelethonTelegramClient | None,
    result: BatchOrchestratorResult,
) -> None:
    if client is None or not notifications_enabled(connection):
        return
    if result.error:
        return
    template = _setting(
        connection, "notify.template_batch_done", DEFAULT_BATCH_TEMPLATE
    )
    accounts_total = len(result.account_results)
    accounts_done = sum(
        1
        for item in result.account_results
        if item.account.status.value == "COMPLETED"
    )
    text = format_template(
        template,
        batch_name=result.batch.batch_name,
        batch_id=result.batch.id or "-",
        accounts_done=accounts_done,
        accounts_total=accounts_total,
        urls_ok=result.summary.completed_urls,
        urls_failed=result.summary.failed_urls,
    )
    try:
        await send_user_notification(
            client, text, target=notification_target(connection)
        )
    except Exception:
        logger.warning("Batch completion Telegram notify failed", exc_info=True)


def bot_error_should_notify(connection: Connection, error_code: str | None) -> bool:
    if not error_code or not is_gui_schema(connection):
        return False
    row = connection.execute(
        """
        SELECT notify_on_match, notify_template
        FROM bot_errors
        WHERE code = ? AND is_active = 1
        """,
        (error_code,),
    ).fetchone()
    return bool(row and int(row["notify_on_match"]) == 1)


def bot_error_template(connection: Connection, error_code: str) -> str:
    row = connection.execute(
        "SELECT notify_template FROM bot_errors WHERE code = ?",
        (error_code,),
    ).fetchone()
    if row is None or not (row["notify_template"] or "").strip():
        return DEFAULT_ERROR_TEMPLATE
    return str(row["notify_template"])


async def notify_bot_error(
    connection: Connection,
    client: TelethonTelegramClient | None,
    job: UrlJob,
    *,
    username: str = "",
) -> None:
    if client is None or not notifications_enabled(connection):
        return
    code = job.last_error_type
    if not bot_error_should_notify(connection, code):
        return
    text = format_template(
        bot_error_template(connection, code or ""),
        username=username,
        url=job.url,
        error=job.last_error or code or "",
    )
    try:
        await send_user_notification(
            client, text, target=notification_target(connection)
        )
    except Exception:
        logger.warning("Bot-error Telegram notify failed", exc_info=True)


__all__ = [
    "DEFAULT_BATCH_TEMPLATE",
    "format_template",
    "notifications_enabled",
    "notify_batch_complete",
    "notify_bot_error",
    "send_ephemeral_notification",
    "send_user_notification",
]
