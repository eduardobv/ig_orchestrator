import json
import os
import subprocess
import sys
from pathlib import Path

import ig_orchestrator


def test_package_imports() -> None:
    assert ig_orchestrator.__version__ == "1.21.0"


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

    assert "ig_orchestrator v1.21.0" in result.stdout


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
