from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from ig_orchestrator.logging_config import get_logger
from ig_orchestrator.settings import Settings

logger = get_logger()

KIND_BOOL = "bool"
KIND_INT = "int"
KIND_CHOICE = "choice"
KIND_PATH = "path"

GROUP_ORDER = "order"
GROUP_RETRY = "retry"
GROUP_BOT = "bot"
GROUP_WATCHER = "watcher"
GROUP_LARGE = "largefile"
GROUP_INSTAGRAM = "instagram"
GROUP_ACCOUNTCHECK = "accountcheck"
GROUP_TELETHON = "telethon"
GROUP_TELEMETRY = "telemetry"
GROUPS = (
    GROUP_ORDER,
    GROUP_RETRY,
    GROUP_BOT,
    GROUP_WATCHER,
    GROUP_LARGE,
    GROUP_INSTAGRAM,
    GROUP_ACCOUNTCHECK,
    GROUP_TELETHON,
    GROUP_TELEMETRY,
)


@dataclass(frozen=True, slots=True)
class RunSettingSpec:
    """One ``app_settings`` key editable in Settings > Ejecución."""

    key: str
    field: str
    kind: str
    group: str
    default: Callable[[Settings], object]
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()

    def parse(self, text: str) -> object:
        """Parse and validate a user/stored value; raises ValueError."""

        value = text.strip()
        if self.kind == KIND_BOOL:
            lowered = value.lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
            raise ValueError("must be 0/1")
        if self.kind == KIND_INT:
            try:
                number = int(value)
            except ValueError as exc:
                raise ValueError("must be an integer") from exc
            if self.minimum is not None and number < self.minimum:
                raise ValueError(f"must be at least {self.minimum}")
            if self.maximum is not None and number > self.maximum:
                raise ValueError(f"must be at most {self.maximum}")
            return number
        if self.kind == KIND_CHOICE:
            upper = value.upper()
            if upper not in self.choices:
                raise ValueError("must be one of " + ", ".join(self.choices))
            return upper
        if self.kind == KIND_PATH:
            return Path(value) if value else None
        raise ValueError(f"unknown kind {self.kind}")

    def format(self, value: object) -> str:
        if self.kind == KIND_BOOL:
            return "1" if value else "0"
        if value is None:
            return ""
        return str(value)


# Order is the order shown in the tab. ``default`` receives the .env Settings so
# precedence is GUI (app_settings) > .env > built-in default.
RUN_SETTING_SPECS: tuple[RunSettingSpec, ...] = (
    RunSettingSpec("processing.stories_first", "stories_first", KIND_BOOL, GROUP_ORDER,
                   lambda s: True),
    RunSettingSpec("run.retry.max_retries", "max_retries", KIND_INT, GROUP_RETRY,
                   lambda s: s.max_retries, 0, 20),
    RunSettingSpec("run.retry.story_max", "story_max_retries", KIND_INT, GROUP_RETRY,
                   lambda s: 2, 0, 20),
    RunSettingSpec("run.retry.media_not_found_max", "media_not_found_max_retries", KIND_INT,
                   GROUP_RETRY, lambda s: 3, 0, 20),
    RunSettingSpec("run.retry.no_response_max", "no_response_max_retries", KIND_INT, GROUP_RETRY,
                   lambda s: 3, 0, 20),
    RunSettingSpec("run.retry.global_queue", "global_retry_queue", KIND_BOOL, GROUP_RETRY,
                   lambda s: True),
    RunSettingSpec("run.retry.base_seconds", "retry_base_seconds", KIND_INT, GROUP_RETRY,
                   lambda s: s.retry_base_seconds, 1, 3600),
    RunSettingSpec("run.retry.max_seconds", "retry_max_seconds", KIND_INT, GROUP_RETRY,
                   lambda s: s.retry_max_seconds, 1, 7200),
    RunSettingSpec("run.bot.first_response_timeout_seconds", "first_response_seconds", KIND_INT,
                   GROUP_BOT, lambda s: 30, 5, 600),
    RunSettingSpec("run.bot.first_response_timeout_seconds_story", "first_response_story_seconds",
                   KIND_INT, GROUP_BOT, lambda s: 30, 5, 600),
    RunSettingSpec("run.bot.first_response_timeout_seconds_carousel",
                   "first_response_carousel_seconds", KIND_INT, GROUP_BOT, lambda s: 75, 5, 600),
    RunSettingSpec("run.bot.first_response_timeout_seconds_highlights",
                   "first_response_highlights_seconds", KIND_INT, GROUP_BOT, lambda s: 75, 5, 600),
    RunSettingSpec("run.bot.total_timeout_seconds", "total_timeout_seconds", KIND_INT, GROUP_BOT,
                   lambda s: 120, 10, 3600),
    RunSettingSpec("run.bot.completion_mode", "completion_mode", KIND_CHOICE, GROUP_BOT,
                   lambda s: "EXPECTED_COUNT", choices=("EXPECTED_COUNT", "STABLE")),
    RunSettingSpec("run.bot.grace_ms", "grace_ms", KIND_INT, GROUP_BOT,
                   lambda s: 2500, 200, 30000),
    RunSettingSpec("run.bot.story_attachment_wait_seconds", "story_attachment_wait_seconds",
                   KIND_INT, GROUP_BOT, lambda s: 20, 2, 300),
    RunSettingSpec("run.bot.stable_seconds", "stable_seconds", KIND_INT, GROUP_BOT,
                   lambda s: s.download_stable_seconds, 0, 120),
    RunSettingSpec("run.bot.between_urls_seconds", "between_urls_seconds", KIND_INT, GROUP_BOT,
                   lambda s: 2, 0, 600),
    RunSettingSpec("run.bot.stall_enabled", "stall_enabled", KIND_BOOL, GROUP_BOT,
                   lambda s: True),
    RunSettingSpec("run.bot.stall_probe_delay_seconds", "stall_probe_delay_seconds", KIND_INT,
                   GROUP_BOT, lambda s: 10, 1, 600),
    RunSettingSpec("run.bot.use_events", "use_events", KIND_BOOL, GROUP_BOT, lambda s: True),
    RunSettingSpec("run.bot.fallback_poll_ms", "fallback_poll_ms", KIND_INT, GROUP_BOT,
                   lambda s: 1500, 500, 30000),
    RunSettingSpec("run.bot.parallel_downloads", "parallel_downloads", KIND_INT, GROUP_BOT,
                   lambda s: s.telegram_parallel_downloads, 1, 16),
    RunSettingSpec("run.download.temp_folder", "download_temp_folder", KIND_PATH, GROUP_BOT,
                   lambda s: s.telegram_download_temp_folder),
    RunSettingSpec("run.watcher.fallback_enabled", "watcher_fallback", KIND_BOOL, GROUP_WATCHER,
                   lambda s: s.telegram_watcher_fallback),
    RunSettingSpec("run.largefile.enabled", "large_enabled", KIND_BOOL, GROUP_LARGE,
                   lambda s: True),
    RunSettingSpec("run.largefile.connect_timeout_s", "large_connect_timeout_s", KIND_INT,
                   GROUP_LARGE, lambda s: 10, 1, 300),
    RunSettingSpec("run.largefile.read_timeout_s", "large_read_timeout_s", KIND_INT,
                   GROUP_LARGE, lambda s: 120, 1, 3600),
    RunSettingSpec("run.largefile.max_mb", "large_max_mb", KIND_INT, GROUP_LARGE,
                   lambda s: 500, 1, 10000),
    RunSettingSpec("run.availability.enabled", "availability_enabled", KIND_BOOL,
                   GROUP_INSTAGRAM, lambda s: True),
    RunSettingSpec("run.availability.min_interval_ms", "availability_min_interval_ms", KIND_INT,
                   GROUP_INSTAGRAM, lambda s: 2000, 0, 60000),
    RunSettingSpec("run.availability.timeout_ms", "availability_timeout_ms", KIND_INT,
                   GROUP_INSTAGRAM, lambda s: 8000, 1000, 60000),
    RunSettingSpec("run.accountcheck.interval_seconds", "accountcheck_interval_seconds", KIND_INT,
                   GROUP_ACCOUNTCHECK, lambda s: 30, 5, 3600),
    RunSettingSpec("run.accountcheck.timeout_seconds", "accountcheck_timeout_seconds", KIND_INT,
                   GROUP_ACCOUNTCHECK, lambda s: 15, 3, 120),
    RunSettingSpec("run.telethon.flood_sleep_threshold", "flood_sleep_threshold", KIND_INT,
                   GROUP_TELETHON, lambda s: s.telegram_flood_sleep_threshold, 0, 3600),
    RunSettingSpec("run.telemetry.level", "telemetry_level", KIND_CHOICE, GROUP_TELEMETRY,
                   lambda s: s.telemetry_level, choices=("OFF", "ATTEMPTS", "FULL")),
    RunSettingSpec("run.telemetry.retention_days", "telemetry_retention_days", KIND_INT,
                   GROUP_TELEMETRY, lambda s: s.telemetry_retention_days, 1, 3650),
)

SPECS_BY_KEY = {spec.key: spec for spec in RUN_SETTING_SPECS}


@dataclass(frozen=True, slots=True)
class RunSettings:
    """Effective run configuration (GUI > .env > default)."""

    stories_first: bool
    max_retries: int
    story_max_retries: int
    media_not_found_max_retries: int
    no_response_max_retries: int
    global_retry_queue: bool
    retry_base_seconds: int
    retry_max_seconds: int
    first_response_seconds: int
    first_response_story_seconds: int
    first_response_carousel_seconds: int
    first_response_highlights_seconds: int
    total_timeout_seconds: int
    completion_mode: str
    grace_ms: int
    story_attachment_wait_seconds: int
    between_urls_seconds: int
    stall_enabled: bool
    stall_probe_delay_seconds: int
    stable_seconds: int
    use_events: bool
    fallback_poll_ms: int
    parallel_downloads: int
    download_temp_folder: Path | None
    watcher_fallback: bool
    large_enabled: bool
    large_connect_timeout_s: int
    large_read_timeout_s: int
    large_max_mb: int
    availability_enabled: bool
    availability_min_interval_ms: int
    availability_timeout_ms: int
    accountcheck_interval_seconds: int
    accountcheck_timeout_seconds: int
    flood_sleep_threshold: int
    telemetry_level: str
    telemetry_retention_days: int

    def apply_to(self, settings: Settings) -> Settings:
        """Return .env settings overridden by the run settings they replace."""

        return dataclasses.replace(
            settings,
            max_retries=self.max_retries,
            retry_base_seconds=self.retry_base_seconds,
            retry_max_seconds=self.retry_max_seconds,
            download_wait_timeout_seconds=self.total_timeout_seconds,
            download_stable_seconds=self.stable_seconds,
            telegram_parallel_downloads=self.parallel_downloads,
            telegram_download_temp_folder=self.download_temp_folder,
            telegram_watcher_fallback=self.watcher_fallback,
            telegram_flood_sleep_threshold=self.flood_sleep_threshold,
            telemetry_level=self.telemetry_level,
            telemetry_retention_days=self.telemetry_retention_days,
        )


def load_run_settings(connection: Connection, settings: Settings) -> RunSettings:
    """Resolve every key: stored GUI value, else .env, else built-in default."""

    stored = _read_stored(connection)
    values: dict[str, object] = {}
    for spec in RUN_SETTING_SPECS:
        value = spec.default(settings)
        text = stored.get(spec.key)
        if text is not None and (text.strip() or spec.kind == KIND_PATH):
            try:
                value = spec.parse(text)
            except ValueError as exc:
                logger.warning(
                    "Invalid run setting ignored: key={} value={} error={}",
                    spec.key,
                    text,
                    exc,
                )
        values[spec.field] = value
    return RunSettings(**values)  # type: ignore[arg-type]


def validate_run_setting(key: str, text: str) -> object:
    """Validate a value typed in the GUI; raises ValueError with the reason."""

    return SPECS_BY_KEY[key].parse(text)


def save_run_settings(
    connection: Connection,
    values: dict[str, str],
    env_settings: Settings | None = None,
) -> None:
    """Persist validated texts into ``app_settings`` (GUI database).

    With ``env_settings``, a value equal to what .env / the built-in default
    already gives is not stored (and any old override is removed), so later
    .env edits keep applying to settings the user never changed.
    """

    for key, text in values.items():
        spec = SPECS_BY_KEY[key]
        parsed = spec.parse(text)  # never store an invalid value
        if env_settings is not None and parsed == spec.default(env_settings):
            connection.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            continue
        value_type = {
            KIND_BOOL: "BOOLEAN",
            KIND_INT: "INTEGER",
            KIND_PATH: "PATH",
        }.get(spec.kind, "TEXT")
        connection.execute(
            """
            INSERT INTO app_settings (key, value, value_type, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (key, text.strip(), value_type),
        )
    connection.commit()


def reset_run_settings(connection: Connection) -> None:
    """Drop every stored override so .env / defaults apply again."""

    placeholders = ",".join("?" for _ in RUN_SETTING_SPECS)
    connection.execute(
        f"DELETE FROM app_settings WHERE key IN ({placeholders})",
        [spec.key for spec in RUN_SETTING_SPECS],
    )
    connection.commit()


def stored_run_setting_texts(connection: Connection) -> dict[str, str]:
    return _read_stored(connection)


def _read_stored(connection: Connection) -> dict[str, str]:
    from ig_orchestrator.db.schema_mode import is_gui_schema

    if not is_gui_schema(connection):
        return {}  # the v1 rollback database keeps .env behaviour
    try:
        rows = connection.execute(
            "SELECT key, value FROM app_settings WHERE key = 'processing.stories_first' "
            "OR key LIKE 'run.%'"
        ).fetchall()
    except Exception:
        return {}
    return {str(row["key"]): str(row["value"]) for row in rows}


__all__ = [
    "GROUPS",
    "RUN_SETTING_SPECS",
    "RunSettingSpec",
    "RunSettings",
    "load_run_settings",
    "reset_run_settings",
    "save_run_settings",
    "stored_run_setting_texts",
    "validate_run_setting",
]
