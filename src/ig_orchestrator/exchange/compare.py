"""Non-Tk helpers: compare pulled folders with a batch and probe a path."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Connection


@dataclass(frozen=True, slots=True)
class BatchComparison:
    received: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


def list_recent_batches(connection: Connection, limit: int = 30) -> list[tuple[int, str, str]]:
    rows = connection.execute(
        "SELECT id, batch_name, status FROM input_batches ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [(int(r[0]), str(r[1]), str(r[2])) for r in rows]


def batch_usernames(connection: Connection, batch_id: int) -> list[str]:
    rows = connection.execute(
        """
        SELECT a.username
        FROM batch_accounts ba
        JOIN catalog_accounts a ON a.id = ba.catalog_account_id
        WHERE ba.batch_id = ?
        ORDER BY ba.sort_order
        """,
        (batch_id,),
    ).fetchall()
    return [str(r[0]) for r in rows]


def compare_with_batch(
    connection: Connection, batch_id: int, folder_names: list[str]
) -> BatchComparison:
    """Case-insensitive comparison of folder names against the batch accounts."""

    expected = {name.casefold(): name for name in batch_usernames(connection, batch_id)}
    present = {name.casefold(): name for name in folder_names}
    return BatchComparison(
        received=sorted((expected[k] for k in expected if k in present), key=str.casefold),
        missing=sorted((expected[k] for k in expected if k not in present), key=str.casefold),
        extra=sorted((present[k] for k in present if k not in expected), key=str.casefold),
    )


@dataclass(frozen=True, slots=True)
class ProbeResult:
    exists: bool
    writable: bool = False
    free_bytes: int | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and not self.error


def probe_path(path: str | Path, *, timeout: float = 8.0, check_write: bool = True) -> ProbeResult:
    """Existence, write access and free space, bounded by *timeout* (offline shares hang)."""

    outcome: list[ProbeResult] = []

    def _work() -> None:
        target = Path(path)
        try:
            if not target.is_dir():
                outcome.append(ProbeResult(False, error="No existe o no es accesible"))
                return
            writable = False
            if check_write:
                marker = target / f".probe_{uuid.uuid4().hex}"
                try:
                    marker.write_bytes(b"")
                    os.remove(marker)
                    writable = True
                except OSError:
                    writable = False
            outcome.append(ProbeResult(True, writable, shutil.disk_usage(target).free))
        except OSError as exc:
            outcome.append(ProbeResult(False, error=str(exc)))

    thread = threading.Thread(target=_work, name="path-probe", daemon=True)
    thread.start()
    thread.join(timeout)
    if not outcome:
        return ProbeResult(False, error=f"Sin respuesta en {timeout:.0f} s")
    return outcome[0]
