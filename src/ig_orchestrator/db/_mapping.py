from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from sqlite3 import Row
from typing import Any, TypeVar

TStrEnum = TypeVar("TStrEnum", bound=StrEnum)


def dump_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def load_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def dump_date(value: date) -> str:
    return value.isoformat()


def load_date(value: str) -> date:
    return date.fromisoformat(value)


def dump_path(value: Path | None) -> str | None:
    return str(value) if value is not None else None


def load_path(value: str | None) -> Path | None:
    return Path(value) if value is not None else None


def dump_enum(value: StrEnum) -> str:
    return value.value


def load_enum(enum_type: type[TStrEnum], value: str) -> TStrEnum:
    return enum_type(value)


def row_to_dict(row: Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)
