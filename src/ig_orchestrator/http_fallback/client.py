"""Instagram web API client: media info by id and file download (blocking)."""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ig_orchestrator.http_fallback.config import HttpFallbackConfig
from ig_orchestrator.telegram.large_file import media_id_from_url

KIND_NO_SESSION = "NO_SESSION"
KIND_SESSION = "SESSION"
KIND_RATE_LIMIT = "RATE_LIMIT"
KIND_NOT_FOUND = "NOT_FOUND"
KIND_TRANSIENT = "TRANSIENT"
KIND_UNSUPPORTED = "UNSUPPORTED"

# Texts shown to the user: what happened AND what to do.
SESSION_ADVICE = (
    "La cookie de Instagram está caducada o ha sido rechazada. Vuelve a entrar en "
    "instagram.com con Chrome, copia la nueva cookie «sessionid» (F12 > Application > "
    "Cookies > instagram.com) en Configuración > Ejecución > Sesión HTTP y pulsa "
    "«Probar sesión»."
)
NO_SESSION_ADVICE = (
    "No hay cookie de Instagram configurada. Copia la cookie «sessionid» de Chrome "
    "(F12 > Application > Cookies > instagram.com) en Configuración > Ejecución > "
    "Sesión HTTP."
)

_CHUNK = 256 * 1024
_SESSION_MARKERS = ("login_required", "checkpoint_required", "challenge_required")


class HttpFallbackError(Exception):
    """A failed request; ``kind`` tells the caller how to react."""

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


@dataclass(frozen=True, slots=True)
class MediaFile:
    name: str  # file name without extension: the item's pk
    url: str
    extension: str  # ".jpg" / ".mp4"
    is_video: bool = False


# (url, headers, timeout) -> (status, body)
Transport = Callable[[str, dict[str, str], float], tuple[int, bytes]]
# (url, destination, headers, timeout) -> None (raises HttpFallbackError)
FileFetcher = Callable[[str, Path, dict[str, str], float], None]


def default_transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, body
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise HttpFallbackError(KIND_TRANSIENT, f"{type(exc).__name__}: {exc}") from exc


def default_file_fetcher(
    url: str, destination: Path, headers: dict[str, str], timeout: float
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    part.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers=headers)
    try:
        written = 0
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with part.open("wb") as handle:
                while chunk := response.read(_CHUNK):
                    written += len(chunk)
                    handle.write(chunk)
        if written == 0:
            raise HttpFallbackError(KIND_TRANSIENT, "Empty download.")
        part.replace(destination)
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        # An expired signed CDN url answers 403: the caller asks for fresh urls.
        raise HttpFallbackError(KIND_TRANSIENT, f"CDN HTTP {exc.code}", exc.code) from exc
    except HttpFallbackError:
        part.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        part.unlink(missing_ok=True)
        raise HttpFallbackError(KIND_TRANSIENT, f"{type(exc).__name__}: {exc}") from exc


class InstagramHttpClient:
    """Fetches ``/api/v1/media/<id>/info/`` with the configured session."""

    def __init__(
        self,
        config: HttpFallbackConfig,
        *,
        transport: Transport = default_transport,
        file_fetcher: FileFetcher = default_file_fetcher,
    ) -> None:
        self._config = config
        self._transport = transport
        self._file_fetcher = file_fetcher

    def _headers(self) -> dict[str, str]:
        cookie = f"sessionid={self._config.sessionid}"
        if self._config.csrftoken:
            cookie += f"; csrftoken={self._config.csrftoken}"
        return {
            "accept": "*/*",
            "cookie": cookie,
            "origin": "https://www.instagram.com",
            "referer": "https://www.instagram.com/",
            "user-agent": self._config.user_agent,
            "x-ig-app-id": self._config.app_id,
        }

    def fetch_media_files(self, post_url: str) -> list[MediaFile]:
        """Return the best file of every item of a post/reel (blocking)."""

        if not self._config.has_session:
            raise HttpFallbackError(KIND_NO_SESSION, NO_SESSION_ADVICE)
        media_id = media_id_from_url(post_url)
        if media_id is None:
            raise HttpFallbackError(KIND_UNSUPPORTED, f"URL no soportada: {post_url}")
        url = f"https://{self._config.api_host}/api/v1/media/{media_id}/info/"
        status, body = self._transport(
            url, self._headers(), self._config.request_timeout_seconds
        )
        text = body.decode("utf-8", errors="replace") if body else ""
        if status in (401, 403) or (status == 400 and _is_session_problem(text)):
            raise HttpFallbackError(KIND_SESSION, SESSION_ADVICE, status)
        if status == 429:
            raise HttpFallbackError(KIND_RATE_LIMIT, "Instagram respondió 429.", status)
        if status == 404:
            raise HttpFallbackError(KIND_NOT_FOUND, "Instagram: contenido no encontrado.", status)
        if status >= 500 or status == 408:
            raise HttpFallbackError(KIND_TRANSIENT, f"HTTP {status}", status)
        if status != 200:
            raise HttpFallbackError(KIND_TRANSIENT, f"HTTP {status}", status)
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise HttpFallbackError(KIND_TRANSIENT, "Respuesta no es JSON.", status) from exc
        if _is_session_problem(str(data.get("message", ""))):
            raise HttpFallbackError(KIND_SESSION, SESSION_ADVICE, status)
        items = data.get("items") or []
        if not items:
            raise HttpFallbackError(KIND_NOT_FOUND, "Instagram: sin contenido.", status)
        files = extract_media_files(items[0])
        if not files:
            raise HttpFallbackError(KIND_NOT_FOUND, "Instagram: sin archivos descargables.", status)
        return files

    def download(self, media: MediaFile, destination: Path) -> None:
        """Download one file from the CDN (no cookies needed)."""

        headers = {"user-agent": self._config.user_agent}
        self._file_fetcher(
            media.url, destination, headers, self._config.download_timeout_seconds
        )


def _is_session_problem(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _SESSION_MARKERS)


def extract_media_files(item: dict) -> list[MediaFile]:
    """Best-quality file per item; the carousel children use their own pk."""

    children = item.get("carousel_media") or []
    sources = children if children else [item]
    files: list[MediaFile] = []
    for source in sources:
        media = _best_file(source)
        if media is not None:
            files.append(media)
    return files


def _best_file(source: dict) -> MediaFile | None:
    name = str(source.get("pk") or source.get("id") or "").split("_")[0]
    if not name:
        return None
    videos = source.get("video_versions") or []
    if videos:
        best = max(videos, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
        return MediaFile(name=name, url=best["url"], extension=".mp4", is_video=True)
    candidates = (source.get("image_versions2") or {}).get("candidates") or []
    if not candidates:
        return None
    best = max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))
    return MediaFile(name=name, url=best["url"], extension=".jpg")


__all__ = [
    "HttpFallbackError",
    "InstagramHttpClient",
    "KIND_NOT_FOUND",
    "KIND_NO_SESSION",
    "KIND_RATE_LIMIT",
    "KIND_SESSION",
    "KIND_TRANSIENT",
    "KIND_UNSUPPORTED",
    "MediaFile",
    "NO_SESSION_ADVICE",
    "SESSION_ADVICE",
    "extract_media_files",
]
