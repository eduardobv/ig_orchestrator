from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
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
from ig_orchestrator.input import (
    DuplicateBatchNameError,
    backup_and_clean_batch_json,
    import_parsed_batch,
    parse_batch_json,
)
from ig_orchestrator.logging_config import configure_app_logging
from ig_orchestrator.orchestration import (
    AccountOrchestrator,
    AccountOrchestratorConfig,
    BatchOrchestrator,
    BatchOrchestratorConfig,
    UrlJobProcessor,
    UrlJobProcessorConfig,
    UrlJobProcessorResult,
)
from ig_orchestrator.reports import MarkdownReportBuilder
from ig_orchestrator.settings import SettingsError, load_settings
from ig_orchestrator.telegram import (
    BotConversationConfig,
    BotConversationService,
    TelegramClientConfig,
    TelegramClientError,
    TelethonTelegramClient,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the minimal command surface available before the full CLI task."""

    parser = argparse.ArgumentParser(prog="ig_orchestrator")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Process the input batch for real. This is the default when --input is used without --dry-run.",
    )
    join_group = parser.add_mutually_exclusive_group()
    join_group.add_argument(
        "--join-after-pending-batch-id",
        type=int,
        default=None,
        metavar="BATCH_ID",
        help="Resume BATCH_ID first, then process the new input batch.",
    )
    join_group.add_argument(
        "--join-before-pending-batch-id",
        type=int,
        default=None,
        metavar="BATCH_ID",
        help="Process the new input batch first, then resume BATCH_ID.",
    )
    subparsers = parser.add_subparsers(dest="command")
    init_db_parser = subparsers.add_parser("init-db")
    init_db_parser.add_argument("--db-path", type=Path, default=None)
    run_continue_parser = subparsers.add_parser(
        "run_continue",
        help="Continue resumable work from SQLite without importing batch.json.",
    )
    run_continue_parser.add_argument("--batch-id", type=int, default=None)
    run_continue_parser.add_argument("--batch-name", type=str, default=None)

    args = parser.parse_args(argv)

    join_requested = (
        args.join_after_pending_batch_id is not None
        or args.join_before_pending_batch_id is not None
    )
    if join_requested and args.input is None:
        parser.error("join options require --input with a new batch JSON")
    if join_requested and args.dry_run:
        parser.error("join options are only available for real --run executions")

    if args.command == "init-db":
        return _init_db(args.db_path)
    if args.command == "run_continue":
        return _run_continue(
            batch_id=args.batch_id,
            batch_name=args.batch_name,
        )

    if args.input is not None:
        if args.dry_run:
            return _dry_run_batch(args.input)
        return _run_batch(
            args.input,
            join_after_pending_batch_id=args.join_after_pending_batch_id,
            join_before_pending_batch_id=args.join_before_pending_batch_id,
        )

    print(f"ig_orchestrator v{__version__}")
    print("Use --help to see the available run and continuation modes.")
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
    execution_started_at = datetime.now(timezone.utc)
    configure_app_logging()
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
                execution_started_at=execution_started_at,
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


def _run_batch(
    input_path: Path,
    *,
    join_after_pending_batch_id: int | None = None,
    join_before_pending_batch_id: int | None = None,
) -> int:
    execution_started_at = datetime.now(timezone.utc)
    configure_app_logging()
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Cannot run batch: {exc}")
        return 2

    init_database(settings.sqlite_db_path)
    connection = connect(settings.sqlite_db_path)
    report_paths: list[Path] = []
    telegram_client = TelethonTelegramClient(
        TelegramClientConfig.from_settings(settings)
    )

    try:
        batch_repository = BatchRepository(connection)
        requested_pending_batch_id = (
            join_after_pending_batch_id
            if join_after_pending_batch_id is not None
            else join_before_pending_batch_id
        )
        if requested_pending_batch_id is not None:
            _validate_pending_batch(batch_repository, requested_pending_batch_id)

        parsed_batch = parse_batch_json(input_path)
        imported = import_parsed_batch(parsed_batch, connection, settings=settings)
        finalized_input = backup_and_clean_batch_json(parsed_batch)
        _print_ignored_accounts(parsed_batch)
        print(f"Batch imported: {imported.batch.batch_name} (id={imported.batch.id})")
        print(f"Batch backup: {finalized_input.backup_path}")
        print(f"Input JSON cleaned: {finalized_input.input_path}")

        account_repository = AccountRepository(connection)
        url_job_repository = UrlJobRepository(connection)
        download_repository = DownloadRepository(connection)
        run_repository = RunRepository(connection)

        conversation_service = BotConversationService(
            telegram_client=telegram_client,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            config=BotConversationConfig(
                download_folder=settings.telegram_desktop_download_folder,
                download_wait_timeout_seconds=settings.download_wait_timeout_seconds,
                download_stable_seconds=settings.download_stable_seconds,
            ),
        )
        url_job_processor = UrlJobProcessor(
            url_job_repository=url_job_repository,
            account_repository=account_repository,
            download_repository=download_repository,
            conversation_service=conversation_service,
            config=UrlJobProcessorConfig(
                default_working_folder=settings.working_folder,
            ),
        )
        account_orchestrator = AccountOrchestrator(
            account_repository=account_repository,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            run_repository=run_repository,
            url_job_processor=url_job_processor,
            config=AccountOrchestratorConfig(
                default_working_folder=settings.working_folder,
                execution_started_at=execution_started_at,
                max_retries=settings.max_retries,
                retry_base_seconds=settings.retry_base_seconds,
                retry_max_seconds=settings.retry_max_seconds,
                wait_between_retries=True,
            ),
        )
        batch_orchestrator = BatchOrchestrator(
            batch_repository=BatchRepository(connection),
            account_repository=account_repository,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            run_repository=run_repository,
            account_orchestrator=account_orchestrator,
            config=BatchOrchestratorConfig(
                progress_callback=_print_account_progress,
            ),
        )
        if imported.batch.id is None:
            raise RuntimeError("Imported batch has no id")

        batch_ids = _joined_batch_ids(
            batch_repository=batch_repository,
            new_batch_id=imported.batch.id,
            join_after_pending_batch_id=join_after_pending_batch_id,
            join_before_pending_batch_id=join_before_pending_batch_id,
        )

        async def _process():
            results = []
            async with telegram_client:
                for batch_id in batch_ids:
                    results.append(await batch_orchestrator.process_batch(batch_id))
            return results

        results = asyncio.run(_process())
        report_builder = MarkdownReportBuilder(connection)
        for result in results:
            if result.run.id is not None:
                report_paths.append(
                    report_builder.write(result.run.id, settings.reports_folder)
                )
    except DuplicateBatchNameError as exc:
        print(f"Batch not imported: {exc}")
        return 2
    except TelegramClientError as exc:
        print(f"Telegram client failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Batch failed: {exc}")
        return 1
    finally:
        connection.close()

    print(f"Processed {len(results)} batch(es).")
    for result in results:
        print(f"- {result.batch.batch_name}: {result.summary.summary}")
    print(f"SQLite database: {settings.sqlite_db_path}")
    for report_path in report_paths:
        print(f"Markdown report: {report_path}")
    return 1 if any(result.error for result in results) else 0


def _run_continue(
    *,
    batch_id: int | None = None,
    batch_name: str | None = None,
) -> int:
    execution_started_at = datetime.now(timezone.utc)
    configure_app_logging()
    if batch_id is not None and batch_name is not None:
        print("Cannot continue: use only one of --batch-id or --batch-name.")
        return 2

    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Cannot continue run: {exc}")
        return 2

    init_database(settings.sqlite_db_path)
    connection = connect(settings.sqlite_db_path)
    telegram_client = TelethonTelegramClient(
        TelegramClientConfig.from_settings(settings)
    )
    report_paths: list[Path] = []

    try:
        account_repository = AccountRepository(connection)
        url_job_repository = UrlJobRepository(connection)
        download_repository = DownloadRepository(connection)
        run_repository = RunRepository(connection)
        batch_repository = BatchRepository(connection)

        batches = _select_continue_batches(
            batch_repository=batch_repository,
            batch_id=batch_id,
            batch_name=batch_name,
        )
        if not batches:
            print("No resumable batches found in SQLite.")
            return 0

        conversation_service = BotConversationService(
            telegram_client=telegram_client,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            config=BotConversationConfig(
                download_folder=settings.telegram_desktop_download_folder,
                download_wait_timeout_seconds=settings.download_wait_timeout_seconds,
                download_stable_seconds=settings.download_stable_seconds,
            ),
        )
        url_job_processor = UrlJobProcessor(
            url_job_repository=url_job_repository,
            account_repository=account_repository,
            download_repository=download_repository,
            conversation_service=conversation_service,
            config=UrlJobProcessorConfig(
                default_working_folder=settings.working_folder,
            ),
        )
        account_orchestrator = AccountOrchestrator(
            account_repository=account_repository,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            run_repository=run_repository,
            url_job_processor=url_job_processor,
            config=AccountOrchestratorConfig(
                default_working_folder=settings.working_folder,
                execution_started_at=execution_started_at,
                max_retries=settings.max_retries,
                retry_base_seconds=settings.retry_base_seconds,
                retry_max_seconds=settings.retry_max_seconds,
                wait_between_retries=True,
            ),
        )
        batch_orchestrator = BatchOrchestrator(
            batch_repository=batch_repository,
            account_repository=account_repository,
            url_job_repository=url_job_repository,
            download_repository=download_repository,
            run_repository=run_repository,
            account_orchestrator=account_orchestrator,
            config=BatchOrchestratorConfig(
                progress_callback=_print_account_progress,
            ),
        )

        async def _process_all():
            results = []
            async with telegram_client:
                for batch in batches:
                    if batch.id is None:
                        continue
                    results.append(await batch_orchestrator.process_batch(batch.id))
            return results

        results = asyncio.run(_process_all())
        report_builder = MarkdownReportBuilder(connection)
        for result in results:
            if result.run.id is not None:
                report_paths.append(
                    report_builder.write(result.run.id, settings.reports_folder)
                )
    except TelegramClientError as exc:
        print(f"Telegram client failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Run continue failed: {exc}")
        return 1
    finally:
        connection.close()

    print(f"Run continue processed {len(results)} batch(es).")
    for result in results:
        print(f"- {result.batch.batch_name}: {result.summary.summary}")
    print(f"SQLite database: {settings.sqlite_db_path}")
    for report_path in report_paths:
        print(f"Markdown report: {report_path}")
    return 1 if any(result.error for result in results) else 0


def _select_continue_batches(
    *,
    batch_repository: BatchRepository,
    batch_id: int | None,
    batch_name: str | None,
):
    if batch_id is not None:
        batch = batch_repository.get_by_id(batch_id)
        if batch is None:
            raise ValueError(f"Input batch not found: {batch_id}")
        return [batch]
    if batch_name is not None:
        batch = batch_repository.get_by_name(batch_name)
        if batch is None:
            raise ValueError(f"Input batch not found: {batch_name}")
        return [batch]
    return batch_repository.list_with_resumable_work()


def _joined_batch_ids(
    *,
    batch_repository: BatchRepository,
    new_batch_id: int,
    join_after_pending_batch_id: int | None,
    join_before_pending_batch_id: int | None,
) -> list[int]:
    pending_batch_id = (
        join_after_pending_batch_id
        if join_after_pending_batch_id is not None
        else join_before_pending_batch_id
    )
    if pending_batch_id is None:
        return [new_batch_id]
    if pending_batch_id == new_batch_id:
        raise ValueError("The pending batch and new batch must be different")
    _validate_pending_batch(batch_repository, pending_batch_id)
    if join_after_pending_batch_id is not None:
        return [pending_batch_id, new_batch_id]
    return [new_batch_id, pending_batch_id]


def _validate_pending_batch(
    batch_repository: BatchRepository,
    pending_batch_id: int,
) -> None:
    if pending_batch_id <= 0:
        raise ValueError("Pending batch id must be positive")
    pending_batch = batch_repository.get_by_id(pending_batch_id)
    if pending_batch is None:
        raise ValueError(f"Pending input batch not found: {pending_batch_id}")
    if not batch_repository.has_resumable_work(pending_batch_id):
        raise ValueError(f"Batch {pending_batch_id} has no resumable pending work")


def _print_ignored_accounts(parsed_batch) -> None:
    for ignored in parsed_batch.ignored_accounts:
        username = ignored.username or "<blank username>"
        print(
            f"Ignored account #{ignored.account_index} ({username}): "
            f"{ignored.reason}."
        )


def _print_account_progress(current: int, total: int, account) -> None:
    percentage = int((current / total) * 100) if total else 100
    print(
        f"[{current}/{total} | {percentage:3d}%] Processing account: "
        f"{account.username}"
    )
