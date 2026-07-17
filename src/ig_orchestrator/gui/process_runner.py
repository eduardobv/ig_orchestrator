from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Thread


MANUAL_RENAME_SCRIPT = Path(r"D:\Archivos\Scripts\IG\ManualRenameFiles\main.py")


@dataclass(frozen=True, slots=True)
class NewAccountRenameParameters:
    username: str
    owner_id: str
    start_init_date: str
    destination_path: str


def build_run_continue_command(batch_id: int, *, dry_run: bool = False) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "ig_orchestrator",
    ]
    if dry_run:
        command.append("--dry-run")
    command.extend(["run_continue", "--batch-id", str(batch_id)])
    return command


def build_manual_rename_command(
    start_now_date: str,
    *,
    new_accounts: tuple[NewAccountRenameParameters, ...] = (),
    script_path: Path = MANUAL_RENAME_SCRIPT,
) -> list[str]:
    """Build the external manual-renamer command for a completed GUI batch."""
    command = [
        sys.executable,
        str(script_path),
        "--newRename",
        "--startNowDate",
        start_now_date,
    ]
    for account in new_accounts:
        command.extend(
            [
                "--new-account",
                account.username,
                account.owner_id,
                account.start_init_date,
                account.destination_path,
            ]
        )
    command.extend(["--no-duplicated", "--move-renamed"])
    return command


class ProcessRunner:
    """Run ``run_continue`` without blocking Tkinter and stream its output."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(
        self,
        command: list[str],
        *,
        on_output: Callable[[str], None],
        on_complete: Callable[[int], None],
    ) -> None:
        if self.is_running():
            raise RuntimeError("A GUI process is already running")

        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["IG_ORCHESTRATOR_GUI_PROGRESS"] = "1"
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
        )

        def consume_output() -> None:
            process = self.process
            if process is None:
                return
            if process.stdout is not None:
                for line in process.stdout:
                    on_output(line)
            exit_code = process.wait()
            self.process = None
            on_complete(exit_code)

        Thread(target=consume_output, name="gui-run-continue", daemon=True).start()

    def cancel(self) -> bool:
        if not self.is_running() or self.process is None:
            return False
        self.process.terminate()
        return True


__all__ = [
    "MANUAL_RENAME_SCRIPT",
    "NewAccountRenameParameters",
    "ProcessRunner",
    "build_manual_rename_command",
    "build_run_continue_command",
]
