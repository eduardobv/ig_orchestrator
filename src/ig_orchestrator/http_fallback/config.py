"""Effective configuration of the HTTP fallback (built from ``RunSettings``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from ig_orchestrator.orchestration.run_settings import DEFAULT_HTTP_USER_AGENT, RunSettings


def parse_hhmm(text: str) -> time:
    hours, minutes = text.strip().split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True, slots=True)
class HttpFallbackConfig:
    enabled: bool = True
    posts: bool = True
    reels: bool = True
    bot_attempts: int = 2
    retry_delay_seconds: float = 10.0
    max_consecutive: int = 3
    interval_seconds: float = 30.0
    jitter_percent: int = 20
    max_per_run: int = 200
    recheck_every: int = 10
    pause_429_minutes: int = 15
    max_429: int = 3
    request_timeout_seconds: float = 30.0
    download_timeout_seconds: float = 120.0
    night_enabled: bool = True
    night_start: time = time(0, 0)
    night_end: time = time(6, 0)
    night_interval_seconds: float = 300.0
    botdown_enabled: bool = True
    probe_urls: tuple[str, ...] = ("https://www.instagram.com/p/DeO6TtQMqY9/",)
    botdown_silences: int = 2
    probe_timeout_seconds: float = 60.0
    probe_gap_minutes: int = 10
    botdown_interval_seconds: float = 120.0
    botdown_block_minutes: int = 60
    botdown_max_blocks: int = 6
    botdown_wait_threshold: int = 100
    botdown_wait_minutes: int = 60
    botdown_wait_attempts: int = 1
    sessionid: str = ""
    csrftoken: str = ""
    app_id: str = "936619743392459"
    user_agent: str = DEFAULT_HTTP_USER_AGENT
    api_host: str = "i.instagram.com"

    @property
    def active(self) -> bool:
        """True when the run must use the coordinator (HTTP and/or bot-down guard)."""

        return self.enabled or self.botdown_enabled

    @property
    def has_session(self) -> bool:
        return bool(self.sessionid.strip())

    @classmethod
    def from_run_settings(cls, rs: RunSettings) -> "HttpFallbackConfig":
        return cls(
            enabled=rs.http_enabled,
            posts=rs.http_posts,
            reels=rs.http_reels,
            bot_attempts=rs.http_bot_attempts,
            retry_delay_seconds=float(rs.stall_probe_delay_seconds),
            max_consecutive=rs.http_max_consecutive,
            interval_seconds=float(rs.http_interval_seconds),
            jitter_percent=rs.http_jitter_percent,
            max_per_run=rs.http_max_per_run,
            recheck_every=rs.http_recheck_every,
            pause_429_minutes=rs.http_pause_429_minutes,
            max_429=rs.http_max_429,
            request_timeout_seconds=float(rs.http_request_timeout_seconds),
            download_timeout_seconds=float(rs.http_download_timeout_seconds),
            night_enabled=rs.night_enabled,
            night_start=parse_hhmm(rs.night_start),
            night_end=parse_hhmm(rs.night_end),
            night_interval_seconds=float(rs.night_interval_seconds),
            botdown_enabled=rs.botdown_enabled,
            probe_urls=tuple(u for u in rs.botdown_probe_urls.split(",") if u.strip()),
            botdown_silences=rs.botdown_silences,
            probe_timeout_seconds=float(rs.botdown_probe_timeout_seconds),
            probe_gap_minutes=rs.botdown_probe_gap_minutes,
            botdown_interval_seconds=float(rs.botdown_interval_seconds),
            botdown_block_minutes=rs.botdown_block_minutes,
            botdown_max_blocks=rs.botdown_max_blocks,
            botdown_wait_threshold=rs.botdown_wait_threshold,
            botdown_wait_minutes=rs.botdown_wait_minutes,
            botdown_wait_attempts=rs.botdown_wait_attempts,
            sessionid=rs.http_sessionid.strip(),
            csrftoken=rs.http_csrftoken.strip(),
            app_id=rs.http_app_id.strip() or "936619743392459",
            user_agent=rs.http_user_agent.strip() or DEFAULT_HTTP_USER_AGENT,
            api_host=rs.http_api_host.strip() or "i.instagram.com",
        )


__all__ = ["HttpFallbackConfig", "parse_hhmm"]
