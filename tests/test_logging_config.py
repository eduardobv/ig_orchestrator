from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ig_orchestrator.logging_config import (
    REDACTED,
    configure_account_run_logging,
    configure_app_logging,
    get_logger,
    logging_context,
)


def test_configure_app_logging_writes_app_log_and_redacts_secrets(
    tmp_path: Path,
) -> None:
    log_path = configure_app_logging(tmp_path / "logs", reset=True)

    get_logger().info("starting with api_hash=abc123 token:supersecret")
    with logging_context(account_username="example_user", account_log_key="account"):
        get_logger().info("account-only info")
        get_logger().warning("account warning password=hidden")

    content = log_path.read_text(encoding="utf-8")
    assert "starting with" in content
    assert "account-only info" not in content
    assert "account warning" in content
    assert f"api_hash={REDACTED}" in content
    assert f"token={REDACTED}" in content
    assert f"password={REDACTED}" in content
    assert "abc123" not in content
    assert "supersecret" not in content
    assert "hidden" not in content


def test_account_run_logging_writes_only_matching_context(tmp_path: Path) -> None:
    handle = configure_account_run_logging(
        username="example_user",
        run_id=7,
        started_at=datetime(2026, 6, 15, 12, 30, tzinfo=timezone.utc),
        logs_folder=tmp_path / "logs",
    )

    with logging_context(
        account_username="example_user",
        run_id=7,
        account_log_key=handle.account_log_key,
    ):
        get_logger().debug("File detected: {}", "image.jpg")
        get_logger().info("URL processed: {}", "https://www.instagram.com/reel/ABC/")

    with logging_context(account_username="other_user", run_id=8):
        get_logger().info("this should not enter the account log")

    handle.close()

    assert handle.path == (
        tmp_path / "logs" / "20260615_123000" / "example_user.log"
    )
    content = handle.path.read_text(encoding="utf-8")
    assert "account=example_user" in content
    assert "run=7" in content
    assert "File detected" in content
    assert "URL processed" in content
    assert "this should not enter" not in content


def test_multiple_account_logs_share_execution_folder_and_append(
    tmp_path: Path,
) -> None:
    execution_started_at = datetime(2026, 6, 21, 11, 15, 19, tzinfo=timezone.utc)

    first = configure_account_run_logging(
        username="same_user",
        run_id=10,
        started_at=execution_started_at,
        logs_folder=tmp_path / "logs",
    )
    with logging_context(
        account_username="same_user",
        run_id=10,
        account_log_key=first.account_log_key,
    ):
        get_logger().info("first account pass")
    first.close()

    second = configure_account_run_logging(
        username="same_user",
        run_id=11,
        started_at=execution_started_at,
        logs_folder=tmp_path / "logs",
    )
    with logging_context(
        account_username="same_user",
        run_id=11,
        account_log_key=second.account_log_key,
    ):
        get_logger().info("second account pass")
    second.close()

    execution_folders = [
        path for path in (tmp_path / "logs").iterdir() if path.is_dir()
    ]
    assert execution_folders == [tmp_path / "logs" / "20260621_111519"]
    assert first.path == second.path
    content = second.path.read_text(encoding="utf-8")
    assert "first account pass" in content
    assert "second account pass" in content
