from pathlib import Path

import pytest

from ig_orchestrator.settings import SettingsError, load_settings


ENV_NAMES = (
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELETHON_SESSION_NAME",
    "TELEGRAM_DOWNLOAD_BOT_USERNAME",
    "TELEGRAM_DESKTOP_DOWNLOAD_FOLDER",
    "WORKING_FOLDER",
    "REPORTS_FOLDER",
    "SQLITE_DB_PATH",
    "MAX_RETRIES",
    "RETRY_BASE_SECONDS",
    "RETRY_MAX_SECONDS",
    "DOWNLOAD_WAIT_TIMEOUT_SECONDS",
    "DOWNLOAD_STABLE_SECONDS",
    "FINAL_BASE_FOLDER",
    "MANUAL_RENAME_BAT_PATH",
    "MANUAL_RENAME_CONFIG_PATH",
)


def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)


def write_env_file(path: Path, *, include_api_hash: bool = True) -> None:
    lines = [
        "TELEGRAM_API_ID=12345",
        "TELETHON_SESSION_NAME=telegram_user_session",
        "TELEGRAM_DOWNLOAD_BOT_USERNAME=@example_bot",
        r"TELEGRAM_DESKTOP_DOWNLOAD_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop",
        r"WORKING_FOLDER=C:\Users\eduba\Downloads\DW\Telegram_Desktop",
        "REPORTS_FOLDER=reports",
        r"SQLITE_DB_PATH=data\orchestrator.db",
        "MAX_RETRIES=5",
        "RETRY_BASE_SECONDS=90",
        "RETRY_MAX_SECONDS=900",
        "DOWNLOAD_WAIT_TIMEOUT_SECONDS=300",
        "DOWNLOAD_STABLE_SECONDS=10",
        r"FINAL_BASE_FOLDER=G:\4K Stogram\00.FAVORITES",
        r"MANUAL_RENAME_BAT_PATH=C:\path\to\ManualRenameFiles.bat",
        r"MANUAL_RENAME_CONFIG_PATH=C:\path\to\config.json",
    ]
    if include_api_hash:
        lines.insert(1, "TELEGRAM_API_HASH=secret_hash")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_load_settings_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_environment(monkeypatch)
    env_file = tmp_path / ".env"
    write_env_file(env_file)

    settings = load_settings(env_file)

    assert settings.telegram_api_id == 12345
    assert settings.telegram_api_hash == "secret_hash"
    assert settings.telethon_session_name == "telegram_user_session"
    assert settings.telegram_download_bot_username == "@example_bot"
    assert settings.telegram_desktop_download_folder == Path(
        r"C:\Users\eduba\Downloads\DW\Telegram_Desktop"
    )
    assert settings.working_folder == Path(
        r"C:\Users\eduba\Downloads\DW\Telegram_Desktop"
    )
    assert settings.reports_folder == Path("reports")
    assert settings.sqlite_db_path == Path(r"data\orchestrator.db")
    assert settings.max_retries == 5
    assert settings.retry_base_seconds == 90
    assert settings.retry_max_seconds == 900
    assert settings.download_wait_timeout_seconds == 300
    assert settings.download_stable_seconds == 10
    assert settings.final_base_folder == Path(r"G:\4K Stogram\00.FAVORITES")
    assert settings.manual_rename_bat_path == Path(r"C:\path\to\ManualRenameFiles.bat")
    assert settings.manual_rename_config_path == Path(r"C:\path\to\config.json")


def test_missing_required_variable_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_settings_environment(monkeypatch)
    env_file = tmp_path / ".env"
    write_env_file(env_file, include_api_hash=False)

    with pytest.raises(SettingsError) as exc_info:
        load_settings(env_file)

    message = str(exc_info.value)
    assert "Missing required environment variables" in message
    assert "TELEGRAM_API_HASH" in message
    assert "secret_hash" not in message


def test_reserved_future_variables_are_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_settings_environment(monkeypatch)
    env_file = tmp_path / ".env"
    write_env_file(env_file)
    content = env_file.read_text(encoding="utf-8")
    for env_name in (
        "FINAL_BASE_FOLDER",
        "MANUAL_RENAME_BAT_PATH",
        "MANUAL_RENAME_CONFIG_PATH",
    ):
        content = "\n".join(
            line for line in content.splitlines() if not line.startswith(env_name)
        )
    env_file.write_text(content, encoding="utf-8")

    settings = load_settings(env_file)

    assert settings.final_base_folder is None
    assert settings.manual_rename_bat_path is None
    assert settings.manual_rename_config_path is None
