from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BotResponseStatus(StrEnum):
    OK = "OK"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    NON_RETRYABLE_ERROR = "NON_RETRYABLE_ERROR"
    UNKNOWN = "UNKNOWN"


class BotErrorType(StrEnum):
    SERVICE_OVERLOADED = "SERVICE_OVERLOADED"
    GEOBLOCK_REQUIRED = "GEOBLOCK_REQUIRED"
    MEDIA_NOT_FOUND_OR_UNAVAILABLE = "MEDIA_NOT_FOUND_OR_UNAVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    STORIES_NOT_FOUND = "STORIES_NOT_FOUND"
    PRIVATE_ACCOUNT_STORIES = "PRIVATE_ACCOUNT_STORIES"


@dataclass(frozen=True, slots=True)
class BotResponse:
    status: BotResponseStatus
    original_message: str | None
    last_error: str | None = None
    last_error_type: BotErrorType | None = None


_RETRYABLE_ERRORS: tuple[tuple[str, BotErrorType], ...] = (
    (
        "The service is overloaded, please try again later.",
        BotErrorType.SERVICE_OVERLOADED,
    ),
    ("geoblock_required", BotErrorType.GEOBLOCK_REQUIRED),
    (
        "Media not found or unavailable",
        BotErrorType.MEDIA_NOT_FOUND_OR_UNAVAILABLE,
    ),
)

_NON_RETRYABLE_ERRORS: tuple[tuple[str, BotErrorType], ...] = (
    ("We're sorry, we couldn't find that.", BotErrorType.NOT_FOUND),
    ("Stories for user_name not found", BotErrorType.STORIES_NOT_FOUND),
    (
        "We can't get stories from a private account (instagram limit)",
        BotErrorType.PRIVATE_ACCOUNT_STORIES,
    ),
)


def parse_bot_response(message: str | None) -> BotResponse:
    """Classify a Telegram bot text response without mutating the message."""

    if message is None or not message.strip():
        return BotResponse(
            status=BotResponseStatus.UNKNOWN,
            original_message=message,
        )

    normalized_message = message.casefold()

    retryable_error_type = _find_error_type(normalized_message, _RETRYABLE_ERRORS)
    if retryable_error_type is not None:
        return BotResponse(
            status=BotResponseStatus.RETRYABLE_ERROR,
            original_message=message,
            last_error=message,
            last_error_type=retryable_error_type,
        )

    non_retryable_error_type = _find_error_type(
        normalized_message,
        _NON_RETRYABLE_ERRORS,
    )
    if non_retryable_error_type is not None:
        return BotResponse(
            status=BotResponseStatus.NON_RETRYABLE_ERROR,
            original_message=message,
            last_error=message,
            last_error_type=non_retryable_error_type,
        )

    return BotResponse(
        status=BotResponseStatus.OK,
        original_message=message,
    )


def _find_error_type(
    normalized_message: str,
    known_errors: tuple[tuple[str, BotErrorType], ...],
) -> BotErrorType | None:
    for error_text, error_type in known_errors:
        if error_text.casefold() in normalized_message:
            return error_type
    return None


__all__ = [
    "BotErrorType",
    "BotResponse",
    "BotResponseStatus",
    "parse_bot_response",
]
