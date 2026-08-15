from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from sqlite3 import Connection

from ig_orchestrator.gui.batch_draft import AccountDraft
from ig_orchestrator.gui.batch_resume_service import finish_batch, load_batch_draft
from ig_orchestrator.gui.process_runner import NewAccountRenameParameters
from ig_orchestrator.models import InputBatchStatus


class QueueStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    AWAITING_RENAME = "AWAITING_RENAME"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class QueueItemStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    REMOVED = "REMOVED"
    SKIPPED = "SKIPPED"


EXECUTABLE_BATCH_STATUSES = frozenset(
    {
        InputBatchStatus.DRAFT.value,
        InputBatchStatus.IMPORTED.value,
        InputBatchStatus.PARTIAL.value,
        InputBatchStatus.FAILED.value,
    }
)
RENAME_BATCH_STATUSES = frozenset({InputBatchStatus.AWAITING_RENAME.value})
OPEN_QUEUE_STATUSES = frozenset(
    {
        QueueStatus.DRAFT.value,
        QueueStatus.RUNNING.value,
        QueueStatus.PAUSED.value,
        QueueStatus.AWAITING_RENAME.value,
    }
)


class BatchQueueError(ValueError):
    """Raised when a queue operation is invalid."""


@dataclass(frozen=True, slots=True)
class QueueItem:
    id: int
    queue_id: int
    batch_id: int
    batch_name: str
    batch_status: str
    sort_order: int
    status: str

    @property
    def is_pending(self) -> bool:
        return self.status == QueueItemStatus.PENDING.value

    @property
    def is_running(self) -> bool:
        return self.status == QueueItemStatus.RUNNING.value

    @property
    def is_removed(self) -> bool:
        return self.status == QueueItemStatus.REMOVED.value

    @property
    def participates_in_rename(self) -> bool:
        return self.status not in {
            QueueItemStatus.REMOVED.value,
            QueueItemStatus.SKIPPED.value,
        }


@dataclass(frozen=True, slots=True)
class BatchQueue:
    id: int
    status: str
    items: tuple[QueueItem, ...]
    created_at: str
    updated_at: str

    @property
    def pending_items(self) -> tuple[QueueItem, ...]:
        return tuple(item for item in self.items if item.is_pending)

    @property
    def running_item(self) -> QueueItem | None:
        return next((item for item in self.items if item.is_running), None)

    @property
    def rename_batch_ids(self) -> tuple[int, ...]:
        return tuple(item.batch_id for item in self.items if item.participates_in_rename)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_QUEUE_STATUSES


@dataclass(frozen=True, slots=True)
class CombinedRenameParameters:
    start_now_date: str
    new_accounts: tuple[NewAccountRenameParameters, ...]
    batch_ids: tuple[int, ...]
    dates_by_batch: tuple[tuple[int, str], ...]

    @property
    def has_mixed_dates(self) -> bool:
        dates = {date for _batch_id, date in self.dates_by_batch if date}
        return len(dates) > 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batch_row(connection: Connection, batch_id: int):
    row = connection.execute(
        "SELECT id, batch_name, status FROM input_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    if row is None:
        raise BatchQueueError(f"Batch not found: {batch_id}")
    return row


def get_open_queue(connection: Connection) -> BatchQueue | None:
    row = connection.execute(
        """
        SELECT id FROM batch_run_queues
        WHERE status IN (?, ?, ?, ?)
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        tuple(OPEN_QUEUE_STATUSES),
    ).fetchone()
    if row is None:
        return None
    return get_queue(connection, int(row["id"]))


def get_queue(connection: Connection, queue_id: int) -> BatchQueue:
    row = connection.execute(
        "SELECT * FROM batch_run_queues WHERE id = ?",
        (queue_id,),
    ).fetchone()
    if row is None:
        raise BatchQueueError(f"Queue not found: {queue_id}")
    item_rows = connection.execute(
        """
        SELECT i.id, i.queue_id, i.batch_id, i.sort_order, i.status,
               b.batch_name, b.status AS batch_status
        FROM batch_run_queue_items i
        JOIN input_batches b ON b.id = i.batch_id
        WHERE i.queue_id = ?
        ORDER BY i.sort_order, i.id
        """,
        (queue_id,),
    ).fetchall()
    items = tuple(
        QueueItem(
            id=int(item["id"]),
            queue_id=int(item["queue_id"]),
            batch_id=int(item["batch_id"]),
            batch_name=str(item["batch_name"]),
            batch_status=str(item["batch_status"]),
            sort_order=int(item["sort_order"]),
            status=str(item["status"]),
        )
        for item in item_rows
    )
    return BatchQueue(
        id=int(row["id"]),
        status=str(row["status"]),
        items=items,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _create_empty_queue(connection: Connection) -> int:
    now = _now()
    cursor = connection.execute(
        """
        INSERT INTO batch_run_queues (status, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        (QueueStatus.DRAFT.value, now, now),
    )
    connection.commit()
    return int(cursor.lastrowid)


def ensure_open_queue(connection: Connection) -> BatchQueue:
    existing = get_open_queue(connection)
    if existing is not None:
        return existing
    return get_queue(connection, _create_empty_queue(connection))


def add_batches_to_open_queue(
    connection: Connection,
    batch_ids: list[int] | tuple[int, ...],
) -> BatchQueue:
    if not batch_ids:
        raise BatchQueueError("Selecciona al menos un lote para la cola")
    queue = ensure_open_queue(connection)
    existing_ids = {item.batch_id for item in queue.items}
    next_order = max((item.sort_order for item in queue.items), default=0)
    now = _now()
    added = 0
    for batch_id in batch_ids:
        if batch_id in existing_ids:
            continue
        row = _batch_row(connection, batch_id)
        status = str(row["status"])
        if status in EXECUTABLE_BATCH_STATUSES:
            item_status = QueueItemStatus.PENDING.value
        elif status in RENAME_BATCH_STATUSES:
            item_status = QueueItemStatus.COMPLETED.value
        else:
            raise BatchQueueError(
                f"El lote {batch_id} ({row['batch_name']}) no se puede "
                f"encolar en estado {status}"
            )
        next_order += 1
        connection.execute(
            """
            INSERT INTO batch_run_queue_items (
                queue_id, batch_id, sort_order, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (queue.id, batch_id, next_order, item_status, now, now),
        )
        existing_ids.add(batch_id)
        added += 1
    if added == 0 and not queue.items:
        raise BatchQueueError("No se agregó ningún lote nuevo a la cola")
    has_pending = connection.execute(
        """
        SELECT 1 FROM batch_run_queue_items
        WHERE queue_id = ? AND status = ?
        LIMIT 1
        """,
        (queue.id, QueueItemStatus.PENDING.value),
    ).fetchone()
    next_status = queue.status
    if has_pending is not None and queue.status == QueueStatus.AWAITING_RENAME.value:
        next_status = QueueStatus.DRAFT.value
    connection.execute(
        "UPDATE batch_run_queues SET status = ?, updated_at = ? WHERE id = ?",
        (next_status, now, queue.id),
    )
    connection.commit()
    return get_queue(connection, queue.id)


def remove_pending_item(connection: Connection, item_id: int) -> BatchQueue:
    row = connection.execute(
        "SELECT * FROM batch_run_queue_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise BatchQueueError(f"Ítem de cola no encontrado: {item_id}")
    if str(row["status"]) != QueueItemStatus.PENDING.value:
        raise BatchQueueError("Solo se pueden quitar lotes que aún no han empezado")
    now = _now()
    connection.execute(
        """
        UPDATE batch_run_queue_items
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (QueueItemStatus.REMOVED.value, now, item_id),
    )
    connection.execute(
        "UPDATE batch_run_queues SET updated_at = ? WHERE id = ?",
        (now, int(row["queue_id"])),
    )
    connection.commit()
    return get_queue(connection, int(row["queue_id"]))


def move_queue_item(connection: Connection, item_id: int, *, direction: int) -> BatchQueue:
    if direction not in (-1, 1):
        raise BatchQueueError("direction must be -1 or 1")
    row = connection.execute(
        "SELECT * FROM batch_run_queue_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise BatchQueueError(f"Ítem de cola no encontrado: {item_id}")
    queue = get_queue(connection, int(row["queue_id"]))
    movable = [item for item in queue.items if not item.is_removed]
    index = next((i for i, item in enumerate(movable) if item.id == item_id), None)
    if index is None:
        raise BatchQueueError("El ítem no se puede reordenar")
    target = index + direction
    if target < 0 or target >= len(movable):
        return queue
    first = movable[index]
    second = movable[target]
    now = _now()
    connection.execute(
        "UPDATE batch_run_queue_items SET sort_order = ?, updated_at = ? WHERE id = ?",
        (second.sort_order, now, first.id),
    )
    connection.execute(
        "UPDATE batch_run_queue_items SET sort_order = ?, updated_at = ? WHERE id = ?",
        (first.sort_order, now, second.id),
    )
    connection.execute(
        "UPDATE batch_run_queues SET updated_at = ? WHERE id = ?",
        (now, queue.id),
    )
    connection.commit()
    return get_queue(connection, queue.id)


def start_or_resume_queue(connection: Connection, queue_id: int) -> QueueItem:
    queue = get_queue(connection, queue_id)
    if queue.status == QueueStatus.COMPLETED.value:
        raise BatchQueueError("La cola ya está completada")
    current = queue.running_item
    if current is None:
        if not queue.pending_items:
            raise BatchQueueError("No hay lotes pendientes en la cola")
        current = queue.pending_items[0]
        now = _now()
        connection.execute(
            """
            UPDATE batch_run_queue_items
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (QueueItemStatus.RUNNING.value, now, current.id),
        )
    now = _now()
    connection.execute(
        "UPDATE batch_run_queues SET status = ?, updated_at = ? WHERE id = ?",
        (QueueStatus.RUNNING.value, now, queue.id),
    )
    connection.commit()
    return get_queue(connection, queue.id).running_item or current


def mark_current_item_completed(connection: Connection, queue_id: int) -> QueueItem | None:
    queue = get_queue(connection, queue_id)
    current = queue.running_item
    now = _now()
    if current is not None:
        connection.execute(
            """
            UPDATE batch_run_queue_items
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (QueueItemStatus.COMPLETED.value, now, current.id),
        )
    remaining = connection.execute(
        """
        SELECT 1 FROM batch_run_queue_items
        WHERE queue_id = ? AND status = ?
        LIMIT 1
        """,
        (queue_id, QueueItemStatus.PENDING.value),
    ).fetchone()
    if remaining is None:
        connection.execute(
            "UPDATE batch_run_queues SET status = ?, updated_at = ? WHERE id = ?",
            (QueueStatus.AWAITING_RENAME.value, now, queue_id),
        )
        connection.commit()
        return None
    connection.execute(
        "UPDATE batch_run_queues SET updated_at = ? WHERE id = ?",
        (now, queue_id),
    )
    connection.commit()
    return get_queue(connection, queue_id).pending_items[0]


def pause_queue(connection: Connection, queue_id: int) -> BatchQueue:
    now = _now()
    connection.execute(
        "UPDATE batch_run_queues SET status = ?, updated_at = ? WHERE id = ?",
        (QueueStatus.PAUSED.value, now, queue_id),
    )
    connection.commit()
    return get_queue(connection, queue_id)


def next_item_after_removal(connection: Connection, queue_id: int) -> QueueItem | None:
    """If the running item just finished and no PENDING remain, close for rename."""
    queue = get_queue(connection, queue_id)
    if queue.pending_items:
        return queue.pending_items[0]
    if queue.running_item is None:
        now = _now()
        connection.execute(
            "UPDATE batch_run_queues SET status = ?, updated_at = ? WHERE id = ?",
            (QueueStatus.AWAITING_RENAME.value, now, queue_id),
        )
        connection.commit()
    return None


def collect_rename_parameters(
    connection: Connection,
    batch_ids: list[int] | tuple[int, ...],
) -> CombinedRenameParameters:
    if not batch_ids:
        raise BatchQueueError("No hay lotes para armar el comando de renombrado")
    dates_by_batch: list[tuple[int, str]] = []
    new_accounts: list[NewAccountRenameParameters] = []
    seen: set[str] = set()
    for batch_id in batch_ids:
        draft = load_batch_draft(connection, batch_id)
        date_value = draft.default_start_now_date.strip()
        dates_by_batch.append((batch_id, date_value))
        for account in draft.accounts:
            _append_new_account(account, new_accounts, seen)
    start_now_date = _latest_start_date(dates_by_batch)
    return CombinedRenameParameters(
        start_now_date=start_now_date,
        new_accounts=tuple(new_accounts),
        batch_ids=tuple(batch_ids),
        dates_by_batch=tuple(dates_by_batch),
    )


def collect_queue_rename_parameters(
    connection: Connection,
    queue_id: int,
) -> CombinedRenameParameters:
    queue = get_queue(connection, queue_id)
    return collect_rename_parameters(connection, queue.rename_batch_ids)


def finish_queue_after_rename(connection: Connection, queue_id: int) -> None:
    queue = get_queue(connection, queue_id)
    for batch_id in queue.rename_batch_ids:
        finish_batch(connection, batch_id)
    now = _now()
    connection.execute(
        "UPDATE batch_run_queues SET status = ?, updated_at = ? WHERE id = ?",
        (QueueStatus.COMPLETED.value, now, queue_id),
    )
    connection.commit()


def _append_new_account(
    account: AccountDraft,
    collected: list[NewAccountRenameParameters],
    seen: set[str],
) -> None:
    if not account.is_new_account:
        return
    key = account.username.casefold()
    if key in seen:
        return
    seen.add(key)
    collected.append(
        NewAccountRenameParameters(
            username=account.username,
            owner_id=account.owner_id,
            start_init_date=account.start_init_date,
            destination_path=account.destination_path,
        )
    )


def _latest_start_date(dates_by_batch: list[tuple[int, str]]) -> str:
    valid = [(batch_id, value) for batch_id, value in dates_by_batch if value]
    if not valid:
        raise BatchQueueError("Ningún lote de la cola tiene startNowDate")
    return max(valid, key=lambda item: item[1])[1]


__all__ = [
    "BatchQueue",
    "BatchQueueError",
    "CombinedRenameParameters",
    "EXECUTABLE_BATCH_STATUSES",
    "OPEN_QUEUE_STATUSES",
    "QueueItem",
    "QueueItemStatus",
    "QueueStatus",
    "RENAME_BATCH_STATUSES",
    "add_batches_to_open_queue",
    "collect_queue_rename_parameters",
    "collect_rename_parameters",
    "ensure_open_queue",
    "finish_queue_after_rename",
    "get_open_queue",
    "get_queue",
    "mark_current_item_completed",
    "move_queue_item",
    "next_item_after_removal",
    "pause_queue",
    "remove_pending_item",
    "start_or_resume_queue",
]
