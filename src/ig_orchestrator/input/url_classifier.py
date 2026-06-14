from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from ig_orchestrator.models import PublicationType


class UrlClassifierError(ValueError):
    """Raised when a URL cannot be classified because it is not valid input."""


def classify_instagram_url(url: str) -> PublicationType:
    """Return the initial publication type for an Instagram URL."""

    parsed = urlparse(url.strip())
    _validate_instagram_url(parsed.scheme, parsed.hostname, url)

    segments = [segment.lower() for segment in parsed.path.split("/") if segment]

    if _is_highlight_url(segments):
        return PublicationType.HIGHLIGHTS
    if _is_story_url(segments):
        return PublicationType.STORY
    if _is_reel_url(segments):
        return PublicationType.REEL
    if _is_post_url(segments):
        query = parse_qs(parsed.query, keep_blank_values=True)
        return PublicationType.POST if "img_index" in query else PublicationType.REEL

    return PublicationType.UNKNOWN


def _validate_instagram_url(scheme: str, hostname: str | None, url: str) -> None:
    if scheme not in {"http", "https"}:
        raise UrlClassifierError(f"URL must use http or https: {url}")

    normalized_hostname = (hostname or "").lower().rstrip(".")
    if (
        normalized_hostname != "instagram.com"
        and not normalized_hostname.endswith(".instagram.com")
    ):
        raise UrlClassifierError(f"URL must use an Instagram domain: {url}")


def _is_highlight_url(segments: list[str]) -> bool:
    return len(segments) >= 3 and segments[:2] == ["stories", "highlights"]


def _is_story_url(segments: list[str]) -> bool:
    return len(segments) >= 2 and segments[0] == "stories" and segments[1] != "highlights"


def _is_reel_url(segments: list[str]) -> bool:
    return len(segments) >= 2 and segments[0] == "reel"


def _is_post_url(segments: list[str]) -> bool:
    return len(segments) >= 2 and segments[0] == "p"


__all__ = ["UrlClassifierError", "classify_instagram_url"]
