"""Bot health probe: send a known-good URL and see whether the bot answers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from ig_orchestrator.logging_config import get_logger

logger = get_logger()

BotProbe = Callable[[], Awaitable[bool]]


class TelegramBotProbe:
    """Any message from the bot after our probe counts as «the bot is alive».

    Error replies ("Media not found") also prove it is alive. Nothing is
    downloaded and nothing reaches the library.
    """

    def __init__(
        self,
        telegram_client: Any,
        urls: tuple[str, ...],
        timeout_seconds: float,
        *,
        poll_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = telegram_client
        self._urls = urls
        self._timeout = timeout_seconds
        self._poll = poll_seconds
        self._clock = clock
        self._sleeper = sleeper

    async def __call__(self) -> bool:
        for url in self._urls:
            if await self._probe_one(url):
                return True
        return False

    async def _probe_one(self, url: str) -> bool:
        since = datetime.now(timezone.utc) - timedelta(seconds=1)
        try:
            sent = await self._client.send_message_to_bot(url)
        except Exception as exc:
            logger.warning("Bot probe could not be sent: {}", exc)
            return False
        sent_id = getattr(sent, "id", None)
        deadline = self._clock() + self._timeout
        while self._clock() < deadline:
            try:
                messages = await self._client.get_bot_messages_after(since, limit=30)
            except Exception as exc:
                logger.warning("Bot probe read failed: {}", exc)
                messages = []
            for message in messages:
                if getattr(message, "out", False):
                    continue
                message_id = getattr(message, "id", None)
                if isinstance(sent_id, int) and isinstance(message_id, int) and message_id <= sent_id:
                    continue
                logger.info("Bot probe answered: url={}", url)
                return True
            await self._sleeper(self._poll)
        logger.warning("Bot probe got no answer: url={}", url)
        return False


__all__ = ["BotProbe", "TelegramBotProbe"]
