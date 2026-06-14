from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from ig_orchestrator.settings import Settings
from ig_orchestrator.telegram import (
    TelegramClientConfig,
    TelegramClientError,
    TelethonTelegramClient,
)


@dataclass
class FakeMessage:
    id: int
    text: str
    date: datetime


class FakeTelethonClient:
    def __init__(self) -> None:
        self.started = False
        self.disconnected = False
        self.sent_messages: list[tuple[str, str]] = []
        self.messages = [
            FakeMessage(1, "old", datetime(2026, 6, 14, 10, tzinfo=timezone.utc)),
            FakeMessage(2, "newer", datetime(2026, 6, 14, 12, tzinfo=timezone.utc)),
            FakeMessage(3, "newest", datetime(2026, 6, 14, 13, tzinfo=timezone.utc)),
        ]

    async def start(self) -> None:
        self.started = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def send_message(self, entity: str, message: str) -> FakeMessage:
        self.sent_messages.append((entity, message))
        return FakeMessage(99, message, datetime(2026, 6, 14, 14, tzinfo=timezone.utc))

    async def get_messages(self, entity: str, *, limit: int) -> list[FakeMessage]:
        assert entity == "@download_bot"
        return self.messages[-limit:]

    async def iter_messages(self, entity: str, *, limit: int) -> Any:
        assert entity == "@download_bot"
        for message in reversed(self.messages[-limit:]):
            yield message


def test_config_from_settings_hides_api_hash_in_repr() -> None:
    settings = Settings(
        telegram_api_id=12345,
        telegram_api_hash="secret_hash",
        telethon_session_name="telegram_user_session",
        telegram_download_bot_username="@download_bot",
        telegram_desktop_download_folder=_path("telegram"),
        working_folder=_path("work"),
        reports_folder=_path("reports"),
        sqlite_db_path=_path("data/orchestrator.db"),
        max_retries=5,
        retry_base_seconds=90,
        retry_max_seconds=900,
        download_wait_timeout_seconds=300,
        download_stable_seconds=10,
    )

    config = TelegramClientConfig.from_settings(settings)

    assert config.api_id == 12345
    assert config.api_hash == "secret_hash"
    assert config.session_name == "telegram_user_session"
    assert config.bot_username == "@download_bot"
    assert "secret_hash" not in repr(config)


def test_start_reuses_existing_client_until_disconnected() -> None:
    asyncio.run(_assert_start_reuses_existing_client_until_disconnected())


async def _assert_start_reuses_existing_client_until_disconnected() -> None:
    fake_client = FakeTelethonClient()
    created: list[tuple[str, int, str]] = []
    wrapper = TelethonTelegramClient(
        _config(),
        client_factory=lambda session, api_id, api_hash: _factory(
            created, fake_client, session, api_id, api_hash
        ),
    )

    await wrapper.start()
    await wrapper.start()

    assert fake_client.started is True
    assert created == [("telegram_user_session", 12345, "secret_hash")]
    assert wrapper.is_started is True

    await wrapper.disconnect()

    assert fake_client.disconnected is True
    assert wrapper.is_started is False


def test_send_message_to_configured_bot() -> None:
    asyncio.run(_assert_send_message_to_configured_bot())


async def _assert_send_message_to_configured_bot() -> None:
    fake_client = FakeTelethonClient()
    wrapper = TelethonTelegramClient(_config(), client_factory=lambda *_args: fake_client)

    await wrapper.start()
    sent = await wrapper.send_message_to_bot(" https://www.instagram.com/reel/ABC/ ")

    assert sent.id == 99
    assert fake_client.sent_messages == [
        ("@download_bot", "https://www.instagram.com/reel/ABC/")
    ]


def test_get_latest_bot_messages() -> None:
    asyncio.run(_assert_get_latest_bot_messages())


async def _assert_get_latest_bot_messages() -> None:
    wrapper = TelethonTelegramClient(
        _config(),
        client_factory=lambda *_args: FakeTelethonClient(),
    )

    await wrapper.start()
    messages = await wrapper.get_latest_bot_messages(limit=2)

    assert [message.text for message in messages] == ["newer", "newest"]


def test_get_bot_messages_after_filters_and_returns_chronological_order() -> None:
    asyncio.run(_assert_get_bot_messages_after_filters_and_returns_chronological_order())


async def _assert_get_bot_messages_after_filters_and_returns_chronological_order() -> None:
    wrapper = TelethonTelegramClient(
        _config(),
        client_factory=lambda *_args: FakeTelethonClient(),
    )

    await wrapper.start()
    messages = await wrapper.get_bot_messages_after(datetime(2026, 6, 14, 11))

    assert [message.text for message in messages] == ["newer", "newest"]


def test_using_client_before_start_raises_clear_error() -> None:
    asyncio.run(_assert_using_client_before_start_raises_clear_error())


async def _assert_using_client_before_start_raises_clear_error() -> None:
    wrapper = TelethonTelegramClient(
        _config(),
        client_factory=lambda *_args: FakeTelethonClient(),
    )

    with pytest.raises(TelegramClientError, match="not started"):
        await wrapper.get_latest_bot_messages()


def _config() -> TelegramClientConfig:
    return TelegramClientConfig(
        api_id=12345,
        api_hash="secret_hash",
        session_name="telegram_user_session",
        bot_username="@download_bot",
    )


def _factory(
    created: list[tuple[str, int, str]],
    fake_client: FakeTelethonClient,
    session: str,
    api_id: int,
    api_hash: str,
) -> FakeTelethonClient:
    created.append((session, api_id, api_hash))
    return fake_client


def _path(value: str) -> Any:
    from pathlib import Path

    return Path(value)
