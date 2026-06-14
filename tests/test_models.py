from datetime import date
from pathlib import Path

import pytest

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


def test_create_core_domain_models() -> None:
    batch = InputBatch(
        batch_name="descargas_junio_2026",
        schema_version="1.0",
        status=InputBatchStatus.IMPORTED,
        source_file=Path("config/batch.example.json"),
    )
    account = Account(
        batch_id=1,
        username="example_user",
        start_now_date=date(2026, 6, 4),
        download_stories=True,
        generated_story_url="https://www.instagram.com/stories/example_user/",
        working_folder=Path(r"C:\Users\eduba\Downloads\DW\Telegram_Desktop"),
        status=AccountStatus.PENDING,
    )
    url_job = UrlJob(
        account_id=1,
        url="https://www.instagram.com/reel/ABC123xyz/",
        publication_type=PublicationType.REEL,
        source=UrlSource.INPUT_URL,
        status=UrlJobStatus.PENDING,
        max_retries=5,
    )
    download_file = DownloadFile(
        url_job_id=1,
        original_path=Path("video.mp4"),
        media_type=MediaType.VIDEO,
        file_extension=".mp4",
        status=DownloadFileStatus.DETECTED,
        file_size=1024,
        sha256="a" * 64,
    )
    config = AppConfig(
        key="max_retries",
        value="5",
        value_type=ConfigValueType.INTEGER,
    )
    run_summary = RunSummary(
        status=RunStatus.PARTIAL,
        total_urls=3,
        completed_urls=2,
        failed_urls=1,
        downloaded_files=4,
    )

    assert batch.status == InputBatchStatus.IMPORTED
    assert account.download_stories is True
    assert url_job.publication_type == PublicationType.REEL
    assert download_file.media_type == MediaType.VIDEO
    assert config.value_type == ConfigValueType.INTEGER
    assert run_summary.failed_urls == 1


def test_model_enums_expose_plan_values() -> None:
    assert {item.value for item in PublicationType} == {
        "POST",
        "REEL",
        "STORY",
        "HIGHLIGHTS",
        "UNKNOWN",
    }
    assert {item.value for item in UrlSource} == {"GENERATED_STORY", "INPUT_URL"}
    assert "RETRY_PENDING" in {item.value for item in UrlJobStatus}
    assert "CLASSIFIED_AS_HIGHLIGHTS" in {
        item.value for item in DownloadFileStatus
    }


def test_blank_required_text_is_rejected() -> None:
    with pytest.raises(ValueError, match="username"):
        Account(
            username=" ",
            start_now_date=date(2026, 6, 4),
            download_stories=False,
            status=AccountStatus.PENDING,
        )


def test_negative_counters_are_rejected() -> None:
    with pytest.raises(ValueError, match="retries"):
        UrlJob(
            account_id=1,
            url="https://www.instagram.com/p/XYZ789abc/",
            publication_type=PublicationType.POST,
            source=UrlSource.INPUT_URL,
            status=UrlJobStatus.PENDING,
            retries=-1,
        )

    with pytest.raises(ValueError, match="failed_urls"):
        RunSummary(status=RunStatus.FAILED, total_urls=1, failed_urls=-1)


def test_download_file_validates_extension_and_sha256() -> None:
    with pytest.raises(ValueError, match="file_extension"):
        DownloadFile(
            url_job_id=1,
            original_path=Path("image"),
            media_type=MediaType.IMAGE,
            file_extension="jpg",
            status=DownloadFileStatus.DETECTED,
        )

    with pytest.raises(ValueError, match="sha256"):
        DownloadFile(
            url_job_id=1,
            original_path=Path("image.jpg"),
            media_type=MediaType.IMAGE,
            file_extension=".jpg",
            status=DownloadFileStatus.DETECTED,
            sha256="bad",
        )
