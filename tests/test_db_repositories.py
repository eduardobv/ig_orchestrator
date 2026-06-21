from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
import pytest

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    ConfigRepository,
    DownloadRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.main import main
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    AppConfig,
    ConfigValueType,
    DownloadFile,
    DownloadFileStatus,
    InputBatch,
    InputBatchStatus,
    MediaType,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)


def test_init_database_is_idempotent_and_repositories_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"

    init_database(db_path)
    init_database(db_path)

    with connect(db_path) as connection:
        config_repo = ConfigRepository(connection)
        batch_repo = BatchRepository(connection)
        account_repo = AccountRepository(connection)
        run_repo = RunRepository(connection)
        url_job_repo = UrlJobRepository(connection)
        download_repo = DownloadRepository(connection)

        config = config_repo.upsert(
            AppConfig(
                key="max_retries",
                value="5",
                value_type=ConfigValueType.INTEGER,
            )
        )
        assert config_repo.get("max_retries") == config

        batch = batch_repo.create(
            InputBatch(
                batch_name="descargas_junio_2026",
                schema_version="1.0",
                source_file=Path("config/batch.example.json"),
                status=InputBatchStatus.IMPORTED,
            )
        )
        assert batch.id is not None

        account = account_repo.create(
            Account(
                batch_id=batch.id,
                username="example_user",
                start_now_date=date(2026, 6, 4),
                download_stories=True,
                generated_story_url="https://www.instagram.com/stories/example_user/",
                working_folder=Path("working/example_user"),
                status=AccountStatus.PENDING,
            )
        )
        assert account.id is not None

        run = run_repo.create(
            RunSummary(status=RunStatus.PROCESSING, total_urls=1),
            batch_id=batch.id,
            account_id=account.id,
        )

        job = url_job_repo.create(
            UrlJob(
                account_id=account.id,
                run_id=run.id,
                url="https://www.instagram.com/reel/ABC123xyz/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.PENDING,
                max_retries=5,
            )
        )
        assert job.id is not None

        download_file = download_repo.create(
            DownloadFile(
                url_job_id=job.id,
                original_path=Path("Telegram Desktop/video.mp4"),
                working_path=Path("working/example_user/reels/video.mp4"),
                media_type=MediaType.VIDEO,
                file_extension=".mp4",
                file_size=2048,
                sha256="b" * 64,
                status=DownloadFileStatus.DETECTED,
            )
        )

        updated_batch = batch_repo.update_status(batch.id, InputBatchStatus.PROCESSING)
        updated_account = account_repo.update_status(
            account.id, AccountStatus.PROCESSING
        )
        updated_job = url_job_repo.update_status(
            job.id,
            UrlJobStatus.COMPLETED,
            finished_at=datetime.now(timezone.utc),
        )
        updated_file = download_repo.update_status(
            download_file.id, DownloadFileStatus.FINALIZED
        )
        updated_run = run_repo.update_summary(
            run.id,
            RunSummary(
                status=RunStatus.COMPLETED,
                total_urls=1,
                completed_urls=1,
                downloaded_files=1,
            ),
            report_path=Path("reports/run.md"),
            finished_at=datetime.now(timezone.utc),
        )

        assert updated_batch.status == InputBatchStatus.PROCESSING
        assert updated_account.status == AccountStatus.PROCESSING
        assert updated_job.status == UrlJobStatus.COMPLETED
        assert updated_file.status == DownloadFileStatus.FINALIZED
        assert updated_run.status == RunStatus.COMPLETED
        assert updated_run.report_path == Path("reports/run.md")

        assert batch_repo.list_by_status(InputBatchStatus.PROCESSING) == [
            updated_batch
        ]
        assert account_repo.list_by_status(AccountStatus.PROCESSING) == [
            updated_account
        ]
        assert url_job_repo.list_by_status(UrlJobStatus.COMPLETED) == [updated_job]
        assert download_repo.list_by_status(DownloadFileStatus.FINALIZED) == [
            updated_file
        ]
        assert run_repo.list_by_status(RunStatus.COMPLETED) == [updated_run]
        assert account_repo.list_by_batch(batch.id) == [updated_account]
        assert url_job_repo.list_by_account(account.id) == [updated_job]
        assert download_repo.list_by_url_job(job.id) == [updated_file]


def test_init_db_command_creates_schema_with_explicit_path(tmp_path: Path) -> None:
    db_path = tmp_path / "cli.db"

    exit_code = main(["init-db", "--db-path", str(db_path)])

    assert exit_code == 0
    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "app_config",
        "input_batches",
        "accounts",
        "account_history",
        "url_jobs",
        "duplicate_url_jobs",
        "download_files",
        "runs",
    }.issubset(table_names)


def test_init_database_adds_duplicate_url_jobs_table_to_existing_db(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE app_config (key TEXT PRIMARY KEY)")
        connection.commit()

    init_database(db_path)

    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "duplicate_url_jobs" in table_names


def test_batch_repository_lists_batches_with_resumable_work(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        batch_repo = BatchRepository(connection)
        account_repo = AccountRepository(connection)
        url_job_repo = UrlJobRepository(connection)

        resumable_batch = batch_repo.create(
            InputBatch(
                batch_name="resumable",
                schema_version="1.0",
                status=InputBatchStatus.PROCESSING,
            )
        )
        resumable_account = account_repo.create(
            Account(
                batch_id=resumable_batch.id,
                username="resumable_user",
                start_now_date=date(2026, 6, 16),
                download_stories=False,
                status=AccountStatus.PROCESSING,
            )
        )
        url_job_repo.create(
            UrlJob(
                account_id=resumable_account.id,
                url="https://www.instagram.com/reel/ABC123xyz/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.WAITING_DOWNLOAD,
            )
        )

        completed_batch = batch_repo.create(
            InputBatch(
                batch_name="completed",
                schema_version="1.0",
                status=InputBatchStatus.COMPLETED,
            )
        )
        completed_account = account_repo.create(
            Account(
                batch_id=completed_batch.id,
                username="completed_user",
                start_now_date=date(2026, 6, 16),
                download_stories=False,
                status=AccountStatus.COMPLETED,
            )
        )
        url_job_repo.create(
            UrlJob(
                account_id=completed_account.id,
                url="https://www.instagram.com/reel/XYZ123xyz/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.COMPLETED,
            )
        )

        assert batch_repo.list_with_resumable_work() == [resumable_batch]


def test_input_batch_name_is_unique_in_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        repo = BatchRepository(connection)
        repo.create(
            InputBatch(
                batch_name="unique_batch",
                schema_version="1.0",
                status=InputBatchStatus.IMPORTED,
            )
        )

        with pytest.raises(sqlite3.IntegrityError):
            repo.create(
                InputBatch(
                    batch_name="unique_batch",
                    schema_version="1.0",
                    status=InputBatchStatus.IMPORTED,
                )
            )
