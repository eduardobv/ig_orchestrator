from __future__ import annotations

import pytest

from ig_orchestrator.input import UrlClassifierError, classify_instagram_url
from ig_orchestrator.models import PublicationType


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.instagram.com/p/DZPjwEjitxx/?img_index=1", PublicationType.POST),
        ("https://www.instagram.com/reel/ABC123xyz/", PublicationType.REEL),
        ("https://www.instagram.com/p/DZPjwEjitxx/", PublicationType.REEL),
        ("https://www.instagram.com/stories/user_name/", PublicationType.STORY),
        (
            "https://www.instagram.com/stories/highlights/17851330941375169/",
            PublicationType.HIGHLIGHTS,
        ),
    ],
)
def test_classify_known_instagram_urls(
    url: str, expected: PublicationType
) -> None:
    assert classify_instagram_url(url) == expected


def test_unknown_is_reserved_for_supported_instagram_domain() -> None:
    assert (
        classify_instagram_url("https://www.instagram.com/explore/tags/example/")
        == PublicationType.UNKNOWN
    )


def test_rejects_non_instagram_url() -> None:
    with pytest.raises(UrlClassifierError, match="Instagram domain"):
        classify_instagram_url("https://example.com/foo")
