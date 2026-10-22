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


# Public post/reel shortcodes have 11 characters; the links of private accounts carry a
# much longer id (~39 characters) that the download bot cannot resolve.
PUBLIC_SHORTCODE_MAX_LENGTH = 14


def is_private_post_url(url: str) -> bool:
    """True for an Instagram post/reel URL with the long id of a private account."""

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname != "instagram.com" and not hostname.endswith(".instagram.com"):
        return False
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0].lower() not in {"p", "reel", "reels", "tv"}:
        return False
    return len(segments[1]) > PUBLIC_SHORTCODE_MAX_LENGTH


def find_private_post_urls(lines: list[str]) -> list[str]:
    """The lines of *lines* that are private-account post URLs (see ``is_private_post_url``)."""

    return [line.strip() for line in lines if line.strip() and is_private_post_url(line)]


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


__all__ = [
    "UrlClassifierError",
    "classify_instagram_url",
    "find_private_post_urls",
    "is_private_post_url",
]
