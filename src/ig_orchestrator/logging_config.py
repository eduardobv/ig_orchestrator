from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import Pattern
import logging
import re
from typing import Any, Iterator


LOGGER_NAME = "ig_orchestrator"
LOG_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | "
    "run=%(run_id)s account=%(account_username)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LEVEL = "INFO"
DEFAULT_ACCOUNT_LEVEL = "DEBUG"
REDACTED = "<redacted>"
_MISSING_EXTRA = "-"
_SENSITIVE_KEY_PARTS = (
    "api_hash",
    "api_id",
    "auth",
    "code",
    "env",
    "hash",
    "password",
    "phone",
    "secret",
    "session",
    "token",
)
_SENSITIVE_ASSIGNMENT_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(api_hash|api_id|password|secret|session|token|code|phone)\b"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
)
_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})
_logger = logging.getLogger(LOGGER_NAME)
_logger.setLevel(logging.DEBUG)
_logger.propagate = False
_app_handlers: dict[Path, logging.Handler] = {}


@dataclass(frozen=True, slots=True)
class AccountLogHandle:
    """Handle for a per-account run log handler."""

    path: Path
    handler: logging.Handler
    account_log_key: str

    def close(self) -> None:
        _logger.removeHandler(self.handler)
        self.handler.close()


class ProjectLogger:
    def debug(self, message: str, *args: Any) -> None:
        _logger.debug(_format_message(message, args))

    def info(self, message: str, *args: Any) -> None:
        _logger.info(_format_message(message, args))

    def warning(self, message: str, *args: Any) -> None:
        _logger.warning(_format_message(message, args))

    def error(self, message: str, *args: Any) -> None:
        _logger.error(_format_message(message, args))

    def exception(self, message: str, *args: Any) -> None:
        _logger.exception(_format_message(message, args))


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _log_context.get()
        record.run_id = _sanitize_value("run_id", context.get("run_id", _MISSING_EXTRA))
        record.account_username = _sanitize_value(
            "account_username",
            context.get("account_username", _MISSING_EXTRA),
        )
        record.account_log_key = context.get("account_log_key")
        return True


class _AccountLogFilter(_ContextFilter):
    def __init__(self, account_log_key: str) -> None:
        super().__init__()
        self.account_log_key = account_log_key

    def filter(self, record: logging.LogRecord) -> bool:
        super().filter(record)
        return record.account_log_key == self.account_log_key


class _AppLogFilter(_ContextFilter):
    def filter(self, record: logging.LogRecord) -> bool:
        super().filter(record)
        return record.levelno >= logging.WARNING or record.account_log_key is None


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = _sanitize_text(str(record.getMessage()))
        record.args = ()
        return super().format(record)


def configure_app_logging(
    logs_folder: Path | str = Path("logs"),
    *,
    level: str = DEFAULT_LEVEL,
    reset: bool = False,
) -> Path:
    """Configure the global application log and return its path."""

    folder = Path(logs_folder)
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / "app.log"
    resolved_path = log_path.resolve()

    if reset and resolved_path in _app_handlers:
        old_handler = _app_handlers.pop(resolved_path)
        _logger.removeHandler(old_handler)
        old_handler.close()

    if resolved_path not in _app_handlers:
        handler = _file_handler(log_path, level)
        handler.addFilter(_AppLogFilter())
        _logger.addHandler(handler)
        _app_handlers[resolved_path] = handler
    return log_path


def configure_account_run_logging(
    *,
    username: str,
    run_id: int,
    started_at: datetime,
    logs_folder: Path | str = Path("logs"),
    level: str = DEFAULT_ACCOUNT_LEVEL,
) -> AccountLogHandle:
    """Create a per-account run log under ``logs/YYYYMMDD_HHMMSS``."""

    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be blank")
    if run_id <= 0:
        raise ValueError("run_id must be positive")
    if not isinstance(started_at, datetime):
        raise ValueError("started_at must be a datetime")

    execution_folder = Path(logs_folder) / _execution_folder_name(started_at)
    execution_folder.mkdir(parents=True, exist_ok=True)
    log_path = execution_folder / f"{_safe_log_filename(normalized_username)}.log"
    account_log_key = f"{normalized_username}:{run_id}:{log_path.resolve()}"

    handler = _file_handler(log_path, level)
    handler.addFilter(_AccountLogFilter(account_log_key))
    _logger.addHandler(handler)
    return AccountLogHandle(
        path=log_path,
        handler=handler,
        account_log_key=account_log_key,
    )


@contextmanager
def logging_context(**extra: Any) -> Iterator[None]:
    """Bind contextual values to all logs emitted in the current async task."""

    current = dict(_log_context.get())
    current.update({key: _sanitize_value(key, value) for key, value in extra.items()})
    token = _log_context.set(current)
    try:
        yield
    finally:
        _log_context.reset(token)


def get_logger() -> ProjectLogger:
    """Return the project logger."""

    return ProjectLogger()


def _file_handler(path: Path, level: str) -> logging.FileHandler:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(_level(level))
    handler.setFormatter(_RedactingFormatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    return handler


def _level(level: str) -> int:
    numeric_level = logging.getLevelName(level.upper())
    if isinstance(numeric_level, int):
        return numeric_level
    raise ValueError(f"Invalid log level: {level}")


def _format_message(message: str, args: tuple[Any, ...]) -> str:
    if not args:
        return _sanitize_text(message)
    return _sanitize_text(message.format(*args))


def _sanitize_value(key: str, value: Any) -> Any:
    if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
        return REDACTED
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_text(text: str) -> str:
    sanitized = text
    for pattern in _SENSITIVE_ASSIGNMENT_PATTERNS:
        sanitized = pattern.sub(lambda match: f"{match.group(1)}={REDACTED}", sanitized)
    return sanitized


def _execution_folder_name(started_at: datetime) -> str:
    return started_at.strftime("%Y%m%d_%H%M%S")


def _safe_log_filename(username: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", username.strip())
    return safe_name or "unknown_username"


__all__ = [
    "AccountLogHandle",
    "REDACTED",
    "configure_account_run_logging",
    "configure_app_logging",
    "get_logger",
    "logging_context",
]
