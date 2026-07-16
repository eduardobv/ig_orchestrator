import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import ig_orchestrator
from ig_orchestrator import main as app_main
from ig_orchestrator.db import AccountRepository, BatchRepository, UrlJobRepository, connect, init_database
from ig_orchestrator.models import DownloadFile, DownloadFileStatus, MediaType, UrlJobStatus
from ig_orchestrator.models import Account, AccountStatus, InputBatch, InputBatchStatus, PublicationType, UrlJob, UrlSource
from ig_orchestrator.telegram import BotConversationResult


def test_package_imports() -> None:
    assert ig_orchestrator.__version__ == "1.26.1"


def test_module_entrypoint_runs() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")

    result = subprocess.run(
        [sys.executable, "-m", "ig_orchestrator"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert "ig_orchestrator v1.26.1" in result.stdout


def test_module_entrypoint_dry_run_imports_batch_without_telegram(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    input_path = tmp_path / "batch.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_name": "dry_run_batch",
                "defaults": {
                    "download_stories": False,
                    "start_now_date": "2026-06-14",
                },
                "accounts": [
                    {
                        "username": "example_user",
                        "urls": ["https://www.instagram.com/reel/ABC123xyz/"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(project_root / "src"),
            "TELEGRAM_API_ID": "12345",
            "TELEGRAM_API_HASH": "dummy_hash",
            "TELETHON_SESSION_NAME": "dummy_session",
            "TELEGRAM_DOWNLOAD_BOT_USERNAME": "@dummy_bot",
            "TELEGRAM_DESKTOP_DOWNLOAD_FOLDER": str(tmp_path / "telegram"),
            "WORKING_FOLDER": str(tmp_path / "working"),
            "REPORTS_FOLDER": str(tmp_path / "reports"),
            "SQLITE_DB_PATH": str(tmp_path / "orchestrator.db"),
            "MAX_RETRIES": "5",
            "RETRY_BASE_SECONDS": "90",
            "RETRY_MAX_SECONDS": "900",
            "DOWNLOAD_WAIT_TIMEOUT_SECONDS": "300",
            "DOWNLOAD_STABLE_SECONDS": "10",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "ig_orchestrator", "--input", str(input_path), "--dry-run"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert "Dry-run batch: dry_run_batch" in result.stdout
    assert "No Telegram messages were sent and no files were moved." in result.stdout
    assert not (tmp_path / "working" / "example_user").exists()


def test_main_real_run_processes_batch_with_telegram_service(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "batch.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_name": "real_run_batch",
                "defaults": {
                    "download_stories": False,
                    "start_now_date": "2026-06-16",
                },
                "accounts": [
                    {
                        "username": "real_user",
                        "urls": [
                            "https://www.instagram.com/p/DZnUzdJAtiV/?img_index=1"
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "dummy_hash")
    monkeypatch.setenv("TELETHON_SESSION_NAME", str(tmp_path / "dummy_session"))
    monkeypatch.setenv("TELEGRAM_DOWNLOAD_BOT_USERNAME", "@dummy_bot")
    monkeypatch.setenv("TELEGRAM_DESKTOP_DOWNLOAD_FOLDER", str(tmp_path / "telegram"))
    monkeypatch.setenv("WORKING_FOLDER", str(tmp_path / "working"))
    monkeypatch.setenv("REPORTS_FOLDER", str(tmp_path / "reports"))
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "orchestrator.db"))
    monkeypatch.setenv("MAX_RETRIES", "1")
    monkeypatch.setenv("RETRY_BASE_SECONDS", "1")
    monkeypatch.setenv("RETRY_MAX_SECONDS", "1")
    monkeypatch.setenv("DOWNLOAD_WAIT_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DOWNLOAD_STABLE_SECONDS", "0")
    monkeypatch.setenv("POST_PROCESS_ENABLED", "true")
    monkeypatch.setenv("POST_PROCESS_COMMAND", str(tmp_path / "MRF_auto.cmd"))
    post_process_calls = []

    class FakeTelegramClient:
        def __init__(self, _config):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

    class FakeBotConversationService:
        def __init__(self, **kwargs):
            self.url_job_repository = kwargs["url_job_repository"]
            self.download_repository = kwargs["download_repository"]
            self.download_folder = kwargs["config"].download_folder

        async def process_url_job(self, job):
            self.download_folder.mkdir(parents=True, exist_ok=True)
            downloaded_path = self.download_folder / f"downloaded_{job.id}.jpg"
            downloaded_path.write_bytes(b"fake image")
            stored_file = self.download_repository.create(
                DownloadFile(
                    url_job_id=job.id,
                    original_path=downloaded_path,
                    media_type=MediaType.IMAGE,
                    file_extension=".jpg",
                    file_size=downloaded_path.stat().st_size,
                    status=DownloadFileStatus.DETECTED,
                )
            )
            updated_job = self.url_job_repository.update_status(
                job.id,
                UrlJobStatus.DOWNLOADED,
                finished_at=datetime.now(timezone.utc),
            )
            return BotConversationResult(job=updated_job, files=(stored_file,))

    class FakePostProcessRunner:
        def __init__(self, config):
            self.config = config

        def run(self):
            post_process_calls.append(self.config.command)
            assert list((tmp_path / "reports").glob("run_*.md"))
            return app_main.PostProcessResult(
                skipped=False,
                success=True,
                command=self.config.command,
                exit_code=0,
            )

    monkeypatch.setattr(app_main, "TelethonTelegramClient", FakeTelegramClient)
    monkeypatch.setattr(app_main, "BotConversationService", FakeBotConversationService)
    monkeypatch.setattr(app_main, "PostProcessRunner", FakePostProcessRunner)

    exit_code = app_main.main(["--input", str(input_path), "--run"])

    assert exit_code == 0
    assert (tmp_path / "working" / "real_user" / "downloaded_1.jpg").is_file()
    assert list((tmp_path / "reports").glob("run_*.md"))
    assert post_process_calls == [tmp_path / "MRF_auto.cmd"]


def test_run_continue_processes_sqlite_batch_without_importing_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        batch = BatchRepository(connection).create(
            InputBatch(
                batch_name="continue_batch",
                schema_version="1.0",
                status=InputBatchStatus.PROCESSING,
            )
        )
        account = AccountRepository(connection).create(
            Account(
                batch_id=batch.id,
                username="continue_user",
                start_now_date=datetime(2026, 6, 16, tzinfo=timezone.utc).date(),
                download_stories=False,
                working_folder=tmp_path / "working" / "continue_user",
                status=AccountStatus.PROCESSING,
            )
        )
        UrlJobRepository(connection).create(
            UrlJob(
                account_id=account.id,
                url="https://www.instagram.com/reel/ABC123xyz/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.WAITING_DOWNLOAD,
                max_retries=1,
            )
        )

    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "dummy_hash")
    monkeypatch.setenv("TELETHON_SESSION_NAME", str(tmp_path / "dummy_session"))
    monkeypatch.setenv("TELEGRAM_DOWNLOAD_BOT_USERNAME", "@dummy_bot")
    monkeypatch.setenv("TELEGRAM_DESKTOP_DOWNLOAD_FOLDER", str(tmp_path / "telegram"))
    monkeypatch.setenv("WORKING_FOLDER", str(tmp_path / "working"))
    monkeypatch.setenv("REPORTS_FOLDER", str(tmp_path / "reports"))
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("MAX_RETRIES", "1")
    monkeypatch.setenv("RETRY_BASE_SECONDS", "1")
    monkeypatch.setenv("RETRY_MAX_SECONDS", "1")
    monkeypatch.setenv("DOWNLOAD_WAIT_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DOWNLOAD_STABLE_SECONDS", "0")

    class FakeTelegramClient:
        def __init__(self, _config):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

    class FakeBotConversationService:
        def __init__(self, **kwargs):
            self.url_job_repository = kwargs["url_job_repository"]
            self.download_repository = kwargs["download_repository"]
            self.download_folder = kwargs["config"].download_folder

        async def process_url_job(self, job):
            self.download_folder.mkdir(parents=True, exist_ok=True)
            downloaded_path = self.download_folder / f"continued_{job.id}.mp4"
            downloaded_path.write_bytes(b"fake video")
            stored_file = self.download_repository.create(
                DownloadFile(
                    url_job_id=job.id,
                    original_path=downloaded_path,
                    media_type=MediaType.VIDEO,
                    file_extension=".mp4",
                    file_size=downloaded_path.stat().st_size,
                    status=DownloadFileStatus.DETECTED,
                )
            )
            updated_job = self.url_job_repository.update_status(
                job.id,
                UrlJobStatus.DOWNLOADED,
                finished_at=datetime.now(timezone.utc),
            )
            return BotConversationResult(job=updated_job, files=(stored_file,))

    monkeypatch.setattr(app_main, "TelethonTelegramClient", FakeTelegramClient)
    monkeypatch.setattr(app_main, "BotConversationService", FakeBotConversationService)

    exit_code = app_main.main(["run_continue"])

    assert exit_code == 0
    assert (tmp_path / "working" / "continue_user" / "reels" / "continued_1.mp4").is_file()
    assert list((tmp_path / "reports").glob("run_*.md"))
