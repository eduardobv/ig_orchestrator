import os
import subprocess
import sys
from pathlib import Path

import ig_orchestrator


def test_package_imports() -> None:
    assert ig_orchestrator.__version__ == "1.2.0"


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

    assert "ig_orchestrator v1.2.0" in result.stdout
