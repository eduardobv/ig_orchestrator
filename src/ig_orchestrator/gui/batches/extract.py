"""Extract the COMPLETED accounts of a stopped batch into a new "por renombrar" batch."""

from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from ig_orchestrator.db.schema_mode import is_gui_schema

EXTRACTABLE_BATCH_STATUSES = frozenset({"PARTIAL", "FAILED"})


class ExtractCompletedError(ValueError):
    """Raised when the completed accounts cannot be extracted."""


@dataclass(frozen=True, slots=True)
class ExtractCompletedResult:
    target_batch_id: int
    target_batch_name: str
    usernames: tuple[str, ...]
    url_count: int


def list_completed_usernames(connection: Connection, batch_id: int) -> list[str]:
    """Usernames of the COMPLETED accounts of a batch, in batch order."""
    if not is_gui_schema(connection):
        return []
    rows = connection.execute(
        """
        SELECT ca.username
        FROM batch_accounts ba
        JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
        JOIN batch_account_statuses bas ON bas.id = ba.status_id
        WHERE ba.batch_id = ? AND bas.code = 'COMPLETED'
        ORDER BY ba.sort_order, ba.id
        """,
        (batch_id,),
    ).fetchall()
    return [str(row["username"]) for row in rows]


def suggest_extract_name(connection: Connection, batch_id: int) -> str:
    """Free name derived from the source batch: ``<nombre>_LISTAS``, ``_LISTAS2``..."""
    row = connection.execute("SELECT name FROM batches WHERE id = ?", (batch_id,)).fetchone()
    base = f"{row['name'] if row else 'lote'}_LISTAS"
    name, number = base, 1
    while connection.execute("SELECT 1 FROM batches WHERE name = ?", (name,)).fetchone():
        number += 1
        name = f"{base}{number}"
    return name


def extract_completed_accounts(
    connection: Connection,
    *,
    batch_id: int,
    target_name: str,
) -> ExtractCompletedResult:
    """Move every COMPLETED account of a stopped batch to a new AWAITING_RENAME batch.

    The accounts keep their rows (new / update / Renew flags, owner, destination, URLs and
    their statuses, run history), so the new batch can be renamed here or published and
    pulled from another instance exactly as the original would have been. The accounts
    that are not completed stay in the source batch, which can be resumed later.
    All-or-nothing.
    """
    if not is_gui_schema(connection):
        raise ExtractCompletedError("Esta acción solo está disponible en la base de la GUI")
    name = target_name.strip()
    if not name:
        raise ExtractCompletedError("El nombre del nuevo lote no puede estar vacío")

    batch = connection.execute(
        """
        SELECT b.id, b.schema_version, b.start_date, bs.code AS status
        FROM batches b JOIN batch_statuses bs ON bs.id = b.status_id
        WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if batch is None:
        raise ExtractCompletedError(f"Lote no encontrado: {batch_id}")
    if str(batch["status"]) not in EXTRACTABLE_BATCH_STATUSES:
        raise ExtractCompletedError(
            "Solo se pueden sacar cuentas de un lote detenido (PARTIAL); "
            f"estado actual: {batch['status']}"
        )

    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM batches WHERE name = ?", (name,)).fetchone():
            raise ExtractCompletedError(f"Ya existe un lote llamado «{name}»")
        accounts = connection.execute(
            """
            SELECT ba.id, ca.username
            FROM batch_accounts ba
            JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
            JOIN batch_account_statuses bas ON bas.id = ba.status_id
            WHERE ba.batch_id = ? AND bas.code = 'COMPLETED'
            ORDER BY ba.sort_order, ba.id
            """,
            (batch_id,),
        ).fetchall()
        if not accounts:
            raise ExtractCompletedError("El lote no tiene cuentas completadas")
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM batch_accounts WHERE batch_id = ?", (batch_id,)
            ).fetchone()[0]
        )
        if len(accounts) >= total:
            raise ExtractCompletedError(
                "Todas las cuentas están completadas: usa Renombrar sobre el lote "
                "en lugar de sacarlas"
            )
        status_id = connection.execute(
            "SELECT id FROM batch_statuses WHERE code = 'AWAITING_RENAME'"
        ).fetchone()[0]
        target_id = int(
            connection.execute(
                """
                INSERT INTO batches (
                    name, schema_version, status_id, start_date, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (name, batch["schema_version"], status_id, batch["start_date"]),
            ).lastrowid
        )
        url_count = 0
        for order, row in enumerate(accounts, start=1):
            connection.execute(
                """
                UPDATE batch_accounts
                SET batch_id = ?, sort_order = ?, updated_at = datetime('now')
                WHERE id = ? AND batch_id = ?
                """,
                (target_id, order, row["id"], batch_id),
            )
            url_count += int(
                connection.execute(
                    "SELECT COUNT(*) FROM batch_urls WHERE batch_account_id = ?",
                    (row["id"],),
                ).fetchone()[0]
            )
            connection.execute(
                "UPDATE duplicate_urls SET batch_id = ? WHERE batch_account_id = ?",
                (target_id, row["id"]),
            )
        connection.execute(
            "UPDATE batches SET updated_at = datetime('now') WHERE id = ?", (batch_id,)
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ExtractCompletedResult(
        target_batch_id=target_id,
        target_batch_name=name,
        usernames=tuple(str(row["username"]) for row in accounts),
        url_count=url_count,
    )


__all__ = [
    "EXTRACTABLE_BATCH_STATUSES",
    "ExtractCompletedError",
    "ExtractCompletedResult",
    "extract_completed_accounts",
    "list_completed_usernames",
    "suggest_extract_name",
]
