from __future__ import annotations

import asyncio
import re
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from enum import StrEnum

from ig_orchestrator.logging_config import get_logger

logger = get_logger()

# Error type stored when Instagram itself says the post is gone.
MEDIA_REMOVED_ERROR_TYPE = "MEDIA_REMOVED"

REQUEST_TIMEOUT_SECONDS = 15
MIN_SECONDS_BETWEEN_CHECKS = 2.0
# A browser User-Agent makes Instagram answer the JS error page even for live
# posts (verified 2026-10-24); a plain client UA gets the real page.
_USER_AGENT = "curl/8.4.0"
_CHECKABLE_URL = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/[\w-]+",
    re.IGNORECASE,
)


class PostAvailability(StrEnum):
    EXISTS = "EXISTS"
    REMOVED = "REMOVED"
    UNKNOWN = "UNKNOWN"


AvailabilityChecker = Callable[[str], Awaitable[PostAvailability]]


def is_checkable_url(url: str) -> bool:
    """Only posts/reels have a public page; stories and highlights do not."""

    return _CHECKABLE_URL.match(url.strip()) is not None


def classify_post_html(html: str) -> PostAvailability:
    """Classify the anonymous Instagram page of a post.

    Gone/unavailable posts render the client-side error route (``PolarisErrorRoot``
    with ``pageID: httpErrorPage``); live posts (also 18+) ship ``og:title``.
    Anything else (login wall, rate limit, layout change) is UNKNOWN.
    """

    if "PolarisErrorRoot" in html and "httpErrorPage" in html:
        return PostAvailability.REMOVED
    if 'property="og:title"' in html or "og:title" in html:
        return PostAvailability.EXISTS
    return PostAvailability.UNKNOWN


def _canonical_url(url: str) -> str:
    return url.strip().split("?", 1)[0].split("#", 1)[0]


def _fetch_html(url: str) -> str | None:
    request = urllib.request.Request(
        _canonical_url(url),
        headers={"User-Agent": _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.info("Post availability request failed: url={} error={}", url, exc)
        return None


class InstagramPostAvailabilityChecker:
    """Anonymous check (no login) used after a bot ``Media not found`` answer."""

    def __init__(
        self,
        *,
        fetcher: Callable[[str], str | None] = _fetch_html,
        min_interval_seconds: float = MIN_SECONDS_BETWEEN_CHECKS,
    ) -> None:
        self._fetcher = fetcher
        self._min_interval = min_interval_seconds
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def __call__(self, url: str) -> PostAvailability:
        if not is_checkable_url(url):
            return PostAvailability.UNKNOWN
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            html = await asyncio.to_thread(self._fetcher, url)
            self._last_call = time.monotonic()
        availability = (
            PostAvailability.UNKNOWN if html is None else classify_post_html(html)
        )
        logger.info("Post availability: url={} result={}", url, availability.value)
        return availability


__all__ = [
    "AvailabilityChecker",
    "InstagramPostAvailabilityChecker",
    "MEDIA_REMOVED_ERROR_TYPE",
    "PostAvailability",
    "classify_post_html",
    "is_checkable_url",
]
