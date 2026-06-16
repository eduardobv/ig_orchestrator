from datetime import date, datetime, timezone
from pathlib import Path

from ig_orchestrator.db import (
    AccountRepository,
    DownloadRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    DownloadFile,
    DownloadFileStatus,
    MediaType,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.reports import (
    MarkdownReport,
    MarkdownReportBuilder,
    MarkdownReportFile,
    MarkdownReportRow,
    render_markdown_report,
)


def test_render_markdown_report_formats_zero_and_multiple_files() -> None:
    report = MarkdownReport(
        run_id=7,
        executed_at=datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc),
        rows=(
            MarkdownReportRow(
                username="example_user",
                publication_type=PublicationType.STORY,
                url="https://www.instagram.com/stories/example_user/",
                status=UrlJobStatus.FAILED_FINAL.value,
            ),
            MarkdownReportRow(
                username="example_user",
                publication_type=PublicationType.REEL,
                url="https://www.instagram.com/reel/ABC123xyz/",
                status=UrlJobStatus.COMPLETED.value,
                files=(
                    MarkdownReportFile(
                        filename="video.mp4",
                        directory="working/example_user/reels",
                    ),
                    MarkdownReportFile(
                        filename="cover.jpg",
                        directory="working/example_user",
                    ),
                ),
            ),
        ),
    )

    markdown = render_markdown_report(report)

    assert "Fecha y hora de ejecucion: 2026-06-15T10:30:00+00:00" in markdown
    assert "| Username | Tipo | Urls | Fichero | Cantidad | Estado | Directory |" in markdown
    assert (
        "| example_user | Story | https://www.instagram.com/stories/example_user/ "
        "| 0 files | 0 | FAILED_FINAL |  |"
    ) in markdown
    assert "<br>- video.mp4<br>- cover.jpg" in markdown
    assert "<br>- working/example_user/reels<br>- working/example_user" in markdown


def test_markdown_report_builder_reads_sqlite_writes_file_and_updates_run(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    reports_folder = tmp_path / "reports"
    started_at = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    init_database(db_path)

    with connect(db_path) as connection:
        account_repo = AccountRepository(connection)
        run_repo = RunRepository(connection)
        url_job_repo = UrlJobRepository(connection)
        download_repo = DownloadRepository(connection)

        account = account_repo.create(
            Account(
                username="example_user",
                start_now_date=date(2026, 6, 4),
                download_stories=True,
                generated_story_url="https://www.instagram.com/stories/example_user/",
                working_folder=Path("working/example_user"),
                status=AccountStatus.COMPLETED,
            )
        )
        assert account.id is not None

        run = run_repo.create(
            RunSummary(
                status=RunStatus.COMPLETED,
                total_urls=2,
                completed_urls=2,
                downloaded_files=2,
            ),
            account_id=account.id,
            started_at=started_at,
        )

        story_job = url_job_repo.create(
            UrlJob(
                account_id=account.id,
                run_id=run.id,
                url="https://www.instagram.com/stories/example_user/",
                publication_type=PublicationType.STORY,
                source=UrlSource.GENERATED_STORY,
                status=UrlJobStatus.COMPLETED,
            )
        )
        reel_job = url_job_repo.create(
            UrlJob(
                account_id=account.id,
                run_id=run.id,
                url="https://www.instagram.com/reel/ABC123xyz/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.COMPLETED,
            )
        )
        assert story_job.id is not None
        assert reel_job.id is not None

        download_repo.create(
            DownloadFile(
                url_job_id=reel_job.id,
                original_path=Path("Telegram Desktop/video.mp4"),
                working_path=Path("working/example_user/reels/video.mp4"),
                media_type=MediaType.VIDEO,
                file_extension=".mp4",
                status=DownloadFileStatus.FINALIZED,
            )
        )
        download_repo.create(
            DownloadFile(
                url_job_id=reel_job.id,
                original_path=Path("Telegram Desktop/cover.jpg"),
                working_path=Path("working/example_user/cover.jpg"),
                media_type=MediaType.IMAGE,
                file_extension=".jpg",
                status=DownloadFileStatus.FINALIZED,
            )
        )

        report_path = MarkdownReportBuilder(connection).write(run.id, reports_folder)
        stored_run = run_repo.get_by_id(run.id)

    assert report_path == reports_folder / "run_20260615_120000.md"
    assert report_path.exists()
    assert stored_run is not None
    assert stored_run.report_path == report_path

    markdown = report_path.read_text(encoding="utf-8")
    assert "Fecha y hora de ejecucion: 2026-06-15T12:00:00+00:00" in markdown
    assert (
        "| example_user | Story | https://www.instagram.com/stories/example_user/ "
        "| 0 files | 0 | COMPLETED |  |"
    ) in markdown
    assert (
        "| example_user | Reel | https://www.instagram.com/reel/ABC123xyz/ "
        "| <br>- video.mp4<br>- cover.jpg | 2 | COMPLETED "
    ) in markdown
