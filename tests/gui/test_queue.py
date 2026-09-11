from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk

import pytest

from ig_orchestrator.db import (
    AccountHistoryRepository,
    AccountRepository,
    BatchRepository,
    RunRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.db.migrations import apply_migrations
from ig_orchestrator.gui.app import (
    _BATCH_COLUMNS,
    InstagramOrchestratorApp,
    _account_display_status,
    _batch_column_samples,
    _batch_mode_details,
    batch_username_matches_filter,
    catalog_focus_username,
    _catalog_entry_colors,
    _catalog_width_chars,
    filter_batch_accounts,
    _half_screen_geometry,
    _instagram_profile_url,
    _open_chrome_tab,
    _play_completion_sound,
    _set_ttk_enabled,
    _latest_executed_batch_name,
    _new_account_rename_parameters,
    _sort_accounts_by_username,
    stories_cell_text,
    _timestamp_console_text,
    _username_heading_title,
)
from ig_orchestrator.gui.account_catalog_service import (
    AccountCatalogEntry,
    AccountCatalogService,
    filter_catalog_entries,
    list_usernames_active_on_date,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import (
    BatchDraftValidationError,
    inspect_account_draft,
    normalize_url_lines,
    save_batch_draft,
    validate_batch_draft,
)
from ig_orchestrator.gui.batch_resume_service import (
    activate_draft_batch,
    complete_account_manually,
    delete_draft_batch,
    fail_account_manually,
    finish_batch,
    get_account_runtime_progress,
    is_batch_ready_for_rename,
    list_account_problem_urls,
    list_historical_batches,
    list_managed_batches,
    list_pending_batches,
    load_batch_draft,
    mark_batch_executed_elsewhere,
    mark_batch_interrupted,
    resolve_account_download_folder,
)
from ig_orchestrator.gui.batch_transfer_service import (
    BatchTransferError,
    export_batch_payload,
    import_batch_from_payload,
)
from ig_orchestrator.gui.process_runner import (
    NewAccountRenameParameters,
    build_manual_rename_command,
    build_run_continue_command,
    format_command_for_shell,
    format_manual_rename_command_preview,
)
from ig_orchestrator.gui.rename_folder_status import (
    decide_rename_completion,
    has_unmoved_account_folders,
    list_unmoved_account_folders,
)
from ig_orchestrator.input import DuplicateBatchNameError
from ig_orchestrator.models import (
    AccountHistoryStatus,
    AccountStatus,
    InputBatchStatus,
    PublicationType,
    RunStatus,
    RunSummary,
    UrlJobStatus,
    UrlSource,
)
from ig_orchestrator.settings import Settings

def _draft_with_name(name: str, username: str, *, new_account: bool = False) -> BatchDraft:
    return BatchDraft(
        batch_name=name,
        default_start_now_date="2026-08-15",
        accounts=[
            AccountDraft(
                username=username,
                urls=["https://www.instagram.com/reel/QUEUE1/"],
                is_new_account=new_account,
                owner_id="111" if new_account else "",
                start_init_date="2025-01-01" if new_account else "",
                destination_path=r"G:\4K Stogram\00.MODELS-A" if new_account else "",
            )
        ],
    )


def test_batch_queue_add_remove_and_reject_running_removal(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        BatchQueueError,
        QueueItemStatus,
        add_batches_to_open_queue,
        get_queue,
        remove_pending_item,
        start_or_resume_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("q1", "user_one"), connection)
        second = save_batch_draft(_draft_with_name("q2", "user_two"), connection)
        third = save_batch_draft(_draft_with_name("q3", "user_three"), connection)
        queue = add_batches_to_open_queue(
            connection,
            [first.batch.id, second.batch.id, third.batch.id],
        )
        assert [item.batch_id for item in queue.items] == [
            first.batch.id,
            second.batch.id,
            third.batch.id,
        ]
        start_or_resume_queue(connection, queue.id)
        running = get_queue(connection, queue.id).running_item
        assert running is not None
        with pytest.raises(BatchQueueError, match="se está ejecutando"):
            remove_pending_item(connection, running.id)
        pending_third = next(
            item for item in get_queue(connection, queue.id).items
            if item.batch_id == third.batch.id
        )
        updated = remove_pending_item(connection, pending_third.id)
        assert updated.items[-1].status == QueueItemStatus.REMOVED.value
        assert updated.pending_items[0].batch_id == second.batch.id


def test_batch_queue_advance_then_awaiting_rename_after_last_pending_removed(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueStatus,
        add_batches_to_open_queue,
        get_queue,
        mark_current_item_completed,
        remove_pending_item,
        start_or_resume_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("seq1", "alpha"), connection)
        second = save_batch_draft(_draft_with_name("seq2", "beta"), connection)
        third = save_batch_draft(_draft_with_name("seq3", "gamma"), connection)
        queue = add_batches_to_open_queue(
            connection,
            [first.batch.id, second.batch.id, third.batch.id],
        )
        start_or_resume_queue(connection, queue.id)
        next_item = mark_current_item_completed(connection, queue.id)
        assert next_item is not None
        assert next_item.batch_id == second.batch.id
        start_or_resume_queue(connection, queue.id)
        third_item = next(
            item for item in get_queue(connection, queue.id).items
            if item.batch_id == third.batch.id
        )
        remove_pending_item(connection, third_item.id)
        assert mark_current_item_completed(connection, queue.id) is None
        closed = get_queue(connection, queue.id)
        assert closed.status == QueueStatus.AWAITING_RENAME.value
        assert closed.rename_batch_ids == (first.batch.id, second.batch.id)


def test_collect_rename_parameters_merges_new_accounts_and_latest_date(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import collect_rename_parameters
    from ig_orchestrator.gui.process_runner import build_manual_rename_command

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    earlier = BatchDraft(
        batch_name="rename_a",
        default_start_now_date="2026-08-14",
        accounts=[
            AccountDraft(
                username="new_a",
                urls=["https://www.instagram.com/reel/A1/"],
                is_new_account=True,
                owner_id="10",
                start_init_date="2025-01-01",
                destination_path=r"G:\4K Stogram\00.MODELS-A",
            )
        ],
    )
    later = BatchDraft(
        batch_name="rename_b",
        default_start_now_date="2026-08-15",
        accounts=[
            AccountDraft(
                username="new_b",
                urls=["https://www.instagram.com/reel/B1/"],
                is_new_account=True,
                owner_id="20",
                start_init_date="2025-02-02",
                destination_path=r"G:\4K Stogram\00.MODELS-B",
            )
        ],
    )
    with connect(db_path) as connection:
        first = save_batch_draft(earlier, connection)
        second = save_batch_draft(later, connection)
        params = collect_rename_parameters(
            connection, [first.batch.id, second.batch.id]
        )

    assert params.start_now_date == "2026-08-15"
    assert params.has_mixed_dates is True
    assert [account.username for account in params.new_accounts] == ["new_a", "new_b"]
    command = build_manual_rename_command(
        params.start_now_date,
        new_accounts=params.new_accounts,
    )
    assert command.count("--new-account") == 2
    assert "--move-renamed" in command


def test_finish_queue_after_rename_respects_leftovers_decision(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueStatus,
        add_batches_to_open_queue,
        finish_queue_after_rename,
        get_queue,
        mark_current_item_completed,
        start_or_resume_queue,
    )
    from ig_orchestrator.gui.rename_folder_status import decide_rename_completion
    from ig_orchestrator.models import InputBatchStatus

    leftover = tmp_path / "still_here"
    leftover.mkdir()
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("fin1", "one"), connection)
        second = save_batch_draft(_draft_with_name("fin2", "two"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, second.batch.id]
        )
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)

        blocked = decide_rename_completion(
            exit_code=0, leftover_folders=[leftover]
        )
        assert blocked.mark_completed is False
        assert get_queue(connection, queue.id).status == QueueStatus.AWAITING_RENAME.value

        finish_queue_after_rename(connection, queue.id)
        assert get_queue(connection, queue.id).status == QueueStatus.COMPLETED.value
        assert (
            BatchRepository(connection).get_by_id(first.batch.id).status
            is InputBatchStatus.COMPLETED
        )
        assert (
            BatchRepository(connection).get_by_id(second.batch.id).status
            is InputBatchStatus.COMPLETED
        )


def test_removing_all_queue_items_cancels_zombie_sequence(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        QueueStatus,
        add_batches_to_open_queue,
        get_open_queue,
        get_queue,
        remove_queue_item,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("z1", "zeta_one"), connection)
        second = save_batch_draft(_draft_with_name("z2", "zeta_two"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, second.batch.id]
        )
        for item in list(queue.items):
            remove_queue_item(connection, item.id)
        closed = get_queue(connection, queue.id)
        assert closed.status == QueueStatus.CANCELLED.value
        assert all(
            item.status == QueueItemStatus.REMOVED.value for item in closed.items
        )
        assert get_open_queue(connection) is None


def test_completed_queue_items_can_be_removed_and_do_not_block_rename(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueStatus,
        add_batches_to_open_queue,
        collect_rename_parameters,
        get_open_queue,
        get_queue,
        mark_current_item_completed,
        remove_queue_item,
        start_or_resume_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("done1", "done_one"), connection)
        second = save_batch_draft(_draft_with_name("done2", "done_two"), connection)
        amber = save_batch_draft(_draft_with_name("amber", "amber_user"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, second.batch.id]
        )
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)
        start_or_resume_queue(connection, queue.id)
        mark_current_item_completed(connection, queue.id)
        waiting = get_queue(connection, queue.id)
        assert waiting.status == QueueStatus.AWAITING_RENAME.value
        for item in waiting.items:
            remove_queue_item(connection, item.id)
        assert get_queue(connection, queue.id).status == QueueStatus.CANCELLED.value
        assert get_open_queue(connection) is None
        params = collect_rename_parameters(connection, [amber.batch.id])
        assert params.batch_ids == (amber.batch.id,)


def test_finish_elsewhere_and_delete_detach_batch_from_sequence(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        QueueStatus,
        add_batches_to_open_queue,
        get_open_queue,
        get_queue,
    )
    from ig_orchestrator.gui.batch_resume_service import (
        delete_draft_batch,
        finish_batch,
        mark_batch_executed_elsewhere,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("seq_a", "seq_alpha"), connection)
        second = save_batch_draft(_draft_with_name("seq_b", "seq_beta"), connection)
        third = save_batch_draft(_draft_with_name("seq_c", "seq_gamma"), connection)
        queue = add_batches_to_open_queue(
            connection,
            [first.batch.id, second.batch.id, third.batch.id],
        )

        finish_batch(connection, first.batch.id)
        after_finish = get_queue(connection, queue.id)
        by_batch = {item.batch_id: item for item in after_finish.items}
        assert by_batch[first.batch.id].status == QueueItemStatus.REMOVED.value
        assert [item.batch_id for item in after_finish.pending_items] == [
            second.batch.id,
            third.batch.id,
        ]

        mark_batch_executed_elsewhere(connection, second.batch.id)
        after_elsewhere = get_queue(connection, queue.id)
        by_batch = {item.batch_id: item for item in after_elsewhere.items}
        assert by_batch[second.batch.id].status == QueueItemStatus.REMOVED.value
        assert [item.batch_id for item in after_elsewhere.pending_items] == [
            third.batch.id
        ]
        stored_second = BatchRepository(connection).get_by_id(second.batch.id)
        assert stored_second.status is InputBatchStatus.AWAITING_RENAME

        delete_draft_batch(connection, third.batch.id)
        remaining = get_queue(connection, queue.id)
        assert remaining.status == QueueStatus.CANCELLED.value
        assert get_open_queue(connection) is None
        assert BatchRepository(connection).get_by_id(third.batch.id) is None


def test_get_open_queue_cancels_awaiting_rename_with_only_removed_items(
    tmp_path: Path,
) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        QueueStatus,
        add_batches_to_open_queue,
        get_open_queue,
        get_queue,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("ghost1", "ghost_one"), connection)
        queue = add_batches_to_open_queue(connection, [first.batch.id])
        now = "2026-08-31T06:55:07+00:00"
        connection.execute(
            """
            UPDATE batch_run_queue_items
            SET status = ?, updated_at = ?
            WHERE queue_id = ?
            """,
            (QueueItemStatus.REMOVED.value, now, queue.id),
        )
        connection.execute(
            """
            UPDATE batch_run_queues
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (QueueStatus.AWAITING_RENAME.value, now, queue.id),
        )
        connection.commit()
        assert get_open_queue(connection) is None
        assert get_queue(connection, queue.id).status == QueueStatus.CANCELLED.value


def test_add_batches_reactivates_removed_queue_item(tmp_path: Path) -> None:
    from ig_orchestrator.gui.batch_queue_service import (
        QueueItemStatus,
        add_batches_to_open_queue,
        get_queue,
        remove_queue_item,
    )

    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)
    with connect(db_path) as connection:
        first = save_batch_draft(_draft_with_name("readd", "readd_user"), connection)
        keeper = save_batch_draft(_draft_with_name("keep", "keep_user"), connection)
        queue = add_batches_to_open_queue(
            connection, [first.batch.id, keeper.batch.id]
        )
        remove_queue_item(connection, queue.items[0].id)
        restored = add_batches_to_open_queue(connection, [first.batch.id])
        assert restored.id == queue.id
        by_batch = {item.batch_id: item for item in restored.items}
        assert by_batch[first.batch.id].status == QueueItemStatus.PENDING.value
        assert by_batch[keeper.batch.id].status == QueueItemStatus.PENDING.value
        assert get_queue(connection, restored.id).id == restored.id


