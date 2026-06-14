from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class ConfigValueType(StrEnum):
    TEXT = "TEXT"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    PATH = "PATH"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AppConfig:
    key: str
    value: str
    value_type: ConfigValueType
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("AppConfig.key must not be blank")
        if not self.value.strip():
            raise ValueError("AppConfig.value must not be blank")
        if not isinstance(self.value_type, ConfigValueType):
            raise ValueError("AppConfig.value_type must be a ConfigValueType")
