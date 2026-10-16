"""Pause not-started accounts of a batch by moving them to a saved (DRAFT) batch."""

from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from ig_orchestrator.db.schema_mode import is_gui_schema

PAUSE_SUFFIX = "_PAUSA"
PAUSABLE_BATCH_STATUSES = frozenset({"IMPORTED", "PROCESSING", "PARTIAL"})


class PauseAccountsError(ValueError):
    """Raised when the selected accounts cannot be paused."""


@dataclass(frozen=True, slots=True)
class PauseAccountsResult:
    target_batch_id: int
    target_batch_name: str
    created: bool
    usernames: tuple[str, ...]
    url_count: int


def pause_accounts_to_new_batch(
    connection: Connection,
    *,
    batch_id: int,
    usernames: list[str],
) -> PauseAccountsResult:
    """Move not-started accounts (PENDING, every URL PENDING) to ``<name>_PAUSA``.

    The target is a DRAFT batch ("GUARDADO"). If ``<name>_PAUSA`` already exists as
    DRAFT the accounts are appended to it; otherwise a new batch is created
    (``_PAUSA2``, ``_PAUSA3``... when the name is taken by a non-draft batch).
    All-or-nothing: if any account is not pausable nothing is changed.
    """
    if not is_gui_schema(connection):
        raise PauseAccountsError("Pausar cuentas solo está disponible en la base de la GUI")
    wanted = [name.strip().casefold() for name in usernames if name.strip()]
    if not wanted:
        raise PauseAccountsError("Selecciona al menos una cuenta")

    batch = connection.execute(
        """
        SELECT b.id, b.name, b.schema_version, b.start_date, bs.code AS status
        FROM batches b JOIN batch_statuses bs ON bs.id = b.status_id
        WHERE b.id = ?
        """,
        (batch_id,),
    ).fetchone()
    if batch is None:
        raise PauseAccountsError(f"Lote no encontrado: {batch_id}")
    if str(batch["status"]) not in PAUSABLE_BATCH_STATUSES:
        raise PauseAccountsError(
            "Solo se pueden pausar cuentas de un lote registrado y no terminado "
            f"(estado actual: {batch['status']})"
        )

    try:
        connection.execute("BEGIN IMMEDIATE")
        accounts = _load_accounts(connection, batch_id, wanted)
        _validate(connection, batch_id, accounts, wanted)
        target_id, target_name, created = _find_or_create_target(connection, batch)
        url_count = _move(connection, batch_id, target_id, accounts)
        connection.execute(
            "UPDATE batches SET updated_at = datetime('now') WHERE id IN (?, ?)",
            (batch_id, target_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return PauseAccountsResult(
        target_batch_id=target_id,
        target_batch_name=target_name,
        created=created,
        usernames=tuple(str(row["username"]) for row in accounts),
        url_count=url_count,
    )


def pausable_usernames(connection: Connection, batch_id: int) -> set[str]:
    """Usernames (casefolded) of the batch accounts that could be paused now."""
    if not is_gui_schema(connection):
        return set()
    rows = connection.execute(
        """
        SELECT ca.username
        FROM batch_accounts ba
        JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
        JOIN batch_account_statuses bas ON bas.id = ba.status_id
        WHERE ba.batch_id = ? AND bas.code = 'PENDING'
          AND NOT EXISTS (
              SELECT 1 FROM batch_urls bu
              JOIN batch_url_statuses bus ON bus.id = bu.status_id
              WHERE bu.batch_account_id = ba.id AND bus.code <> 'PENDING'
          )
        """,
        (batch_id,),
    ).fetchall()
    return {str(row["username"]).casefold() for row in rows}


def _load_accounts(connection: Connection, batch_id: int, wanted: list[str]) -> list:
    rows = connection.execute(
        """
        SELECT ba.id, ca.username, bas.code AS status
        FROM batch_accounts ba
        JOIN catalog_accounts ca ON ca.id = ba.catalog_account_id
        JOIN batch_account_statuses bas ON bas.id = ba.status_id
        WHERE ba.batch_id = ?
        ORDER BY ba.sort_order, ba.id
        """,
        (batch_id,),
    ).fetchall()
    return [row for row in rows if str(row["username"]).casefold() in set(wanted)]


def _validate(connection: Connection, batch_id: int, accounts: list, wanted: list[str]) -> None:
    found = {str(row["username"]).casefold() for row in accounts}
    missing = sorted(set(wanted) - found)
    if missing:
        raise PauseAccountsError(
            "No están en el lote: " + ", ".join(f"@{name}" for name in missing)
        )
    refused = []
    for row in accounts:
        started = connection.execute(
            """
            SELECT 1 FROM batch_urls bu
            JOIN batch_url_statuses bus ON bus.id = bu.status_id
            WHERE bu.batch_account_id = ? AND bus.code <> 'PENDING'
            LIMIT 1
            """,
            (row["id"],),
        ).fetchone()
        if str(row["status"]) != "PENDING" or started is not None:
            refused.append(f"@{row['username']} ({row['status']})")
    if refused:
        raise PauseAccountsError(
            "Solo se pueden pausar cuentas que no han empezado (PENDIENTE). "
            "No válidas: " + ", ".join(refused)
        )
    total = connection.execute(
        "SELECT COUNT(*) FROM batch_accounts WHERE batch_id = ?", (batch_id,)
    ).fetchone()[0]
    if len(accounts) >= int(total):
        raise PauseAccountsError(
            "No se pueden pausar todas las cuentas: el lote se quedaría vacío"
        )


def _find_or_create_target(connection: Connection, batch) -> tuple[int, str, bool]:
    base = f"{batch['name']}{PAUSE_SUFFIX}"
    number = 1
    while True:
        name = base if number == 1 else f"{base}{number}"
        row = connection.execute(
            """
            SELECT b.id, bs.code AS status
            FROM batches b JOIN batch_statuses bs ON bs.id = b.status_id
            WHERE b.name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            draft_id = connection.execute(
                "SELECT id FROM batch_statuses WHERE code = 'DRAFT'"
            ).fetchone()[0]
            cursor = connection.execute(
                """
                INSERT INTO batches (
                    name, schema_version, status_id, start_date, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (name, batch["schema_version"], draft_id, batch["start_date"]),
            )
            return int(cursor.lastrowid), name, True
        if str(row["status"]) == "DRAFT":
            return int(row["id"]), name, False
        number += 1


def _move(connection: Connection, source_id: int, target_id: int, accounts: list) -> int:
    next_order = int(
        connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM batch_accounts WHERE batch_id = ?",
            (target_id,),
        ).fetchone()[0]
    )
    url_count = 0
    for row in accounts:
        next_order += 1
        cursor = connection.execute(
            """
            UPDATE batch_accounts
            SET batch_id = ?, sort_order = ?, updated_at = datetime('now')
            WHERE id = ? AND batch_id = ?
              AND status_id = (SELECT id FROM batch_account_statuses WHERE code = 'PENDING')
            """,
            (target_id, next_order, row["id"], source_id),
        )
        if cursor.rowcount != 1:
            raise PauseAccountsError(
                f"@{row['username']} cambió de estado mientras se pausaba; reintenta"
            )
        # Let the next run of the target batch adopt the URLs.
        url_count += connection.execute(
            """
            UPDATE batch_urls SET batch_run_id = NULL, updated_at = datetime('now')
            WHERE batch_account_id = ?
            """,
            (row["id"],),
        ).rowcount
        connection.execute(
            "UPDATE duplicate_urls SET batch_id = ? WHERE batch_account_id = ?",
            (target_id, row["id"]),
        )
    return url_count


__all__ = [
    "PAUSABLE_BATCH_STATUSES",
    "PAUSE_SUFFIX",
    "PauseAccountsError",
    "PauseAccountsResult",
    "pausable_usernames",
    "pause_accounts_to_new_batch",
]
