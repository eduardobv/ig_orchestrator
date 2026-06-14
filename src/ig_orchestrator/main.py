from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from ig_orchestrator import __version__
from ig_orchestrator.db import init_database
from ig_orchestrator.settings import SettingsError, load_settings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the minimal command surface available before the full CLI task."""

    parser = argparse.ArgumentParser(prog="ig_orchestrator")
    subparsers = parser.add_subparsers(dest="command")
    init_db_parser = subparsers.add_parser("init-db")
    init_db_parser.add_argument("--db-path", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.command == "init-db":
        return _init_db(args.db_path)

    print(f"ig_orchestrator v{__version__}")
    print("Base project structure ready. Business logic is not implemented yet.")
    return 0


def _init_db(db_path: Path | None) -> int:
    if db_path is None:
        try:
            db_path = load_settings().sqlite_db_path
        except SettingsError as exc:
            print(f"Cannot initialize database: {exc}")
            return 2

    init_database(db_path)
    print(f"SQLite database ready: {db_path}")
    return 0
