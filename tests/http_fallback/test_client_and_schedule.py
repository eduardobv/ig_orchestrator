from __future__ import annotations

import json
import random
from datetime import datetime, time

import pytest

from ig_orchestrator.http_fallback.client import (
    KIND_NOT_FOUND,
    KIND_NO_SESSION,
    KIND_RATE_LIMIT,
    KIND_SESSION,
    KIND_TRANSIENT,
    KIND_UNSUPPORTED,
    HttpFallbackError,
    InstagramHttpClient,
    extract_media_files,
)
from ig_orchestrator.http_fallback.config import HttpFallbackConfig
from ig_orchestrator.http_fallback.schedule import (
    base_interval,
    in_night_window,
    with_jitter,
)

POST_URL = "https://www.instagram.com/p/DJryedPJmGk/"


def _image(pk: str) -> dict:
    return {
        "pk": pk,
        "image_versions2": {
            "candidates": [
                {"url": f"small-{pk}", "width": 150, "height": 150},
                {"url": f"big-{pk}", "width": 1080, "height": 1350},
                {"url": f"mid-{pk}", "width": 640, "height": 800},
            ]
        },
    }


def test_carousel_files_use_each_pk_and_the_largest_candidate() -> None:
    files = extract_media_files({"pk": "99", "carousel_media": [_image("1"), _image("2")]})

    assert [(f.name, f.url, f.extension) for f in files] == [
        ("1", "big-1", ".jpg"),
        ("2", "big-2", ".jpg"),
    ]


def test_single_video_prefers_video_versions() -> None:
    item = {
        "pk": "7",
        "video_versions": [
            {"url": "low", "width": 320, "height": 568},
            {"url": "high", "width": 720, "height": 1280},
        ],
        "image_versions2": {"candidates": [{"url": "cover", "width": 720, "height": 1280}]},
    }

    (media,) = extract_media_files(item)

    assert (media.name, media.url, media.extension, media.is_video) == ("7", "high", ".mp4", True)


def test_pk_with_user_suffix_is_trimmed() -> None:
    (media,) = extract_media_files({"id": "123_456", "image_versions2": _image("x")["image_versions2"]})

    assert media.name == "123"


def _client(status: int, body: object = None, *, sessionid: str = "SECRETSESSION"):
    seen: dict[str, object] = {}

    def transport(url, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        raw = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
        return status, raw

    config = HttpFallbackConfig(sessionid=sessionid, csrftoken="CSRF")
    return InstagramHttpClient(config, transport=transport), seen


def test_fetch_builds_the_request_and_returns_files() -> None:
    client, seen = _client(200, {"items": [{"carousel_media": [_image("5")], "pk": "9"}]})

    files = client.fetch_media_files(POST_URL)

    assert [f.name for f in files] == ["5"]
    assert seen["url"] == "https://i.instagram.com/api/v1/media/3633219519706980772/info/"
    headers = seen["headers"]
    assert headers["x-ig-app-id"] == "936619743392459"
    assert "sessionid=SECRETSESSION" in headers["cookie"]
    assert "csrftoken=CSRF" in headers["cookie"]


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (401, {}, KIND_SESSION),
        (403, {}, KIND_SESSION),
        (400, {"message": "checkpoint_required"}, KIND_SESSION),
        (200, {"message": "login_required", "items": []}, KIND_SESSION),
        (429, {}, KIND_RATE_LIMIT),
        (404, {}, KIND_NOT_FOUND),
        (200, {"items": []}, KIND_NOT_FOUND),
        (500, {}, KIND_TRANSIENT),
    ],
)
def test_status_codes_map_to_a_kind(status, body, kind) -> None:
    client, _ = _client(status, body)

    with pytest.raises(HttpFallbackError) as info:
        client.fetch_media_files(POST_URL)

    assert info.value.kind == kind


def test_session_error_explains_what_to_do_and_never_leaks_the_cookie() -> None:
    client, _ = _client(403)

    with pytest.raises(HttpFallbackError) as info:
        client.fetch_media_files(POST_URL)

    message = str(info.value)
    assert "caducada" in message and "sessionid" in message and "Probar sesión" in message
    assert "SECRETSESSION" not in message


def test_missing_session_and_unsupported_url() -> None:
    client, _ = _client(200, {}, sessionid="")
    with pytest.raises(HttpFallbackError) as info:
        client.fetch_media_files(POST_URL)
    assert info.value.kind == KIND_NO_SESSION

    client, _ = _client(200, {})
    with pytest.raises(HttpFallbackError) as info:
        client.fetch_media_files("https://www.instagram.com/stories/foo/123/")
    assert info.value.kind == KIND_UNSUPPORTED


def test_night_window_crossing_midnight() -> None:
    start, end = time(22, 0), time(6, 0)
    assert in_night_window(datetime(2026, 1, 1, 23, 30), start, end)
    assert in_night_window(datetime(2026, 1, 2, 3, 0), start, end)
    assert not in_night_window(datetime(2026, 1, 2, 6, 0), start, end)
    assert not in_night_window(datetime(2026, 1, 2, 12, 0), start, end)
    assert not in_night_window(datetime(2026, 1, 2, 3, 0), time(0, 0), time(0, 0))


def test_night_interval_wins_inside_the_window() -> None:
    kwargs = dict(
        interval_seconds=30,
        night_enabled=True,
        night_start=time(0, 0),
        night_end=time(6, 0),
        night_interval_seconds=300,
    )
    assert base_interval(datetime(2026, 1, 1, 3, 0), **kwargs) == 300
    assert base_interval(datetime(2026, 1, 1, 12, 0), **kwargs) == 30
    assert base_interval(datetime(2026, 1, 1, 3, 0), **{**kwargs, "night_enabled": False}) == 30


def test_jitter_stays_within_the_percentage() -> None:
    rng = random.Random(1)
    values = [with_jitter(100, 20, rng) for _ in range(200)]
    assert min(values) >= 80 and max(values) <= 120
    assert with_jitter(100, 0, rng) == 100
