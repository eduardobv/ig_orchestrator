from datetime import date
from pathlib import Path

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    DownloadRepository,
    UrlJobRepository,
    connect,
    init_gui_database,
)
from ig_orchestrator.db.downloaded_files_cleanup import (
    maybe_purge_downloaded_files_for_batch,
    purge_downloaded_files,
)
from ig_orchestrator.gui.batch_resume_service import finish_batch
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    DownloadFile,
    DownloadFileStatus,
    InputBatch,
    InputBatchStatus,
    MediaType,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)


def test_purge_downloaded_files_keeps_url_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        batch = BatchRepository(connection).create(
            InputBatch(
                batch_name="purge_batch",
                schema_version="1.0",
                status=InputBatchStatus.DRAFT,
            )
        )
        account = AccountRepository(connection).create(
            Account(
                batch_id=batch.id,
                username="purge_user",
                start_now_date=date.today(),
                download_stories=False,
                status=AccountStatus.PENDING,
            )
        )
        job = UrlJobRepository(connection).create(
            UrlJob(
                account_id=account.id,
                url="https://www.instagram.com/p/purge/",
                publication_type=PublicationType.POST,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.COMPLETED,
            )
        )
        DownloadRepository(connection).create(
            DownloadFile(
                url_job_id=job.id,
                original_path=tmp_path / "file.mp4",
                media_type=MediaType.VIDEO,
                file_extension=".mp4",
                status=DownloadFileStatus.DETECTED,
            )
        )
        deleted = purge_downloaded_files(connection, batch_id=batch.id)
        remaining_files = int(
            connection.execute("SELECT COUNT(*) FROM downloaded_files").fetchone()[0]
        )
        remaining_urls = int(
            connection.execute("SELECT COUNT(*) FROM batch_urls").fetchone()[0]
        )
        finish_batch(connection, batch.id)
        after_finish = int(
            connection.execute("SELECT COUNT(*) FROM downloaded_files").fetchone()[0]
        )

    assert deleted == 1
    assert remaining_files == 0
    assert remaining_urls == 1
    assert after_finish == 0


def test_keep_retention_skips_auto_purge(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE app_settings
            SET value = 'keep'
            WHERE key = 'retention.downloaded_files'
            """
        )
        connection.commit()
        assert maybe_purge_downloaded_files_for_batch(connection, 1) == 0
