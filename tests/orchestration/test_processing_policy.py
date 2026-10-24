from __future__ import annotations

from datetime import date
from pathlib import Path

from ig_orchestrator.db import connect, init_database, init_gui_database
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.orchestration.processing_policy import (
    AccountOrderInfo,
    STORIES_FIRST_SETTING_KEY,
    AccountJobScope,
    non_story_sweep_accounts,
    ordered_main_pass_jobs,
    read_stories_first_enabled,
    stories_sweep_accounts,
    write_stories_first_enabled,
)


def test_ordered_main_pass_jobs_puts_all_story_types_first() -> None:
    generated = _job(1, PublicationType.STORY, UrlSource.GENERATED_STORY)
    input_story = _job(2, PublicationType.STORY, UrlSource.INPUT_URL)
    reel = _job(3, PublicationType.REEL, UrlSource.INPUT_URL)
    highlight = _job(4, PublicationType.HIGHLIGHTS, UrlSource.INPUT_URL)

    ordered = ordered_main_pass_jobs(
        [reel, highlight, input_story, generated],
        AccountJobScope.ALL,
    )

    assert [job.id for job in ordered] == [generated.id, input_story.id, reel.id, highlight.id]


def test_stories_sweep_keeps_batch_order_and_non_story_sweep_is_lightest_first() -> None:
    story_only = _account(1, "story_only")
    mixed = _account(2, "mixed")
    reels_only = _account(3, "reels_only")
    jobs = {
        1: [_job(10, PublicationType.STORY, UrlSource.GENERATED_STORY, account_id=1)],
        2: [
            _job(20, PublicationType.STORY, UrlSource.GENERATED_STORY, account_id=2),
            _job(21, PublicationType.REEL, UrlSource.INPUT_URL, account_id=2),
        ],
        3: [_job(30, PublicationType.REEL, UrlSource.INPUT_URL, account_id=3)],
    }

    stories = stories_sweep_accounts([story_only, mixed, reels_only], jobs)
    rest = non_story_sweep_accounts([story_only, mixed, reels_only], jobs)

    assert [account.username for account in stories] == ["story_only", "mixed"]
    # Equal workload (1 reel each): ties fall back to batch order.
    assert [account.username for account in rest] == ["mixed", "reels_only"]


def test_stories_sweep_puts_priority_first_then_batch_order() -> None:
    accounts = [_account(i, f"a{i}") for i in (1, 2, 3)]
    jobs = {
        i: [_job(i * 10, PublicationType.STORY, UrlSource.GENERATED_STORY, account_id=i)]
        for i in (1, 2, 3)
    }

    plain = stories_sweep_accounts(accounts, jobs)
    ranked = stories_sweep_accounts(
        accounts, jobs, {3: AccountOrderInfo(priority=1), 2: AccountOrderInfo(priority=2)}
    )

    assert [a.username for a in plain] == ["a1", "a2", "a3"]
    assert [a.username for a in ranked] == ["a3", "a2", "a1"]


def test_non_story_sweep_orders_by_workload_reels_posts_new_then_batch() -> None:
    def many(account_id: int, reels: int, posts: int, base: int) -> list[UrlJob]:
        out = [
            _job(base + n, PublicationType.REEL, UrlSource.INPUT_URL, account_id=account_id)
            for n in range(reels)
        ]
        out += [
            _job(base + 50 + n, PublicationType.POST, UrlSource.INPUT_URL, account_id=account_id)
            for n in range(posts)
        ]
        return out

    names = ["big", "light_posts", "light_reels", "tie_old", "tie_new", "tie_first"]
    accounts = [_account(i, n) for i, n in enumerate(names, start=1)]
    jobs = {
        1: many(1, 60, 40, 1000),  # 100 URLs: last
        2: many(2, 0, 3, 2000),  # 3 URLs, 0 reels
        3: many(3, 3, 0, 3000),  # 3 URLs, 3 reels: before light_posts
        4: many(4, 2, 1, 4000),  # 3 URLs, 2 reels, 1 post
        5: many(5, 2, 1, 5000),  # same as 4 but a new account
        6: many(6, 2, 1, 6000),  # same as 4, listed later than 4
    }
    jobs[7] = []
    info = {5: AccountOrderInfo(is_new_account=True)}

    rest = non_story_sweep_accounts(accounts, jobs, info)

    assert [a.username for a in rest] == [
        "light_reels",
        "tie_old",
        "tie_first",
        "tie_new",
        "light_posts",
        "big",
    ]


def test_non_story_sweep_ignores_stories_when_counting() -> None:
    heavy_stories = _account(1, "stories_many")
    other = _account(2, "other")
    jobs = {
        1: [
            *[
                _job(10 + n, PublicationType.STORY, UrlSource.GENERATED_STORY, account_id=1)
                for n in range(5)
            ],
            _job(30, PublicationType.REEL, UrlSource.INPUT_URL, account_id=1),
        ],
        2: [
            _job(40, PublicationType.REEL, UrlSource.INPUT_URL, account_id=2),
            _job(41, PublicationType.REEL, UrlSource.INPUT_URL, account_id=2),
        ],
    }

    rest = non_story_sweep_accounts([other, heavy_stories], jobs)

    assert [a.username for a in rest] == ["stories_many", "other"]


def test_stories_first_setting_defaults_true_and_can_be_disabled(
    tmp_path: Path,
) -> None:
    v1_path = tmp_path / "orchestrator.sqlite"
    gui_path = tmp_path / "orchestrator_gui.sqlite"
    init_database(v1_path)
    init_gui_database(gui_path)

    with connect(v1_path) as connection:
        assert read_stories_first_enabled(connection) is True
        write_stories_first_enabled(connection, False)
        assert read_stories_first_enabled(connection) is False
        stored = connection.execute(
            "SELECT value FROM app_config WHERE key = ?",
            (STORIES_FIRST_SETTING_KEY,),
        ).fetchone()
        assert stored["value"] == "0"

    with connect(gui_path) as connection:
        assert read_stories_first_enabled(connection) is True
        write_stories_first_enabled(connection, False)
        assert read_stories_first_enabled(connection) is False
        write_stories_first_enabled(connection, True)
        assert read_stories_first_enabled(connection) is True


def _account(account_id: int, username: str) -> Account:
    return Account(
        id=account_id,
        batch_id=1,
        username=username,
        start_now_date=date(2026, 9, 4),
        download_stories=True,
        status=AccountStatus.PENDING,
    )


def _job(
    job_id: int,
    publication_type: PublicationType,
    source: UrlSource,
    *,
    account_id: int = 1,
) -> UrlJob:
    url = (
        "https://www.instagram.com/stories/example/"
        if publication_type is PublicationType.STORY
        else "https://www.instagram.com/reel/ABC/"
    )
    if publication_type is PublicationType.HIGHLIGHTS:
        url = "https://www.instagram.com/stories/highlights/1/"
    return UrlJob(
        id=job_id,
        account_id=account_id,
        url=url,
        publication_type=publication_type,
        source=source,
        status=UrlJobStatus.PENDING,
    )
