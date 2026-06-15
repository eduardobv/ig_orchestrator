from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence

from ig_orchestrator import __version__
from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    DownloadRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.input.batch_importer import import_batch_json
from ig_orchestrator.orchestration import (
    AccountOrchestrator,
    AccountOrchestratorConfig,
    BatchOrchestrator,
    BatchOrchestratorConfig,
    UrlJobProcessorResult,
)
from ig_orchestrator.settings import SettingsError, load_settings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the minimal command surface available before the full CLI task."""

    parser = argparse.ArgumentParser(prog="ig_orchestrator")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    init_db_parser = subparsers.add_parser("init-db")
    init_db_parser.add_argument("--db-path", type=Path, default=None)

    args = parser.parse_args(argv)

    if args.command == "init-db":
        return _init_db(args.db_path)

    if args.input is not None:
        if args.dry_run:
            return _dry_run_batch(args.input)
        print("Processing a real batch is not wired in this minimal entrypoint yet.")
        print("Use --dry-run to validate the batch without Telegram or file moves.")
        return 2

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


class _DryRunUrlJobProcessor:
    async def process(self, url_job_id: int) -> UrlJobProcessorResult:
        raise RuntimeError(
            f"Dry-run should not call the real URL job processor: {url_job_id}"
        )


def _dry_run_batch(input_path: Path) -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Cannot run dry-run: {exc}")
        return 2

    init_database(settings.sqlite_db_path)
    connection = connect(settings.sqlite_db_path)
    try:
        imported = import_batch_json(input_path, connection, settings=settings)
        account_repository = AccountRepository(connection)
        url_job_repository = UrlJobRepository(connection)
        download_repository = DownloadRepository(connection)
        run_repository = RunRepository(connection)
        account_orchestrator = AccountOrchestrator(
            account_repository=account_repository,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            run_repository=run_repository,
            url_job_processor=_DryRunUrlJobProcessor(),
            config=AccountOrchestratorConfig(
                default_working_folder=settings.working_folder,
                max_retries=settings.max_retries,
                retry_base_seconds=settings.retry_base_seconds,
                retry_max_seconds=settings.retry_max_seconds,
                dry_run=True,
            ),
        )
        batch_orchestrator = BatchOrchestrator(
            batch_repository=BatchRepository(connection),
            account_repository=account_repository,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            run_repository=run_repository,
            account_orchestrator=account_orchestrator,
            config=BatchOrchestratorConfig(dry_run=True),
        )
        if imported.batch.id is None:
            raise RuntimeError("Imported batch has no id")
        result = asyncio.run(batch_orchestrator.process_batch(imported.batch.id))
    except Exception as exc:
        print(f"Dry-run failed: {exc}")
        return 1
    finally:
        connection.close()

    print(f"Dry-run batch: {result.batch.batch_name}")
    print(result.summary.summary)
    print(f"SQLite database: {settings.sqlite_db_path}")
    print("No Telegram messages were sent and no files were moved.")
    return 0
