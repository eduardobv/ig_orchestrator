"""Registry of app instances (pc1, inst1…) and the folders they share."""

from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

ROLES = ("MAIN", "WORKER")


@dataclass(frozen=True, slots=True)
class Instance:
    id: int | None
    name: str
    role: str = "WORKER"
    is_local: bool = False
    working_path: str = ""
    exchange_path: str = ""
    exchange_local_path: str = ""
    app_version: str = ""
    last_seen_at: str = ""
    notes: str = ""

    @property
    def pull_source(self) -> str:
        """Folder the main instance reads from: exchange first, then working."""

        return self.exchange_path or self.working_path


_COLUMNS = (
    "id, name, role, is_local, working_path, exchange_path, exchange_local_path,"
    " app_version, last_seen_at, notes"
)


def _from_row(row) -> Instance:
    return Instance(
        id=int(row[0]),
        name=str(row[1]),
        role=str(row[2]),
        is_local=bool(row[3]),
        working_path=str(row[4] or ""),
        exchange_path=str(row[5] or ""),
        exchange_local_path=str(row[6] or ""),
        app_version=str(row[7] or ""),
        last_seen_at=str(row[8] or ""),
        notes=str(row[9] or ""),
    )


class InstanceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list(self) -> list[Instance]:
        rows = self._connection.execute(
            f"SELECT {_COLUMNS} FROM instances ORDER BY is_local DESC, name COLLATE NOCASE"
        ).fetchall()
        return [_from_row(row) for row in rows]

    def get(self, instance_id: int) -> Instance | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM instances WHERE id = ?", (instance_id,)
        ).fetchone()
        return _from_row(row) if row else None

    def get_local(self) -> Instance | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM instances WHERE is_local = 1"
        ).fetchone()
        return _from_row(row) if row else None

    def save(self, instance: Instance) -> int:
        """Insert or update; at most one instance can be local."""

        name = instance.name.strip()
        if not name:
            raise ValueError("El nombre de la instancia es obligatorio")
        if instance.role not in ROLES:
            raise ValueError(f"Rol no valido: {instance.role}")
        values = (
            name,
            instance.role,
            1 if instance.is_local else 0,
            instance.working_path.strip() or None,
            instance.exchange_path.strip() or None,
            instance.exchange_local_path.strip() or None,
            instance.app_version.strip() or None,
            instance.last_seen_at.strip() or None,
            instance.notes.strip() or None,
        )
        try:
            if instance.id is None:
                cursor = self._connection.execute(
                    """
                    INSERT INTO instances (name, role, is_local, working_path, exchange_path,
                        exchange_local_path, app_version, last_seen_at, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                instance_id = int(cursor.lastrowid)
            else:
                self._connection.execute(
                    """
                    UPDATE instances SET name = ?, role = ?, is_local = ?, working_path = ?,
                        exchange_path = ?, exchange_local_path = ?, app_version = ?,
                        last_seen_at = ?, notes = ?
                    WHERE id = ?
                    """,
                    (*values, instance.id),
                )
                instance_id = instance.id
            if instance.is_local:
                self._connection.execute(
                    "UPDATE instances SET is_local = 0 WHERE id <> ?", (instance_id,)
                )
            self._connection.commit()
        except Exception as exc:
            self._connection.rollback()
            if "UNIQUE" in str(exc):
                raise ValueError(f"Ya existe una instancia llamada '{name}'") from exc
            raise
        return instance_id

    def delete(self, instance_id: int) -> None:
        self._connection.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
        self._connection.commit()


__all__ = ["Instance", "InstanceRepository", "ROLES"]
