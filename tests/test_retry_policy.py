import pytest

from ig_orchestrator.models import UrlJobStatus
from ig_orchestrator.orchestration import (
    RetryDecisionAction,
    RetryQueue,
    calculate_retry_decision,
)


@pytest.mark.parametrize(
    ("retries", "expected_delay"),
    [
        (0, 90),
        (1, 180),
        (2, 360),
        (3, 720),
        (4, 900),
    ],
)
def test_retry_backoff_is_exponential_and_capped(
    retries: int,
    expected_delay: int,
) -> None:
    decision = calculate_retry_decision(
        retries=retries,
        max_retries=5,
        base_seconds=90,
        max_seconds=900,
        non_retryable=False,
    )

    assert decision.action == RetryDecisionAction.RETRY
    assert decision.status == UrlJobStatus.RETRY_PENDING
    assert decision.delay_seconds == expected_delay
    assert decision.should_retry is True


def test_non_retryable_error_becomes_final_failure_without_delay() -> None:
    decision = calculate_retry_decision(
        retries=0,
        max_retries=5,
        base_seconds=90,
        max_seconds=900,
        non_retryable=True,
    )

    assert decision.action == RetryDecisionAction.FAILED_FINAL
    assert decision.status == UrlJobStatus.FAILED_FINAL
    assert decision.delay_seconds is None
    assert decision.is_final_failure is True
    assert decision.reason == "non_retryable"


def test_max_retries_becomes_final_failure() -> None:
    decision = calculate_retry_decision(
        retries=5,
        max_retries=5,
        base_seconds=90,
        max_seconds=900,
        non_retryable=False,
    )

    assert decision.action == RetryDecisionAction.FAILED_FINAL
    assert decision.status == UrlJobStatus.FAILED_FINAL
    assert decision.delay_seconds is None
    assert decision.reason == "max_retries_reached"


def test_zero_max_retries_becomes_final_failure() -> None:
    decision = calculate_retry_decision(
        retries=0,
        max_retries=0,
        base_seconds=90,
        max_seconds=900,
        non_retryable=False,
    )

    assert decision.action == RetryDecisionAction.FAILED_FINAL
    assert decision.status == UrlJobStatus.FAILED_FINAL
    assert decision.delay_seconds is None
    assert decision.should_retry is False


def test_retry_queue_preserves_fifo_order_and_requeues_at_the_end() -> None:
    queue = RetryQueue[int]([2, 6])

    assert queue.pop_next() == 2

    queue.requeue(2)

    assert queue.snapshot() == (6, 2)
    assert queue.pop_next() == 6
    assert queue.pop_next() == 2
    assert queue.pop_next() is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "retries": -1,
            "max_retries": 5,
            "base_seconds": 90,
            "max_seconds": 900,
            "non_retryable": False,
        },
        {
            "retries": 0,
            "max_retries": -1,
            "base_seconds": 90,
            "max_seconds": 900,
            "non_retryable": False,
        },
        {
            "retries": 0,
            "max_retries": 5,
            "base_seconds": 0,
            "max_seconds": 900,
            "non_retryable": False,
        },
        {
            "retries": 0,
            "max_retries": 5,
            "base_seconds": 90,
            "max_seconds": 0,
            "non_retryable": False,
        },
    ],
)
def test_retry_policy_rejects_invalid_numbers(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        calculate_retry_decision(**kwargs)  # type: ignore[arg-type]
