from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from ig_orchestrator.telegram import BotResponseStatus, parse_bot_response
from ig_orchestrator.telegram.large_file import (
    LargeFileConfig,
    LargeFileDownloadError,
    download_large_file,
    extract_download_url,
    media_id_from_url,
    shortcode_to_media_id,
)

LONG_URL = "https://cdn.example.com/v/" + "a1B2-_" * 170 + ".mp4?sig=" + "x" * 20


@pytest.mark.parametrize(
    ("shortcode", "media_id"),
    [
        ("De1jzesDHug", "4014272112143137696"),
        ("DUmATXqE99I", "3829749864197250888"),
        ("Deys2HkxrIy", "4013467450971959858"),
    ],
)
def test_shortcode_decodes_to_verified_media_ids(shortcode: str, media_id: str) -> None:
    assert shortcode_to_media_id(shortcode) == media_id


@pytest.mark.parametrize("shortcode", ["", "bad*code", "A" * 12, "_" * 11])
def test_invalid_shortcodes_return_none(shortcode: str) -> None:
    assert shortcode_to_media_id(shortcode) is None


def test_media_id_from_post_and_reel_urls() -> None:
    assert (
        media_id_from_url("https://www.instagram.com/reel/Deys2HkxrIy/?igsh=abc")
        == "4013467450971959858"
    )
    assert (
        media_id_from_url("https://www.instagram.com/user/p/De1jzesDHug/")
        == "4014272112143137696"
    )
    assert media_id_from_url("https://www.instagram.com/stories/user/123/") is None


def test_large_file_message_is_parsed_with_the_full_url() -> None:
    assert len(LONG_URL) > 1000
    response = parse_bot_response(f"error_file_too_large_link\n{LONG_URL}")

    assert response.status is BotResponseStatus.LARGE_FILE_LINK
    assert response.download_url == LONG_URL
    assert extract_download_url("no link here") is None


class _Handler(BaseHTTPRequestHandler):
    body = b"x" * 3_000_000

    def log_message(self, *_args) -> None:  # silence test output
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/forbidden":
            self.send_response(403)
            self.end_headers()
        elif self.path == "/cut":
            self.send_response(200)
            self.send_header("Content-Length", str(len(self.body) + 500))
            self.end_headers()
            self.wfile.write(self.body)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.body)))
            self.end_headers()
            self.wfile.write(self.body)


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_download_streams_to_part_and_renames(tmp_path: Path, server: str) -> None:
    target = tmp_path / "out" / "4013467450971959858.mp4"

    result = asyncio.run(download_large_file(f"{server}/ok", target, LargeFileConfig()))

    assert result == target
    assert target.stat().st_size == len(_Handler.body)
    assert not list(target.parent.glob("*.part"))


@pytest.mark.parametrize("path", ["/forbidden", "/cut"])
def test_download_failures_raise_and_leave_no_files(
    tmp_path: Path, server: str, path: str
) -> None:
    target = tmp_path / "f.mp4"

    with pytest.raises(LargeFileDownloadError):
        asyncio.run(download_large_file(f"{server}{path}", target, LargeFileConfig()))

    assert not target.exists()
    assert not list(tmp_path.glob("*.part"))


def test_download_rejects_files_over_the_limit(tmp_path: Path, server: str) -> None:
    config = LargeFileConfig(max_megabytes=1)

    with pytest.raises(LargeFileDownloadError, match="too big"):
        asyncio.run(download_large_file(f"{server}/ok", tmp_path / "f.mp4", config))
