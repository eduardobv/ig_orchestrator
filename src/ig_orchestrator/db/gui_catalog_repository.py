from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PureWindowsPath
from sqlite3 import Connection, Row

from ig_orchestrator.db.account_history_repository import AccountHistoryRepository
from ig_orchestrator.db.catalog_importer import split_destination_path
from ig_orchestrator.db.lookups import LookupCache
from ig_orchestrator.db._mapping import load_datetime
from ig_orchestrator.models.account_history import AccountHistory, AccountHistoryStatus


_CATALOG_SELECT = """
SELECT
    ca.id,
    ca.instagram_user_id AS user_ig_id,
    ca.username AS user_name,
    cas.code AS status,
    cf.full_path AS field1,
    ca.start_init_date AS field2,
    ca.is_favorite,
    ca.created_at,
    ca.updated_at
FROM catalog_accounts ca
JOIN catalog_account_statuses cas ON cas.id = ca.status_id
LEFT JOIN catalog_folders cf ON cf.id = ca.folder_id
"""


class GuiCatalogRepository(AccountHistoryRepository):
    """account_history-compatible catalog stored in catalog_accounts."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._lookups = LookupCache(connection)

    def create_or_get(self, user_name: str) -> AccountHistory:
        normalized = user_name.strip()
        existing = self.get_by_user_name(normalized)
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        enabled_id = self._lookups.id_for("catalog_account_statuses", "ENABLED")
        cursor = self.connection.execute(
            """
            INSERT INTO catalog_accounts (
                username, status_id, is_favorite, created_at, updated_at
            )
            VALUES (?, ?, 0, ?, ?)
            """,
            (normalized, enabled_id, now, now),
        )
        self.connection.commit()
        stored = self.get_by_id(cursor.lastrowid)
        if stored is None:
            raise RuntimeError("Catalog account was not stored")
        return stored

    def get_by_id(self, history_id: int) -> AccountHistory | None:
        row = self.connection.execute(
            _CATALOG_SELECT + " WHERE ca.id = ?",
            (history_id,),
        ).fetchone()
        return _row_to_history(row)

    def get_by_user_name(self, user_name: str) -> AccountHistory | None:
        row = self.connection.execute(
            _CATALOG_SELECT + " WHERE ca.username = ? COLLATE NOCASE ORDER BY ca.id LIMIT 1",
            (user_name.strip(),),
        ).fetchone()
        return _row_to_history(row)

    def list_all(self) -> list[AccountHistory]:
        rows = self.connection.execute(
            _CATALOG_SELECT + " ORDER BY ca.id"
        ).fetchall()
        return [_row_to_history(row) for row in rows]

    def list_enabled(self) -> list[AccountHistory]:
        disabled_id = self._lookups.id_for("catalog_account_statuses", "DISABLED")
        rows = self.connection.execute(
            _CATALOG_SELECT + " WHERE ca.status_id <> ? ORDER BY ca.id",
            (disabled_id,),
        ).fetchall()
        return [_row_to_history(row) for row in rows]

    def list_disabled_user_names(self) -> set[str]:
        disabled_id = self._lookups.id_for("catalog_account_statuses", "DISABLED")
        rows = self.connection.execute(
            "SELECT username FROM catalog_accounts WHERE status_id = ?",
            (disabled_id,),
        ).fetchall()
        return {str(row["username"]).casefold() for row in rows}

    def list_distinct_destination_paths(self) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT TRIM(cf.full_path) AS destination_path
            FROM catalog_accounts ca
            JOIN catalog_folders cf ON cf.id = ca.folder_id
            WHERE TRIM(cf.full_path) <> ''
            ORDER BY destination_path COLLATE NOCASE
            """
        ).fetchall()
        return [str(row["destination_path"]) for row in rows]

    def update_status(
        self,
        user_name: str,
        status: AccountHistoryStatus,
    ) -> AccountHistory:
        record = self.get_by_user_name(user_name)
        if record is None or record.id is None:
            raise ValueError(f"Catalog account not found: {user_name}")
        status_id = self._lookups.id_for("catalog_account_statuses", status.value)
        self.connection.execute(
            """
            UPDATE catalog_accounts
            SET status_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_id, record.id),
        )
        self.connection.commit()
        stored = self.get_by_id(record.id)
        if stored is None:
            raise RuntimeError("Catalog account disappeared during update")
        return stored

    def _update_catalog_flags(
        self,
        user_name: str,
        *,
        status: AccountHistoryStatus,
        is_favorite: bool,
    ) -> AccountHistory:
        record = self.get_by_user_name(user_name)
        if record is None or record.id is None:
            raise ValueError(f"Catalog account not found: {user_name}")
        status_id = self._lookups.id_for("catalog_account_statuses", status.value)
        self.connection.execute(
            """
            UPDATE catalog_accounts
            SET status_id = ?, is_favorite = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status_id, int(is_favorite), record.id),
        )
        self.connection.commit()
        stored = self.get_by_id(record.id)
        if stored is None:
            raise RuntimeError("Catalog account disappeared during update")
        return stored

    def update_rename_metadata(
        self,
        user_name: str,
        *,
        owner_id: str,
        destination_path: str,
        start_init_date: str,
    ) -> AccountHistory:
        record = self.create_or_get(user_name)
        folder_id = _ensure_folder_path(self.connection, destination_path)
        self.connection.execute(
            """
            UPDATE catalog_accounts
            SET instagram_user_id = ?, folder_id = ?, start_init_date = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (owner_id, folder_id, start_init_date, record.id),
        )
        self.connection.commit()
        stored = self.get_by_id(record.id)
        if stored is None:
            raise RuntimeError("Catalog account disappeared during update")
        return stored

    def update_identity_and_path(
        self,
        user_name: str,
        *,
        owner_id: str,
        destination_path: str,
    ) -> AccountHistory:
        record = self.create_or_get(user_name)
        folder_id = _ensure_folder_path(self.connection, destination_path)
        self.connection.execute(
            """
            UPDATE catalog_accounts
            SET instagram_user_id = ?, folder_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (owner_id, folder_id, record.id),
        )
        self.connection.commit()
        stored = self.get_by_id(record.id)
        if stored is None:
            raise RuntimeError("Catalog account disappeared during update")
        return stored


def _ensure_folder_path(connection: Connection, destination_path: str) -> int | None:
    segments = split_destination_path(destination_path)
    if not segments:
        return None
    parent_id = None
    current_path = ""
    folder_id = None
    now = datetime.now(timezone.utc).isoformat()
    for depth, name in enumerate(segments):
        current_path = name if depth == 0 else str(PureWindowsPath(current_path) / name)
        row = connection.execute(
            "SELECT id FROM catalog_folders WHERE full_path = ?",
            (current_path,),
        ).fetchone()
        if row is None:
            cursor = connection.execute(
                """
                INSERT INTO catalog_folders (
                    parent_id, name, full_path, depth, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (parent_id, name, current_path, depth, now, now),
            )
            folder_id = int(cursor.lastrowid)
        else:
            folder_id = int(row["id"])
        parent_id = folder_id
    return folder_id


def _row_to_history(row: Row | None) -> AccountHistory | None:
    if row is None:
        return None
    created_at = load_datetime(row["created_at"])
    updated_at = load_datetime(row["updated_at"])
    if created_at is None or updated_at is None:
        raise ValueError("Stored catalog account is missing timestamps")
    return AccountHistory(
        id=row["id"],
        user_ig_id=row["user_ig_id"],
        user_name=row["user_name"],
        status=AccountHistoryStatus(row["status"]),
        field1=row["field1"],
        field2=row["field2"],
        is_favorite=bool(row["is_favorite"]),
        created_at=created_at,
        updated_at=updated_at,
    )


__all__ = ["GuiCatalogRepository"]
