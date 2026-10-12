"""Quarantine ("papelera") for library account folders.

Deleting an account moves its folder to ``LIBRARY\\.trash\\<stamp>__<username>`` on the same volume
(an instant rename). It can be restored while the original place is free; only an explicit,
typed confirmation removes it for good.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ig_orchestrator.library.fsops import FsOperationService
from ig_orchestrator.library.paths import to_abs

TRASH_DIR = ".trash"
CONFIRM_WORD = "ELIMINAR"
QUARANTINED, RESTORED, PURGED = "QUARANTINED", "RESTORED", "PURGED"


class TrashError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TrashItem:
    id: int
    account_id: int
    username: str
    original_rel: str
    trash_rel: str
    files: int
    bytes: int
    deleted_at: str
    status: str


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trash_items (
            id INTEGER PRIMARY KEY,
            catalog_account_id INTEGER NOT NULL REFERENCES catalog_accounts(id),
            original_rel TEXT NOT NULL,
            trash_rel TEXT NOT NULL,
            previous_status_id INTEGER,
            files INTEGER DEFAULT 0,
            bytes INTEGER DEFAULT 0,
            deleted_at TEXT NOT NULL,
            expires_at TEXT,
            status TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _stats(folder: str) -> tuple[int, int]:
    files = size = 0
    for current, _dirs, names in os.walk(folder):
        for name in names:
            files += 1
            try:
                size += os.path.getsize(os.path.join(current, name))
            except OSError:
                pass
    return files, size


class TrashService:
    def __init__(self, conn: sqlite3.Connection, *, root: str | None = None) -> None:
        self.conn = conn
        self.fs = FsOperationService(conn, root=root)
        ensure_schema(conn)

    # ------------------------------------------------------------- checks
    def blockers(self, account_id: int) -> list[str]:
        """Reasons why the account cannot be deleted right now (empty list = allowed)."""

        row = self.conn.execute("SELECT username, rel_path FROM catalog_accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            return ["La cuenta no existe"]
        reasons = []
        if not self.fs.is_online():
            reasons.append("La biblioteca (G:) no esta disponible")
        elif not row["rel_path"] or not os.path.isdir(self.fs.abs(str(row["rel_path"]))):
            reasons.append("La cuenta no tiene carpeta en la biblioteca")
        if self.fs._busy_accounts([account_id]):  # noqa: SLF001 - same rule as moves
            reasons.append("Esta en un lote en ejecucion")
        try:
            staged = self.conn.execute(
                "SELECT 1 FROM staged_accounts WHERE catalog_account_id = ? AND status <> 'DUMPED' LIMIT 1", (account_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            staged = None
        if staged is not None:
            reasons.append("Tiene datos pendientes de volcar en el almacen")
        return reasons

    # ------------------------------------------------------------ actions
    def quarantine(self, account_id: int, *, retention_days: int | None = None) -> int:
        reasons = self.blockers(account_id)
        if reasons:
            raise TrashError("; ".join(reasons))
        row = self.conn.execute(
            "SELECT username, rel_path, status_id FROM catalog_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        stamp = _now().strftime("%Y%m%d_%H%M%S")
        trash_rel = f"{TRASH_DIR}\\{stamp}__{row['username']}"
        source = self.fs.abs(str(row["rel_path"]))
        target = self.fs.abs(trash_rel)
        files, size = _stats(source)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            raise TrashError("Ya existe un elemento con ese nombre en la papelera")
        os.rename(source, target)
        deleted_id = self.conn.execute("SELECT id FROM catalog_account_statuses WHERE code = 'DELETED'").fetchone()[0]
        expires = (_now() + timedelta(days=retention_days)).isoformat(timespec="seconds") if retention_days else None
        cursor = self.conn.execute(
            "INSERT INTO trash_items (catalog_account_id, original_rel, trash_rel, previous_status_id, files, bytes,"
            " deleted_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUARANTINED')",
            (account_id, row["rel_path"], trash_rel, row["status_id"], files, size, _now().isoformat(timespec="seconds"), expires),
        )
        self.conn.execute(
            "UPDATE catalog_accounts SET previous_rel_path = rel_path, rel_path = NULL, disk_state = 'TRASHED',"
            " status_id = ?, deleted_at = ?, updated_at = ? WHERE id = ?",
            (deleted_id, _now().isoformat(timespec="seconds"), _now().isoformat(timespec="seconds"), account_id),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def restore(self, item_id: int) -> None:
        item = self._item(item_id)
        if item["status"] != QUARANTINED:
            raise TrashError("El elemento ya no esta en la papelera")
        if not self.fs.is_online():
            raise TrashError("La biblioteca (G:) no esta disponible")
        source, target = self.fs.abs(item["trash_rel"]), self.fs.abs(item["original_rel"])
        if not os.path.isdir(source):
            raise TrashError("La carpeta ya no esta en la papelera")
        if os.path.exists(target) or self.conn.execute(
            "SELECT 1 FROM catalog_accounts WHERE lower(rel_path) = lower(?)", (item["original_rel"],)
        ).fetchone():
            raise TrashError("El sitio original esta ocupado: libera esa carpeta primero")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(source, target)
        self.conn.execute(
            "UPDATE catalog_accounts SET rel_path = ?, disk_state = 'PRESENT', status_id = COALESCE(?, status_id),"
            " deleted_at = NULL, updated_at = ? WHERE id = ?",
            (item["original_rel"], item["previous_status_id"], _now().isoformat(timespec="seconds"), item["catalog_account_id"]),
        )
        self.conn.execute("UPDATE trash_items SET status = 'RESTORED' WHERE id = ?", (item_id,))
        self.conn.commit()

    def purge(self, item_ids: list[int] | None, confirm_word: str) -> tuple[int, int, int]:
        """Delete for good. Returns ``(items, files, bytes)``. Needs the typed confirmation word."""

        if confirm_word.strip() != CONFIRM_WORD:
            raise TrashError(f"Escribe {CONFIRM_WORD} para confirmar")
        if not self.fs.is_online():
            raise TrashError("La biblioteca (G:) no esta disponible")
        items = [i for i in self.list_items() if item_ids is None or i.id in item_ids]
        files = size = 0
        for item in items:
            folder = self.fs.abs(item.trash_rel)
            if os.path.isdir(folder):
                shutil.rmtree(folder)
            files += item.files
            size += item.bytes
            self.conn.execute("UPDATE trash_items SET status = 'PURGED' WHERE id = ?", (item.id,))
        self.conn.commit()
        return len(items), files, size

    def expired(self) -> list[TrashItem]:
        now = _now().isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT id FROM trash_items WHERE status = 'QUARANTINED' AND expires_at IS NOT NULL AND expires_at <= ?", (now,)
        ).fetchall()
        ids = {int(r[0]) for r in rows}
        return [i for i in self.list_items() if i.id in ids]

    # ------------------------------------------------------------ queries
    def _item(self, item_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM trash_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise TrashError("Elemento de la papelera no encontrado")
        return row

    def list_items(self) -> list[TrashItem]:
        rows = self.conn.execute(
            "SELECT t.*, a.username FROM trash_items t JOIN catalog_accounts a ON a.id = t.catalog_account_id"
            " WHERE t.status = 'QUARANTINED' ORDER BY t.id DESC"
        ).fetchall()
        return [
            TrashItem(int(r["id"]), int(r["catalog_account_id"]), str(r["username"]), str(r["original_rel"]),
                      str(r["trash_rel"]), int(r["files"] or 0), int(r["bytes"] or 0), str(r["deleted_at"]), str(r["status"]))
            for r in rows
        ]

    def absolute(self, trash_rel: str) -> str:
        return to_abs(trash_rel, self.fs.root)
