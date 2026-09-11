from __future__ import annotations

from sqlite3 import Connection


_TABLES = {
    "catalog_account_statuses",
    "batch_statuses",
    "batch_account_statuses",
    "batch_url_statuses",
    "batch_run_statuses",
    "publication_types",
    "url_sources",
    "media_types",
    "queue_statuses",
    "queue_item_statuses",
    "downloaded_file_statuses",
    "bot_errors",
}


class LookupCache:
    """Resolve dictionary codes to ids (and back) for the GUI schema."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._code_to_id: dict[str, dict[str, int]] = {}
        self._id_to_code: dict[str, dict[int, str]] = {}

    def id_for(self, table: str, code: str) -> int:
        mapping = self._codes(table)
        try:
            return mapping[code]
        except KeyError as exc:
            raise RuntimeError(f"Unknown {table} code: {code}") from exc

    def code_for(self, table: str, lookup_id: int) -> str:
        mapping = self._ids(table)
        try:
            return mapping[lookup_id]
        except KeyError as exc:
            raise RuntimeError(f"Unknown {table} id: {lookup_id}") from exc

    def optional_id_for(self, table: str, code: str | None) -> int | None:
        if code is None or not code.strip():
            return None
        mapping = self._codes(table)
        return mapping.get(code)

    def _codes(self, table: str) -> dict[str, int]:
        self._load(table)
        return self._code_to_id[table]

    def _ids(self, table: str) -> dict[int, str]:
        self._load(table)
        return self._id_to_code[table]

    def _load(self, table: str) -> None:
        if table not in _TABLES:
            raise ValueError(f"Unsupported lookup table: {table}")
        if table in self._code_to_id:
            return
        rows = self.connection.execute(f"SELECT id, code FROM {table}").fetchall()
        self._code_to_id[table] = {str(row["code"]): int(row["id"]) for row in rows}
        self._id_to_code[table] = {int(row["id"]): str(row["code"]) for row in rows}


__all__ = ["LookupCache"]
