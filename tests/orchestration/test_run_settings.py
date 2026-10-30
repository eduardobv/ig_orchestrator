from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ig_orchestrator.db import connect, init_database
from ig_orchestrator.db.gui_migrations import init_gui_database
from ig_orchestrator.orchestration.retry_policy import calculate_retry_decision
from ig_orchestrator.orchestration.run_settings import (
    RUN_SETTING_SPECS,
    load_run_settings,
    reset_run_settings,
    save_run_settings,
    validate_run_setting,
)
from ig_orchestrator.models import PublicationType
from ig_orchestrator.settings import Settings


def _env(tmp_path: Path) -> Settings:
    return Settings(
        telegram_api_id=1,
        telegram_api_hash="h",
        telethon_session_name="s",
        telegram_download_bot_username="@b",
        telegram_desktop_download_folder=tmp_path / "tg",
        working_folder=tmp_path / "work",
        reports_folder=tmp_path / "reports",
        sqlite_db_path=tmp_path / "x.db",
        max_retries=5,
        retry_base_seconds=90,
        retry_max_seconds=900,
        download_wait_timeout_seconds=300,
        download_stable_seconds=10,
    )


def _gui(tmp_path: Path) -> sqlite3.Connection:
    path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(path)
    return connect(path)


def test_defaults_come_from_env_and_builtin_values(tmp_path: Path) -> None:
    run = load_run_settings(_gui(tmp_path), _env(tmp_path))

    assert run.max_retries == 5 and run.retry_base_seconds == 90
    assert run.total_timeout_seconds == 120 and run.stable_seconds == 10
    assert run.story_max_retries == 2 and run.media_not_found_max_retries == 3
    assert run.use_events is True and run.fallback_poll_ms == 1500
    assert run.parallel_downloads == 4 and run.watcher_fallback is False
    assert run.large_max_mb == 500 and run.availability_timeout_ms == 8000
    assert run.flood_sleep_threshold == 60
    assert run.telemetry_level == "FULL" and run.stories_first is True
    assert run.download_temp_folder is None
    assert run.between_urls_seconds == 2
    assert run.stall_enabled is True and run.stall_probe_delay_seconds == 10


def test_pause_and_stall_settings_are_validated_and_saved(tmp_path: Path) -> None:
    connection = _gui(tmp_path)
    env = _env(tmp_path)

    save_run_settings(
        connection,
        {
            "run.bot.between_urls_seconds": "5",
            "run.bot.stall_enabled": "0",
            "run.bot.stall_probe_delay_seconds": "20",
        },
        env,
    )
    run = load_run_settings(connection, env)

    assert (run.between_urls_seconds, run.stall_enabled, run.stall_probe_delay_seconds) == (
        5,
        False,
        20,
    )
    with pytest.raises(ValueError):
        validate_run_setting("run.bot.between_urls_seconds", "-1")
    with pytest.raises(ValueError):
        validate_run_setting("run.bot.stall_probe_delay_seconds", "0")


def test_gui_value_beats_env_and_apply_to_overrides_settings(tmp_path: Path) -> None:
    connection = _gui(tmp_path)
    env = _env(tmp_path)
    save_run_settings(
        connection,
        {
            "run.retry.max_retries": "2",
            "run.bot.parallel_downloads": "6",
            "run.download.temp_folder": str(tmp_path / "own"),
            "run.watcher.fallback_enabled": "1",
            "processing.stories_first": "0",
        },
    )

    run = load_run_settings(connection, env)
    effective = run.apply_to(env)

    assert run.stories_first is False
    assert effective.max_retries == 2 and effective.telegram_parallel_downloads == 6
    assert effective.telegram_watcher_fallback is True
    assert effective.telegram_download_target_folder == tmp_path / "own"
    assert effective.retry_base_seconds == 90  # untouched keys keep the .env value


def test_invalid_stored_value_is_ignored(tmp_path: Path) -> None:
    connection = _gui(tmp_path)
    connection.execute(
        "INSERT INTO app_settings (key, value, value_type, updated_at) "
        "VALUES ('run.retry.max_retries', 'many', 'INTEGER', datetime('now'))"
    )

    assert load_run_settings(connection, _env(tmp_path)).max_retries == 5


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("run.retry.max_retries", "-1"),
        ("run.retry.max_retries", "abc"),
        ("run.bot.parallel_downloads", "0"),
        ("run.bot.fallback_poll_ms", "100"),
        ("run.telemetry.level", "LOUD"),
        ("run.bot.use_events", "maybe"),
    ],
)
def test_invalid_values_are_rejected_and_never_saved(
    tmp_path: Path, key: str, text: str
) -> None:
    connection = _gui(tmp_path)
    with pytest.raises(ValueError):
        validate_run_setting(key, text)
    with pytest.raises(ValueError):
        save_run_settings(connection, {key: text})
    assert connection.execute(
        "SELECT COUNT(*) FROM app_settings WHERE key = ?", (key,)
    ).fetchone()[0] == 0


def test_reset_restores_env_values(tmp_path: Path) -> None:
    connection = _gui(tmp_path)
    save_run_settings(connection, {"run.retry.max_retries": "1"})
    reset_run_settings(connection)

    assert load_run_settings(connection, _env(tmp_path)).max_retries == 5


def test_v1_database_keeps_env_behaviour(tmp_path: Path) -> None:
    path = tmp_path / "orchestrator.db"
    init_database(path)

    run = load_run_settings(connect(path), _env(tmp_path))

    assert run.max_retries == 5 and run.use_events is True


def test_every_spec_has_unique_key_and_field() -> None:
    assert len({s.key for s in RUN_SETTING_SPECS}) == len(RUN_SETTING_SPECS)
    assert len({s.field for s in RUN_SETTING_SPECS}) == len(RUN_SETTING_SPECS)


def test_retry_caps_follow_configured_values() -> None:
    kwargs = dict(retries=3, max_retries=5, base_seconds=1, max_seconds=10, non_retryable=False)

    story = calculate_retry_decision(
        publication_type=PublicationType.STORY, story_max_retries=4, **kwargs
    )
    capped = calculate_retry_decision(
        publication_type=PublicationType.STORY, story_max_retries=3, **kwargs
    )
    not_found = calculate_retry_decision(
        last_error_type="MEDIA_NOT_FOUND_OR_UNAVAILABLE", media_not_found_max_retries=2, **kwargs
    )

    assert story.should_retry and capped.is_final_failure and not_found.is_final_failure


def test_saving_with_env_only_stores_values_that_differ(tmp_path: Path) -> None:
    connection = _gui(tmp_path)
    env = _env(tmp_path)
    values = {spec.key: spec.format(spec.default(env)) for spec in RUN_SETTING_SPECS}
    values["run.retry.max_retries"] = "2"

    save_run_settings(connection, values, env)

    stored = [
        row[0]
        for row in connection.execute(
            "SELECT key FROM app_settings WHERE key LIKE 'run.%' OR key = 'processing.stories_first'"
        )
    ]
    assert stored == ["run.retry.max_retries"]
    save_run_settings(connection, {"run.retry.max_retries": "5"}, env)
    assert connection.execute(
        "SELECT COUNT(*) FROM app_settings WHERE key = 'run.retry.max_retries'"
    ).fetchone()[0] == 0
