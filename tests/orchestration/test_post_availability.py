from __future__ import annotations

import asyncio

from ig_orchestrator.orchestration.post_availability import (
    InstagramPostAvailabilityChecker,
    PostAvailability,
    classify_post_html,
    is_checkable_url,
)

ERROR_PAGE = (
    '..."rootView":{"allResources":[{"__dr":"PolarisErrorRoot.entrypoint"}]},'
    '"polarisRouteConfig":{"pageID":"httpErrorPage"},"url":"\/p\/X\/"...'
)
OK_PAGE = '<meta property="og:title" content="Someone on Instagram"/><script>x</script>'


def test_classify_error_page_as_removed() -> None:
    assert classify_post_html(ERROR_PAGE) is PostAvailability.REMOVED


def test_classify_page_with_og_title_as_existing() -> None:
    assert classify_post_html(OK_PAGE) is PostAvailability.EXISTS


def test_classify_other_pages_as_unknown() -> None:
    assert classify_post_html("<html>Log in to Instagram</html>") is PostAvailability.UNKNOWN


def test_only_posts_and_reels_are_checkable() -> None:
    assert is_checkable_url("https://www.instagram.com/p/DeH8FAMTCas/?img_index=1")
    assert is_checkable_url("https://www.instagram.com/reel/De1k6zYI7Nc/")
    assert is_checkable_url("https://www.instagram.com/someone/reel/De1k6zYI7Nc/")
    assert not is_checkable_url("https://www.instagram.com/stories/someone/")
    assert not is_checkable_url("https://www.instagram.com/stories/highlights/1/")


def test_checker_strips_query_and_returns_unknown_on_network_failure() -> None:
    seen: list[str] = []

    def fetch(url: str) -> str | None:
        seen.append(url)
        return None

    checker = InstagramPostAvailabilityChecker(fetcher=fetch, min_interval_seconds=0)
    result = asyncio.run(checker("https://www.instagram.com/p/AAA/?img_index=2"))

    assert result is PostAvailability.UNKNOWN
    assert seen == ["https://www.instagram.com/p/AAA/?img_index=2"]


def test_checker_skips_stories_without_a_request() -> None:
    def fetch(url: str) -> str | None:
        raise AssertionError("must not fetch stories")

    checker = InstagramPostAvailabilityChecker(fetcher=fetch, min_interval_seconds=0)

    assert asyncio.run(checker("https://www.instagram.com/stories/u/")) is PostAvailability.UNKNOWN


def test_checker_passes_the_configured_timeout_to_the_default_fetcher(monkeypatch) -> None:
    from ig_orchestrator.orchestration import post_availability as module

    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        seen["timeout"] = timeout
        raise OSError("offline")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    checker = module.InstagramPostAvailabilityChecker(
        min_interval_seconds=0, timeout_seconds=4.5
    )

    import asyncio

    result = asyncio.run(checker("https://www.instagram.com/reel/ABC123xyz/"))

    assert result is module.PostAvailability.UNKNOWN
    assert seen["timeout"] == 4.5
