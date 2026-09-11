from pathlib import Path

from ig_orchestrator.orchestration import PostProcessConfig, PostProcessRunner


def test_post_process_runner_skips_when_disabled(tmp_path: Path) -> None:
    command = tmp_path / "unused.cmd"

    result = PostProcessRunner(
        PostProcessConfig(enabled=False, command=command)
    ).run()

    assert result.skipped is True
    assert result.success is True


def test_post_process_runner_requires_command_when_enabled() -> None:
    result = PostProcessRunner(PostProcessConfig(enabled=True)).run()

    assert result.skipped is False
    assert result.success is False
    assert "no command is configured" in result.error


def test_post_process_runner_runs_cmd_file_and_captures_output(tmp_path: Path) -> None:
    command = tmp_path / "post_process.cmd"
    command.write_text(
        "@echo off\n"
        "echo rename ok\n"
        "exit /b 0\n",
        encoding="utf-8",
    )

    result = PostProcessRunner(
        PostProcessConfig(enabled=True, command=command)
    ).run()

    assert result.skipped is False
    assert result.success is True
    assert result.exit_code == 0
    assert "rename ok" in result.stdout


def test_post_process_runner_reports_non_zero_exit_code(tmp_path: Path) -> None:
    command = tmp_path / "post_process.cmd"
    command.write_text(
        "@echo off\n"
        "echo rename failed 1>&2\n"
        "exit /b 7\n",
        encoding="utf-8",
    )

    result = PostProcessRunner(
        PostProcessConfig(enabled=True, command=command)
    ).run()

    assert result.success is False
    assert result.exit_code == 7
    assert "rename failed" in result.stderr
