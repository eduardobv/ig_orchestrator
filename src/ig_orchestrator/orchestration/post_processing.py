from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ig_orchestrator.logging_config import get_logger


logger = get_logger()


@dataclass(frozen=True, slots=True)
class PostProcessConfig:
    enabled: bool = False
    command: Path | None = None


@dataclass(frozen=True, slots=True)
class PostProcessResult:
    skipped: bool
    success: bool
    command: Path | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class PostProcessRunner:
    """Run a configured post-processing command after reports are written."""

    def __init__(self, config: PostProcessConfig) -> None:
        self._config = config

    def run(self) -> PostProcessResult:
        if not self._config.enabled:
            return PostProcessResult(skipped=True, success=True)
        if self._config.command is None:
            return PostProcessResult(
                skipped=False,
                success=False,
                error="Post-processing is enabled but no command is configured.",
            )

        command = self._config.command
        if not command.exists():
            message = f"Post-processing command not found: {command}"
            logger.error(message)
            return PostProcessResult(
                skipped=False,
                success=False,
                command=command,
                error=message,
            )
        if not command.is_file():
            message = f"Post-processing command is not a file: {command}"
            logger.error(message)
            return PostProcessResult(
                skipped=False,
                success=False,
                command=command,
                error=message,
            )

        args = _process_args(command)
        logger.info("Manual rename post-processing starting: command={}", command)
        try:
            completed = subprocess.run(
                args,
                cwd=command.parent,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except OSError as exc:
            message = f"Post-processing command could not be executed: {exc}"
            logger.error(message)
            return PostProcessResult(
                skipped=False,
                success=False,
                command=command,
                error=message,
            )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if stdout:
            logger.info("Manual rename post-processing stdout: {}", stdout)
        if stderr:
            logger.warning("Manual rename post-processing stderr: {}", stderr)

        success = completed.returncode == 0
        if success:
            logger.info(
                "Manual rename post-processing finished successfully: command={}",
                command,
            )
        else:
            logger.error(
                "Manual rename post-processing failed: command={} exit_code={}",
                command,
                completed.returncode,
            )
        return PostProcessResult(
            skipped=False,
            success=success,
            command=command,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )


def _process_args(command: Path) -> list[str]:
    if command.suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/c", str(command)]
    return [str(command)]


__all__ = [
    "PostProcessConfig",
    "PostProcessResult",
    "PostProcessRunner",
]
