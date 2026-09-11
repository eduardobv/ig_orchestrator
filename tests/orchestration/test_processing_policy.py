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


def test_stories_and_non_story_sweeps_preserve_group_priority() -> None:
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
    assert [account.username for account in rest] == ["mixed", "reels_only"]


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
