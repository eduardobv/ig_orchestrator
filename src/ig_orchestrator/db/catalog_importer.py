from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PureWindowsPath
from sqlite3 import Connection

from ig_orchestrator.db.account_history_repository import AccountHistoryRepository
from ig_orchestrator.models.account_history import AccountHistory


@dataclass(frozen=True, slots=True)
class CatalogImportResult:
    folders_created: int
    accounts_imported: int
    accounts_without_path: int


def split_destination_path(raw: str | None) -> tuple[str, ...]:
    """Split account_history.field1 into GUI tree segments.

    ``G:\\4K Stogram\\00.FAVORITES\\Valeria-Makusheva`` becomes
    ``('G:\\\\4K Stogram', '00.FAVORITES', 'Valeria-Makusheva')``.
    The drive and first folder stay together as the tree root.
    """

    if raw is None:
        return ()
    text = raw.strip()
    if not text:
        return ()
    parts = PureWindowsPath(text).parts
    if len(parts) >= 2:
        root = str(PureWindowsPath(parts[0], parts[1]))
        return (root, *parts[2:])
    return parts


def import_catalog_from_v1(
    v1_connection: Connection,
    gui_connection: Connection,
) -> CatalogImportResult:
    """Copy account_history into catalog_folders + catalog_accounts.

    Preserves catalog account ids. Does not import batches, URLs, runs or files.
    Does not write to the v1 connection.
    """

    status_ids = _status_ids_by_code(gui_connection)
    now = datetime.now(timezone.utc).isoformat()
    folder_ids: dict[str, int] = {}
    folders_created = 0
    accounts_imported = 0
    accounts_without_path = 0

    records = AccountHistoryRepository(v1_connection).list_all()
    for record in records:
        folder_id = None
        segments = split_destination_path(record.field1)
        if segments:
            parent_id = None
            current_path = ""
            for depth, name in enumerate(segments):
                current_path = (
                    name
                    if depth == 0
                    else str(PureWindowsPath(current_path) / name)
                )
                folder_id, created = _get_or_create_folder(
                    gui_connection,
                    folder_ids,
                    parent_id=parent_id,
                    name=name,
                    full_path=current_path,
                    depth=depth,
                    now=now,
                )
                folders_created += int(created)
                parent_id = folder_id
        else:
            accounts_without_path += 1

        _upsert_catalog_account(
            gui_connection,
            record=record,
            folder_id=folder_id,
            status_id=_status_id_for(record, status_ids),
            now=now,
        )
        accounts_imported += 1

    gui_connection.commit()
    return CatalogImportResult(
        folders_created=folders_created,
        accounts_imported=accounts_imported,
        accounts_without_path=accounts_without_path,
    )


def _status_ids_by_code(connection: Connection) -> dict[str, int]:
    rows = connection.execute(
        "SELECT id, code FROM catalog_account_statuses"
    ).fetchall()
    return {str(row["code"]): int(row["id"]) for row in rows}


def _status_id_for(record: AccountHistory, status_ids: dict[str, int]) -> int:
    code = record.status.value
    status_id = status_ids.get(code)
    if status_id is None:
        raise RuntimeError(f"Unknown catalog status code: {code}")
    return status_id


def _get_or_create_folder(
    connection: Connection,
    cache: dict[str, int],
    *,
    parent_id: int | None,
    name: str,
    full_path: str,
    depth: int,
    now: str,
) -> tuple[int, bool]:
    cached = cache.get(full_path)
    if cached is not None:
        return cached, False
    row = connection.execute(
        "SELECT id FROM catalog_folders WHERE full_path = ?",
        (full_path,),
    ).fetchone()
    if row is not None:
        folder_id = int(row["id"])
        cache[full_path] = folder_id
        return folder_id, False
    cursor = connection.execute(
        """
        INSERT INTO catalog_folders (
            parent_id, name, full_path, depth, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (parent_id, name, full_path, depth, now, now),
    )
    folder_id = int(cursor.lastrowid)
    cache[full_path] = folder_id
    return folder_id, True


def _upsert_catalog_account(
    connection: Connection,
    *,
    record: AccountHistory,
    folder_id: int | None,
    status_id: int,
    now: str,
) -> None:
    if record.id is None:
        raise RuntimeError(f"Catalog source row has no id: {record.user_name}")
    created_at = record.created_at.isoformat()
    updated_at = record.updated_at.isoformat()
    connection.execute(
        """
        INSERT INTO catalog_accounts (
            id, username, instagram_user_id, folder_id, start_init_date,
            status_id, is_favorite, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username = excluded.username,
            instagram_user_id = excluded.instagram_user_id,
            folder_id = excluded.folder_id,
            start_init_date = excluded.start_init_date,
            status_id = excluded.status_id,
            is_favorite = excluded.is_favorite,
            updated_at = excluded.updated_at
        """,
        (
            record.id,
            record.user_name,
            record.user_ig_id,
            folder_id,
            record.field2,
            status_id,
            int(record.is_favorite),
            created_at,
            updated_at or now,
        ),
    )


__all__ = [
    "CatalogImportResult",
    "import_catalog_from_v1",
    "split_destination_path",
]
