"""Batch management used by the «Lotes guardados y ejecuciones» dialog (feat-uc2-21)."""

from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from ig_orchestrator.db.schema_mode import is_gui_schema
from ig_orchestrator.gui.batches.pause import PauseAccountsError


class BatchManageError(ValueError):
    """Raised when a batch management action is not allowed."""


@dataclass(frozen=True, slots=True)
class BatchAccountRow:
    username: str
    priority: int
    url_count: int
    download_stories: bool
    start_date: str
    status: str


def _require_gui(connection: Connection) -> None:
    if not is_gui_schema(connection):
        raise BatchManageError("Esta acción solo está disponible en la base de la GUI")


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise BatchManageError("El nombre del lote no puede estar vacío")
    return cleaned


def create_empty_draft_batch(connection: Connection, name: str) -> int:
    """Create an empty DRAFT ("GUARDADO") batch and return its id."""
    _require_gui(connection)
    name = _clean_name(name)
    if connection.execute("SELECT 1 FROM batches WHERE name = ?", (name,)).fetchone():
        raise BatchManageError(f"Ya existe un lote llamado «{name}»")
    draft_id = connection.execute(
        "SELECT id FROM batch_statuses WHERE code = 'DRAFT'"
    ).fetchone()[0]
    cursor = connection.execute(
        """
        INSERT INTO batches (
            name, schema_version, status_id, start_date, created_at, updated_at
        )
        VALUES (?, '1.0', ?, date('now', 'localtime'), datetime('now'), datetime('now'))
        """,
        (name, draft_id),
    )
    connection.commit()
    return int(cursor.lastrowid)


def rename_batch(connection: Connection, batch_id: int, new_name: str) -> None:
    """Change the name of an active (not completed) batch."""
    _require_gui(connection)
    new_name = _clean_name(new_name)
    row = connection.execute(
        """
        SELECT bs.code AS status FROM batches b
        JOIN batch_statuses bs ON bs.id = b.status_id WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if row is None:
        raise BatchManageError(f"Lote no encontrado: {batch_id}")
    if str(row["status"]) == "COMPLETED":
        raise BatchManageError("Un lote histórico (COMPLETED) no se puede renombrar")
    if connection.execute(
        "SELECT 1 FROM batches WHERE name = ? AND id <> ?", (new_name, batch_id)
    ).fetchone():
        raise BatchManageError(f"Ya existe un lote llamado «{new_name}»")
    connection.execute(
        "UPDATE batches SET name = ?, updated_at = datetime('now') WHERE id = ?",
        (new_name, batch_id),
    )
    connection.commit()


def list_batch_accounts(connection: Connection, batch_id: int) -> list[BatchAccountRow]:
    """Accounts of a batch for the detail table (username, prio, urls, stories, date)."""
    if not is_gui_schema(connection):
        return []
    rows = connection.execute(
        """
        SELECT ca.username, ba.priority, ba.download_stories, b.start_date,
               bas.code AS status,
               (SELECT COUNT(*) FROM batch_urls bu
                WHERE bu.batch_account_id = ba.id) AS url_count
        FROM batch_accounts ba
        JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
        JOIN batches b ON b.id = ba.batch_id
        JOIN batch_account_statuses bas ON bas.id = ba.status_id
        WHERE ba.batch_id = ?
        ORDER BY ba.sort_order, ba.id
        """,
        (batch_id,),
    ).fetchall()
    return [
        BatchAccountRow(
            username=str(row["username"]),
            priority=int(row["priority"] or 0),
            url_count=int(row["url_count"] or 0),
            download_stories=bool(row["download_stories"]),
            start_date=str(row["start_date"] or ""),
            status=str(row["status"]),
        )
        for row in rows
    ]


def list_draft_targets(connection: Connection, exclude_batch_id: int) -> list[tuple[int, str]]:
    """Saved (DRAFT) batches that can receive accounts, as (id, name)."""
    if not is_gui_schema(connection):
        return []
    rows = connection.execute(
        """
        SELECT b.id, b.name FROM batches b
        JOIN batch_statuses bs ON bs.id = b.status_id
        WHERE bs.code = 'DRAFT' AND b.id <> ?
        ORDER BY b.id DESC
        """,
        (exclude_batch_id,),
    ).fetchall()
    return [(int(row["id"]), str(row["name"])) for row in rows]


def is_batch_unstarted(connection: Connection, batch_id: int) -> bool:
    """True when nothing ever ran: no runs, every account and URL still PENDING."""
    if not is_gui_schema(connection):
        return False
    if connection.execute(
        "SELECT 1 FROM batch_runs WHERE batch_id = ? LIMIT 1", (batch_id,)
    ).fetchone():
        return False
    row = connection.execute(
        """
        SELECT 1 FROM batch_accounts ba
        JOIN batch_account_statuses bas ON bas.id = ba.status_id
        WHERE ba.batch_id = ?
          AND (bas.code <> 'PENDING' OR EXISTS (
              SELECT 1 FROM batch_urls bu
              JOIN batch_url_statuses bus ON bus.id = bu.status_id
              WHERE bu.batch_account_id = ba.id AND bus.code <> 'PENDING'))
        LIMIT 1
        """,
        (batch_id,),
    ).fetchone()
    return row is None


def restore_batch_to_draft(connection: Connection, batch_id: int) -> None:
    """Bring a closed (COMPLETED) batch that never started back as GUARDADO."""
    _require_gui(connection)
    row = connection.execute(
        """
        SELECT bs.code AS status FROM batches b
        JOIN batch_statuses bs ON bs.id = b.status_id WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if row is None:
        raise BatchManageError(f"Lote no encontrado: {batch_id}")
    if str(row["status"]) != "COMPLETED":
        raise BatchManageError("Solo se recuperan lotes del histórico (COMPLETED)")
    if not is_batch_unstarted(connection, batch_id):
        raise BatchManageError(
            "Este lote ya se inició (tiene ejecuciones o URLs procesadas) y no se puede "
            "recuperar; solo se pueden abrir en modo lectura."
        )
    connection.execute(
        """
        UPDATE batches
        SET status_id = (SELECT id FROM batch_statuses WHERE code = 'DRAFT'),
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (batch_id,),
    )
    connection.commit()


def delete_unstarted_batch(connection: Connection, batch_id: int) -> int:
    """Delete a GUARDADO batch (empty or with accounts) or one that never started.

    Returns the number of accounts removed. Batches with executions are refused.
    """
    _require_gui(connection)
    row = connection.execute(
        """
        SELECT bs.code AS status FROM batches b
        JOIN batch_statuses bs ON bs.id = b.status_id WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if row is None:
        raise BatchManageError(f"Lote no encontrado: {batch_id}")
    status = str(row["status"])
    if status != "DRAFT" and not (
        status in {"IMPORTED", "COMPLETED"} and is_batch_unstarted(connection, batch_id)
    ):
        raise BatchManageError(
            "Solo se pueden borrar lotes GUARDADOS o que nunca se hayan iniciado. "
            "Un lote con ejecuciones se cierra con «Finalizar sin renombrar»."
        )
    account_ids = [
        int(r["id"])
        for r in connection.execute(
            "SELECT id FROM batch_accounts WHERE batch_id = ?", (batch_id,)
        )
    ]
    try:
        connection.execute("BEGIN IMMEDIATE")
        for account_id in account_ids:
            connection.execute(
                "DELETE FROM duplicate_urls WHERE batch_account_id = ?", (account_id,)
            )
            connection.execute(
                "DELETE FROM batch_urls WHERE batch_account_id = ?", (account_id,)
            )
        connection.execute("DELETE FROM batch_accounts WHERE batch_id = ?", (batch_id,))
        connection.execute("DELETE FROM duplicate_urls WHERE batch_id = ?", (batch_id,))
        connection.execute("DELETE FROM batch_queue_items WHERE batch_id = ?", (batch_id,))
        connection.execute("DELETE FROM batch_runs WHERE batch_id = ?", (batch_id,))
        connection.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return len(account_ids)


__all__ = [
    "BatchAccountRow",
    "BatchManageError",
    "PauseAccountsError",
    "create_empty_draft_batch",
    "delete_unstarted_batch",
    "is_batch_unstarted",
    "list_batch_accounts",
    "list_draft_targets",
    "rename_batch",
    "restore_batch_to_draft",
]
