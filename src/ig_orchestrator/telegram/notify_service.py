from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
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


def bot_api_credentials(connection: Connection) -> tuple[str, str] | None:
    """Return (token, chat_id) when the Bot API channel is configured."""
    token = _setting(connection, "notify.bot_token", "").strip()
    chat_id = _setting(connection, "notify.bot_chat_id", "").strip()
    if token and chat_id:
        return token, chat_id
    return None


def send_bot_api_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    urlopen: Any = None,
    timeout: float = 20.0,
) -> None:
    """Send ``text`` through the Telegram Bot API (blocking).

    The sender is the bot, so Telegram notifies the phone (messages sent by
    your own account to "me" never do). Raises ``RuntimeError`` on failure with
    a message that never contains the token.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("description", "")
        except Exception:
            detail = ""
        raise RuntimeError(f"Bot API HTTP {exc.code}: {detail}".strip()) from None
    except Exception as exc:
        raise RuntimeError(f"Bot API request failed: {type(exc).__name__}") from None
    if not body.get("ok", False):
        raise RuntimeError(f"Bot API error: {body.get('description', 'unknown')}")


async def deliver_notification(
    connection: Connection,
    client: TelethonTelegramClient | None,
    text: str,
) -> bool:
    """Send via Bot API when configured (rings the phone), else via Telethon."""
    credentials = bot_api_credentials(connection)
    if credentials is not None:
        await asyncio.to_thread(send_bot_api_message, *credentials, text)
        return True
    if client is None:
        return False
    await send_user_notification(
        client, text, target=notification_target(connection)
    )
    return True


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
    if not notifications_enabled(connection):
        return
    if client is None and bot_api_credentials(connection) is None:
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
        await deliver_notification(connection, client, text)
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
    if not notifications_enabled(connection):
        return
    if client is None and bot_api_credentials(connection) is None:
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
        await deliver_notification(connection, client, text)
    except Exception:
        logger.warning("Bot-error Telegram notify failed", exc_info=True)


__all__ = [
    "DEFAULT_BATCH_TEMPLATE",
    "bot_api_credentials",
    "deliver_notification",
    "send_bot_api_message",
    "format_template",
    "notifications_enabled",
    "notify_batch_complete",
    "notify_bot_error",
    "send_ephemeral_notification",
    "send_user_notification",
]
