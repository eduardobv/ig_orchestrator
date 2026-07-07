from __future__ import annotations

import subprocess
import sys


def build_run_continue_command(batch_id: int, *, dry_run: bool = False) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "ig_orchestrator",
        "run_continue",
        "--batch-id",
        str(batch_id),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


class ProcessRunner:
    """Small subprocess wrapper reserved for the execution GUI task."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


__all__ = ["ProcessRunner", "build_run_continue_command"]
