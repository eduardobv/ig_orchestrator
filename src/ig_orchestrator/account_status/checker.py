"""Anonymous check of one Instagram profile page (no login)."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

# Same reason as ``orchestration.post_availability``: a browser User-Agent gets the JS shell.
_USER_AGENT = "curl/8.4.0"
_PROFILE_ID = re.compile(r'"profile_id"\s*:\s*"?\d+')
_USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")


class AccountStatus(StrEnum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"  # network failure or unexpected HTTP status: nothing can be said


@dataclass(frozen=True, slots=True)
class HttpResult:
    http_status: int | None
    body: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    status: AccountStatus
    http_status: int | None
    detail: str = ""
    rate_limited: bool = False


Fetcher = Callable[[str, float], HttpResult]


def profile_url(username: str) -> str:
    return f"https://www.instagram.com/{username.strip().strip('@')}/"


def is_valid_username(username: str) -> bool:
    return _USERNAME.match(username.strip().strip("@")) is not None


def default_fetcher(url: str, timeout: float) -> HttpResult:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return HttpResult(exc.code, error=str(exc))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return HttpResult(None, error=str(exc))


def classify_profile(result: HttpResult) -> CheckOutcome:
    """``profile_id`` in the HTML means the account exists; a 200 page without it does not.

    429 is reported through ``rate_limited`` so the runner stops at once.
    """

    code = result.http_status
    if code == 429:
        return CheckOutcome(AccountStatus.UNKNOWN, code, "HTTP 429", rate_limited=True)
    if code is None:
        return CheckOutcome(AccountStatus.UNKNOWN, None, result.error or "sin respuesta")
    if code == 404:
        return CheckOutcome(AccountStatus.UNAVAILABLE, code, "HTTP 404")
    if code != 200:
        return CheckOutcome(AccountStatus.UNKNOWN, code, f"HTTP {code}")
    if _PROFILE_ID.search(result.body):
        return CheckOutcome(AccountStatus.AVAILABLE, code, "profile_id")
    return CheckOutcome(AccountStatus.UNAVAILABLE, code, "sin profile_id")


def check_account(
    username: str, *, timeout: float = 15.0, fetcher: Fetcher = default_fetcher
) -> CheckOutcome:
    if not is_valid_username(username):
        return CheckOutcome(AccountStatus.UNKNOWN, None, "nombre no válido para consultar")
    return classify_profile(fetcher(profile_url(username), timeout))


__all__ = [
    "AccountStatus",
    "CheckOutcome",
    "HttpResult",
    "check_account",
    "classify_profile",
    "default_fetcher",
    "is_valid_username",
    "profile_url",
]
