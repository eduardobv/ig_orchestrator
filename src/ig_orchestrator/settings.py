from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


class SettingsError(RuntimeError):
    """Raised when application settings cannot be loaded."""


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    telegram_api_id: int
    telegram_api_hash: str = field(repr=False)
    telethon_session_name: str
    telegram_download_bot_username: str
    telegram_desktop_download_folder: Path
    working_folder: Path
    reports_folder: Path
    sqlite_db_path: Path
    max_retries: int
    retry_base_seconds: int
    retry_max_seconds: int
    download_wait_timeout_seconds: int
    download_stable_seconds: int
    post_process_enabled: bool = False
    post_process_command: Path | None = None
    final_base_folder: Path | None = None
    manual_rename_bat_path: Path | None = None
    manual_rename_config_path: Path | None = None
    sqlite_gui_db_path: Path = field(
        default_factory=lambda: Path(r"data\orchestrator_gui.sqlite")
    )
    window_position: str = "left"
    telegram_download_temp_folder: Path | None = None
    telegram_parallel_downloads: int = 4
    telegram_watcher_fallback: bool = False
    telemetry_level: str = "FULL"
    telemetry_retention_days: int = 90
    # Set from Settings > Ejecución (run.telethon.flood_sleep_threshold), not .env.
    telegram_flood_sleep_threshold: int = 60

    @property
    def telegram_download_target_folder(self) -> Path:
        """Folder where bot media is downloaded (own folder if configured)."""

        return self.telegram_download_temp_folder or self.telegram_desktop_download_folder


_ENV_TO_FIELD = {
    "TELEGRAM_API_ID": "telegram_api_id",
    "TELEGRAM_API_HASH": "telegram_api_hash",
    "TELETHON_SESSION_NAME": "telethon_session_name",
    "TELEGRAM_DOWNLOAD_BOT_USERNAME": "telegram_download_bot_username",
    "TELEGRAM_DESKTOP_DOWNLOAD_FOLDER": "telegram_desktop_download_folder",
    "WORKING_FOLDER": "working_folder",
    "REPORTS_FOLDER": "reports_folder",
    "SQLITE_DB_PATH": "sqlite_db_path",
    "SQLITE_GUI_DB_PATH": "sqlite_gui_db_path",
    "MAX_RETRIES": "max_retries",
    "RETRY_BASE_SECONDS": "retry_base_seconds",
    "RETRY_MAX_SECONDS": "retry_max_seconds",
    "DOWNLOAD_WAIT_TIMEOUT_SECONDS": "download_wait_timeout_seconds",
    "DOWNLOAD_STABLE_SECONDS": "download_stable_seconds",
    "POST_PROCESS_ENABLED": "post_process_enabled",
    "POST_PROCESS_COMMAND": "post_process_command",
    "FINAL_BASE_FOLDER": "final_base_folder",
    "MANUAL_RENAME_BAT_PATH": "manual_rename_bat_path",
    "MANUAL_RENAME_CONFIG_PATH": "manual_rename_config_path",
    "WINDOW_POSITION": "window_position",
    "TELEGRAM_DOWNLOAD_TEMP_FOLDER": "telegram_download_temp_folder",
    "TELEGRAM_PARALLEL_DOWNLOADS": "telegram_parallel_downloads",
    "TELEGRAM_WATCHER_FALLBACK": "telegram_watcher_fallback",
    "TELEMETRY_LEVEL": "telemetry_level",
    "TELEMETRY_RETENTION_DAYS": "telemetry_retention_days",
}

_REQUIRED_ENV_VARS = tuple(
    env_name
    for env_name in _ENV_TO_FIELD
    if env_name
    not in {
        "FINAL_BASE_FOLDER",
        "POST_PROCESS_ENABLED",
        "POST_PROCESS_COMMAND",
        "MANUAL_RENAME_BAT_PATH",
        "MANUAL_RENAME_CONFIG_PATH",
        "SQLITE_GUI_DB_PATH",
        "WINDOW_POSITION",
        "TELEGRAM_DOWNLOAD_TEMP_FOLDER",
        "TELEGRAM_PARALLEL_DOWNLOADS",
        "TELEGRAM_WATCHER_FALLBACK",
        "TELEMETRY_LEVEL",
        "TELEMETRY_RETENTION_DAYS",
    }
)


def load_settings(env_file: str | Path = ".env") -> Settings:
    """Load settings from a dotenv file and process environment variables."""

    env_path = Path(env_file)
    raw_values = {
        key: value
        for key, value in dotenv_values(env_path).items()
        if value is not None
    }

    for env_name in _ENV_TO_FIELD:
        if env_name in os.environ:
            raw_values[env_name] = os.environ[env_name]

    missing = [
        env_name
        for env_name in _REQUIRED_ENV_VARS
        if not raw_values.get(env_name, "").strip()
    ]
    if missing:
        raise SettingsError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    try:
        return Settings(
            telegram_api_id=_parse_int(raw_values, "TELEGRAM_API_ID"),
            telegram_api_hash=_parse_text(raw_values, "TELEGRAM_API_HASH"),
            telethon_session_name=_parse_text(raw_values, "TELETHON_SESSION_NAME"),
            telegram_download_bot_username=_parse_text(
                raw_values, "TELEGRAM_DOWNLOAD_BOT_USERNAME"
            ),
            telegram_desktop_download_folder=_parse_path(
                raw_values, "TELEGRAM_DESKTOP_DOWNLOAD_FOLDER"
            ),
            working_folder=_parse_path(raw_values, "WORKING_FOLDER"),
            reports_folder=_parse_path(raw_values, "REPORTS_FOLDER"),
            sqlite_db_path=_parse_path(raw_values, "SQLITE_DB_PATH"),
            sqlite_gui_db_path=_parse_optional_path(
                raw_values, "SQLITE_GUI_DB_PATH"
            )
            or Path(r"data\orchestrator_gui.sqlite"),
            max_retries=_parse_int(raw_values, "MAX_RETRIES"),
            retry_base_seconds=_parse_int(raw_values, "RETRY_BASE_SECONDS"),
            retry_max_seconds=_parse_int(raw_values, "RETRY_MAX_SECONDS"),
            download_wait_timeout_seconds=_parse_int(
                raw_values, "DOWNLOAD_WAIT_TIMEOUT_SECONDS"
            ),
            download_stable_seconds=_parse_int(raw_values, "DOWNLOAD_STABLE_SECONDS"),
            post_process_enabled=_parse_optional_bool(
                raw_values, "POST_PROCESS_ENABLED", default=False
            ),
            post_process_command=_parse_optional_path(
                raw_values, "POST_PROCESS_COMMAND"
            ),
            final_base_folder=_parse_optional_path(raw_values, "FINAL_BASE_FOLDER"),
            manual_rename_bat_path=_parse_optional_path(
                raw_values, "MANUAL_RENAME_BAT_PATH"
            ),
            manual_rename_config_path=_parse_optional_path(
                raw_values, "MANUAL_RENAME_CONFIG_PATH"
            ),
            window_position=_parse_optional_window_position(
                raw_values, "WINDOW_POSITION", default="left"
            ),
            telegram_download_temp_folder=_parse_optional_path(
                raw_values, "TELEGRAM_DOWNLOAD_TEMP_FOLDER"
            ),
            telegram_parallel_downloads=_parse_optional_positive_int(
                raw_values, "TELEGRAM_PARALLEL_DOWNLOADS", default=4
            ),
            telegram_watcher_fallback=_parse_optional_bool(
                raw_values, "TELEGRAM_WATCHER_FALLBACK", default=False
            ),
            telemetry_level=_parse_telemetry_level(raw_values),
            telemetry_retention_days=_parse_optional_positive_int(
                raw_values, "TELEMETRY_RETENTION_DAYS", default=90
            ),
        )
    except ValueError as exc:
        raise SettingsError(f"Invalid environment settings: {exc}") from exc


def _parse_text(raw_values: dict[str, str], env_name: str) -> str:
    value = raw_values[env_name].strip()
    if not value:
        raise ValueError(f"{env_name} must not be blank")
    return value


def _parse_int(raw_values: dict[str, str], env_name: str) -> int:
    value = _parse_text(raw_values, env_name)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer") from exc


def _parse_path(raw_values: dict[str, str], env_name: str) -> Path:
    return Path(_parse_text(raw_values, env_name))


def _parse_optional_path(raw_values: dict[str, str], env_name: str) -> Path | None:
    value = raw_values.get(env_name)
    if value is None or not value.strip():
        return None
    return Path(value)


def _parse_optional_bool(
    raw_values: dict[str, str],
    env_name: str,
    *,
    default: bool,
) -> bool:
    value = raw_values.get(env_name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{env_name} must be a boolean")


def _parse_telemetry_level(raw_values: dict[str, str]) -> str:
    value = raw_values.get("TELEMETRY_LEVEL")
    if value is None or not value.strip():
        return "FULL"
    normalized = value.strip().upper()
    if normalized not in {"OFF", "ATTEMPTS", "FULL"}:
        raise ValueError("TELEMETRY_LEVEL must be OFF, ATTEMPTS or FULL")
    return normalized


def _parse_optional_positive_int(
    raw_values: dict[str, str],
    env_name: str,
    *,
    default: int,
) -> int:
    value = raw_values.get(env_name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{env_name} must be at least 1")
    return parsed


def _parse_optional_window_position(
    raw_values: dict[str, str],
    env_name: str,
    *,
    default: str,
) -> str:
    value = raw_values.get(env_name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized not in {"left", "center", "right"}:
        raise ValueError(f"{env_name} must be 'left', 'center', or 'right'")
    return normalized


__all__ = ["Settings", "SettingsError", "load_settings"]
