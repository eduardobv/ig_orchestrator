"""Pure timing rules: night window and the pause between HTTP requests."""

from __future__ import annotations

import random
from datetime import datetime, time


def in_night_window(now: datetime, start: time, end: time) -> bool:
    """True when ``now`` (local time) is inside [start, end); crosses midnight."""

    current = now.time().replace(tzinfo=None)
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def base_interval(
    now: datetime,
    *,
    interval_seconds: float,
    night_enabled: bool,
    night_start: time,
    night_end: time,
    night_interval_seconds: float,
) -> float:
    """The night pause wins over any other HTTP pause while the window is on."""

    if night_enabled and in_night_window(now, night_start, night_end):
        return night_interval_seconds
    return interval_seconds


def with_jitter(seconds: float, percent: int, rng: random.Random | None = None) -> float:
    """Spread ``seconds`` by +-``percent`` % so requests do not look periodic."""

    if percent <= 0 or seconds <= 0:
        return seconds
    generator = rng or random
    factor = 1.0 + generator.uniform(-percent, percent) / 100.0
    return max(0.0, seconds * factor)


__all__ = ["base_interval", "in_night_window", "with_jitter"]
