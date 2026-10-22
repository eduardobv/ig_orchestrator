"""Plan model and name validation for library disk operations (no I/O here)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class OpType(StrEnum):
    MKDIR = "MKDIR"
    MOVE_DIR = "MOVE_DIR"
    RENAME_DIR = "RENAME_DIR"
    RMDIR = "RMDIR"  # only used to undo a MKDIR (empty folders only)
    MERGE_DIR = "MERGE_DIR"  # merge the files of src_rel into the folder dst_rel, then remove src_rel
    UNMERGE_DIR = "UNMERGE_DIR"  # undo of MERGE_DIR (uses the recorded payload)


class OpStatus(StrEnum):
    PLANNED = "PLANNED"
    DISK_DONE = "DISK_DONE"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    UNDONE = "UNDONE"


@dataclass(frozen=True, slots=True)
class Step:
    op_type: OpType
    src_rel: str | None
    dst_rel: str | None
    account_id: int | None = None
    payload: str | None = None  # merge manifest (JSON) for MERGE_DIR / UNMERGE_DIR


@dataclass(frozen=True, slots=True)
class Conflict:
    code: str
    message: str
    blocking: bool = True


@dataclass(slots=True)
class Plan:
    title: str
    steps: list[Step] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    affected_accounts: int = 0
    affected_folders: int = 0

    @property
    def blocking(self) -> list[Conflict]:
        return [c for c in self.conflicts if c.blocking]

    @property
    def can_execute(self) -> bool:
        return bool(self.steps) and not self.blocking


_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_name(name: str) -> str | None:
    """Return a human-readable problem for a Windows folder name, or ``None`` if valid."""

    if not name or not name.strip():
        return "El nombre no puede estar vacio"
    if name != name.strip() or name.endswith("."):
        return "El nombre no puede empezar/terminar con espacio ni terminar en punto"
    if _INVALID_CHARS.search(name):
        return 'El nombre contiene caracteres no validos (< > : " / \\ | ? *)'
    if name.split(".")[0].upper() in _RESERVED:
        return "Nombre reservado de Windows"
    if len(name) > 200:
        return "El nombre es demasiado largo"
    return None
