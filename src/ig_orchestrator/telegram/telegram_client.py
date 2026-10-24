from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.settings import Settings

logger = get_logger()


class TelegramClientError(RuntimeError):
    """Raised when the Telegram client cannot be created or used."""


@dataclass(frozen=True)
class TelegramClientConfig:
    """Non-logging Telegram client configuration."""

    api_id: int
    api_hash: str = field(repr=False)
    session_name: str
    bot_username: str
    flood_sleep_threshold: int = 60

    @classmethod
    def from_settings(cls, settings: Settings) -> TelegramClientConfig:
        return cls(
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            session_name=settings.telethon_session_name,
            bot_username=settings.telegram_download_bot_username,
            flood_sleep_threshold=settings.telegram_flood_sleep_threshold,
        )


TelethonClientFactory = Callable[[str, int, str], Any]


class BotMessageSubscription:
    """Queue of incoming bot messages fed by a Telethon NewMessage handler."""

    def __init__(self, client: Any, handler: Any, queue: asyncio.Queue[Any]) -> None:
        self._client = client
        self._handler = handler
        self._queue = queue

    async def get(self, timeout: float) -> Any | None:
        """Wait up to timeout seconds for the next message; None if none arrived."""

        try:
            return await asyncio.wait_for(self._queue.get(), timeout=max(timeout, 0.0))
        except asyncio.TimeoutError:
            return None

    def get_nowait(self) -> Any | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def close(self) -> None:
        try:
            self._client.remove_event_handler(self._handler)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not remove Telegram event handler: {}", exc)


class TelethonTelegramClient:
    """Small async wrapper around Telethon for the download bot workflow."""

    def __init__(
        self,
        config: TelegramClientConfig,
        *,
        client_factory: TelethonClientFactory | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or _default_client_factory
        self._client: Any | None = None

    @property
    def bot_username(self) -> str:
        return self._config.bot_username

    @property
    def is_started(self) -> bool:
        return self._client is not None

    async def __aenter__(self) -> TelethonTelegramClient:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()

    async def start(self) -> None:
        """Create and start Telethon, reusing the configured session if present."""

        if self._client is not None:
            return

        client = self._client_factory(
            self._config.session_name,
            self._config.api_id,
            self._config.api_hash,
        )
        # Telethon sleeps silently on FloodWaits up to this many seconds.
        try:
            client.flood_sleep_threshold = self._config.flood_sleep_threshold
        except AttributeError:  # pragma: no cover - fakes without the attribute
            pass
        await client.start()
        self._client = client
        logger.info(
            "Telegram download acceleration (cryptg): {}",
            "yes" if cryptg_available() else "no (slow Python AES; pip install cryptg)",
        )

    async def disconnect(self) -> None:
        if self._client is None:
            return

        await self._client.disconnect()
        self._client = None

    async def send_message_to_bot(self, text: str) -> Any:
        """Send a message to the configured Telegram download bot."""

        return await self.send_message_to(self._config.bot_username, text)

    async def send_message_to(self, target: str, text: str) -> Any:
        """Send a message to Saved Messages (`me`) or another chat."""

        message = text.strip()
        if not message:
            raise ValueError("message text must not be blank")
        destination = (target or "me").strip() or "me"
        client = self._require_started_client()
        return await client.send_message(destination, message)

    def subscribe_bot_messages(self) -> BotMessageSubscription:
        """Start receiving incoming bot messages as events (no GetHistory polling)."""

        client = self._require_started_client()
        from telethon import events

        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def handler(event: Any) -> None:
            queue.put_nowait(event.message)

        client.add_event_handler(
            handler,
            events.NewMessage(chats=self._config.bot_username, incoming=True),
        )
        return BotMessageSubscription(client, handler, queue)

    async def get_latest_bot_messages(self, *, limit: int = 10) -> list[Any]:
        """Return the latest messages from the configured bot."""

        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        client = self._require_started_client()
        return list(await client.get_messages(self._config.bot_username, limit=limit))

    async def get_bot_messages_after(
        self,
        timestamp: datetime,
        *,
        limit: int = 100,
    ) -> list[Any]:
        """Return bot messages newer than timestamp in chronological order."""

        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        threshold = _as_utc(timestamp)
        client = self._require_started_client()
        messages = [
            message
            async for message in client.iter_messages(
                self._config.bot_username,
                limit=limit,
            )
            if _message_datetime_is_after(message, threshold)
        ]
        messages.reverse()
        return messages

    async def download_message_media(self, message: Any, destination: str) -> str | None:
        """Download media from a bot message using Telethon."""

        client = self._require_started_client()
        downloaded_path = await client.download_media(message, file=destination)
        return str(downloaded_path) if downloaded_path else None

    def _require_started_client(self) -> Any:
        if self._client is None:
            raise TelegramClientError("Telegram client is not started")
        return self._client


def cryptg_available() -> bool:
    try:
        import cryptg  # noqa: F401
    except ImportError:
        return False
    return True


def _default_client_factory(session_name: str, api_id: int, api_hash: str) -> Any:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise TelegramClientError(
            "Telethon is not installed. Install project requirements before using Telegram."
        ) from exc

    return TelegramClient(session_name, api_id, api_hash)


def _message_datetime_is_after(message: Any, threshold: datetime) -> bool:
    message_date = getattr(message, "date", None)
    if not isinstance(message_date, datetime):
        return False
    return _as_utc(message_date) > threshold


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "BotMessageSubscription",
    "cryptg_available",
    "TelegramClientConfig",
    "TelegramClientError",
    "TelethonTelegramClient",
]
