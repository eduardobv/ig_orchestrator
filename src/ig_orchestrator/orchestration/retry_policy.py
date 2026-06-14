from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Deque, Generic, Iterable, TypeVar

from ig_orchestrator.models import UrlJobStatus


class RetryDecisionAction(StrEnum):
    RETRY = "RETRY"
    FAILED_FINAL = "FAILED_FINAL"
    DO_NOT_RETRY = "DO_NOT_RETRY"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    action: RetryDecisionAction
    status: UrlJobStatus | None
    delay_seconds: int | None = None
    reason: str | None = None

    @property
    def should_retry(self) -> bool:
        return self.action == RetryDecisionAction.RETRY

    @property
    def is_final_failure(self) -> bool:
        return self.action == RetryDecisionAction.FAILED_FINAL


T = TypeVar("T")


class RetryQueue(Generic[T]):
    """Small FIFO queue for retry rounds; it never sleeps or schedules time."""

    def __init__(self, items: Iterable[T] | None = None) -> None:
        self._items: Deque[T] = deque(items or ())

    def enqueue(self, item: T) -> None:
        self._items.append(item)

    def requeue(self, item: T) -> None:
        self.enqueue(item)

    def pop_next(self) -> T | None:
        if not self._items:
            return None
        return self._items.popleft()

    def __bool__(self) -> bool:
        return bool(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def snapshot(self) -> tuple[T, ...]:
        return tuple(self._items)


def calculate_retry_decision(
    *,
    retries: int,
    max_retries: int,
    base_seconds: int,
    max_seconds: int,
    non_retryable: bool,
) -> RetryDecision:
    """Calculate retry backoff and final-failure decisions without sleeping."""

    _validate_non_negative("retries", retries)
    _validate_non_negative("max_retries", max_retries)
    _validate_positive("base_seconds", base_seconds)
    _validate_positive("max_seconds", max_seconds)

    if non_retryable:
        return RetryDecision(
            action=RetryDecisionAction.FAILED_FINAL,
            status=UrlJobStatus.FAILED_FINAL,
            reason="non_retryable",
        )

    if retries >= max_retries:
        return RetryDecision(
            action=RetryDecisionAction.FAILED_FINAL,
            status=UrlJobStatus.FAILED_FINAL,
            reason="max_retries_reached",
        )

    delay_seconds = min(base_seconds * (2**retries), max_seconds)
    return RetryDecision(
        action=RetryDecisionAction.RETRY,
        status=UrlJobStatus.RETRY_PENDING,
        delay_seconds=delay_seconds,
        reason="retry_pending",
    )


def _validate_non_negative(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must not be negative")


def _validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


__all__ = [
    "RetryDecision",
    "RetryDecisionAction",
    "RetryQueue",
    "calculate_retry_decision",
]
