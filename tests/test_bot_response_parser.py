from __future__ import annotations

import pytest

from ig_orchestrator.telegram import (
    BotErrorType,
    BotResponseStatus,
    parse_bot_response,
)


@pytest.mark.parametrize(
    ("text", "expected_error_type"),
    [
        (
            "The service is overloaded, please try again later.",
            BotErrorType.SERVICE_OVERLOADED,
        ),
        ("geoblock_required", BotErrorType.GEOBLOCK_REQUIRED),
        (
            "Media not found or unavailable",
            BotErrorType.MEDIA_NOT_FOUND_OR_UNAVAILABLE,
        ),
    ],
)
def test_detects_retryable_errors_case_insensitively(
    text: str,
    expected_error_type: BotErrorType,
) -> None:
    original_message = f"  {text.upper()}  "

    response = parse_bot_response(original_message)

    assert response.status == BotResponseStatus.RETRYABLE_ERROR
    assert response.last_error == original_message
    assert response.last_error_type == expected_error_type


@pytest.mark.parametrize(
    ("text", "expected_error_type"),
    [
        (
            "We're sorry, we couldn't find that.",
            BotErrorType.NOT_FOUND,
        ),
        (
            "Stories for superlisha not found",
            BotErrorType.STORIES_NOT_FOUND,
        ),
        (
            "We can't get stories from a private account (instagram limit)",
            BotErrorType.PRIVATE_ACCOUNT_STORIES,
        ),
    ],
)
def test_detects_non_retryable_errors_case_insensitively(
    text: str,
    expected_error_type: BotErrorType,
) -> None:
    original_message = f"Bot says: {text.swapcase()}"

    response = parse_bot_response(original_message)

    assert response.status == BotResponseStatus.NON_RETRYABLE_ERROR
    assert response.last_error == original_message
    assert response.last_error_type == expected_error_type


@pytest.mark.parametrize(
    "text",
    [
        "Stories for superlisha not found",
        "Stories for iarabroinn not found",
        "STORIES FOR user.with-dots NOT FOUND",
    ],
)
def test_detects_dynamic_story_username_as_non_retryable(text: str) -> None:
    response = parse_bot_response(text)

    assert response.status == BotResponseStatus.NON_RETRYABLE_ERROR
    assert response.last_error_type == BotErrorType.STORIES_NOT_FOUND


def test_non_error_text_is_ok() -> None:
    response = parse_bot_response("Download completed successfully")

    assert response.status == BotResponseStatus.OK
    assert response.last_error is None
    assert response.last_error_type is None


@pytest.mark.parametrize("text", [None, "", "   "])
def test_blank_response_is_unknown(text: str | None) -> None:
    response = parse_bot_response(text)

    assert response.status == BotResponseStatus.UNKNOWN
    assert response.last_error is None
    assert response.last_error_type is None
