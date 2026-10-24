from __future__ import annotations

import asyncio
import re
import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ig_orchestrator.logging_config import get_logger

logger = get_logger()

# Error types stored when the bot only offers a download link (files > 50 MB).
FILE_TOO_LARGE_LINK_MARKER = "error_file_too_large_link"
FILE_TOO_LARGE_DOWNLOAD_FAILED = "FILE_TOO_LARGE_DOWNLOAD_FAILED"

# Same client UA used for the anonymous Instagram check; verified with the bot's
# links (a truncated URL answers 403, the full one 200 video/mp4).
_USER_AGENT = "curl/8.4.0"
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_SHORTCODE_IN_URL = re.compile(
    r"instagram\.com/(?:[^/?#]+/)?(?:p|reel|reels|tv)/([\w-]+)",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://\S+")
_CHUNK_BYTES = 1024 * 1024


class LargeFileDownloadError(RuntimeError):
    """Raised when the direct download of a large file fails."""


@dataclass(frozen=True, slots=True)
class LargeFileConfig:
    enabled: bool = True
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 120.0
    max_megabytes: int = 500

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ValueError("large file timeouts must be positive")
        if self.max_megabytes <= 0:
            raise ValueError("max_megabytes must be positive")


def shortcode_to_media_id(shortcode: str) -> str | None:
    """Decode an Instagram shortcode (base 64) into its numeric media id."""

    if not shortcode or len(shortcode) > 11:
        return None
    value = 0
    for char in shortcode:
        index = _ALPHABET.find(char)
        if index < 0:
            return None
        value = value * 64 + index
    if value >= 1 << 64:
        return None
    return str(value)


def media_id_from_url(url: str) -> str | None:
    """Return the media id for a /p/ or /reel/ URL, or None when undecodable."""

    match = _SHORTCODE_IN_URL.search(url)
    if match is None:
        return None
    return shortcode_to_media_id(match.group(1))


def extract_download_url(message: str | None) -> str | None:
    """Return the first full http(s) URL of a bot message (never truncated)."""

    if not message:
        return None
    match = _URL.search(message)
    return match.group(0) if match else None


async def download_large_file(
    url: str,
    destination: Path,
    config: LargeFileConfig,
) -> Path:
    """Stream url to destination atomically; raises LargeFileDownloadError."""

    return await asyncio.to_thread(_download_blocking, url, destination, config)


def _download_blocking(url: str, destination: Path, config: LargeFileConfig) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(destination.name + ".part")
    part_path.unlink(missing_ok=True)
    max_bytes = config.max_megabytes * 1024 * 1024
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        # urlopen's timeout applies to connect and to each socket read.
        timeout = max(config.connect_timeout_seconds, config.read_timeout_seconds)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            expected = _content_length(response)
            if expected is not None and expected > max_bytes:
                raise LargeFileDownloadError(
                    f"File too big: {expected} bytes (limit {max_bytes})."
                )
            written = 0
            with part_path.open("wb") as handle:
                while chunk := response.read(_CHUNK_BYTES):
                    written += len(chunk)
                    if written > max_bytes:
                        raise LargeFileDownloadError(
                            f"File exceeds the limit of {max_bytes} bytes."
                        )
                    handle.write(chunk)
        if expected is not None and written != expected:
            raise LargeFileDownloadError(
                f"Incomplete download: {written} of {expected} bytes."
            )
        if written == 0:
            raise LargeFileDownloadError("Empty download.")
        part_path.replace(destination)
    except LargeFileDownloadError:
        part_path.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        part_path.unlink(missing_ok=True)
        raise LargeFileDownloadError(f"{type(exc).__name__}: {exc}") from exc
    return destination


def _content_length(response: object) -> int | None:
    value = getattr(response, "headers", {}).get("Content-Length")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


__all__ = [
    "FILE_TOO_LARGE_DOWNLOAD_FAILED",
    "FILE_TOO_LARGE_LINK_MARKER",
    "LargeFileConfig",
    "LargeFileDownloadError",
    "download_large_file",
    "extract_download_url",
    "media_id_from_url",
    "shortcode_to_media_id",
]
