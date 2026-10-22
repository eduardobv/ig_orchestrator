"""Move a renamed download folder into the library (port of ``sc2`` ``move_renamed_folders``).

The destination is the **parent of the account's library folder** plus the downloaded folder's name.
If it already exists the contents are merged without overwriting: any name clash aborts that account.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

MOVED, SKIPPED, FAILED = "MOVED", "SKIPPED", "FAILED"


@dataclass(slots=True)
class MoveResult:
    status: str
    destination: str = ""
    conflicts: list[str] = field(default_factory=list)
    detail: str = ""


def find_directory_merge_conflicts(source: str, destination: str) -> list[str]:
    conflicts = []
    for current_root, dirnames, filenames in os.walk(source):
        rel_root = os.path.relpath(current_root, source)
        destination_root = destination if rel_root == "." else os.path.join(destination, rel_root)
        for dirname in dirnames:
            target = os.path.join(destination_root, dirname)
            if os.path.exists(target) and not os.path.isdir(target):
                conflicts.append(target)
        for filename in filenames:
            target = os.path.join(destination_root, filename)
            if os.path.exists(target):
                conflicts.append(target)
    return conflicts


def merge_directory_contents(source: str, destination: str) -> None:
    os.makedirs(destination, exist_ok=True)
    for entry in os.listdir(source):
        source_path = os.path.join(source, entry)
        destination_path = os.path.join(destination, entry)
        if os.path.isdir(source_path) and os.path.isdir(destination_path):
            merge_directory_contents(source_path, destination_path)
        else:
            shutil.move(source_path, destination_path)
    os.rmdir(source)


def destination_for(source: str, account_folder: str) -> str:
    return os.path.join(os.path.dirname(account_folder), os.path.basename(source))


def preview_move(source: str, account_folder: str) -> MoveResult:
    """What ``move_renamed_folder`` would do (no changes)."""

    return preview_move_to(source, destination_for(source, account_folder))


def preview_move_to(source: str, destination: str) -> MoveResult:
    if os.path.exists(destination) and not os.path.isdir(destination):
        return MoveResult(FAILED, destination, detail="el destino existe y no es una carpeta")
    if not os.path.isdir(source):
        return MoveResult(FAILED, destination, detail="el origen no es una carpeta")
    if os.path.isdir(destination):
        conflicts = find_directory_merge_conflicts(source, destination)
        if conflicts:
            return MoveResult(FAILED, destination, conflicts, "hay ficheros que chocan con los del destino")
    return MoveResult(MOVED, destination)


def move_renamed_folder(source: str, account_folder: str) -> MoveResult:
    return move_folder_to(source, destination_for(source, account_folder))


def move_folder_to(source: str, destination: str) -> MoveResult:
    planned = preview_move_to(source, destination)
    if planned.status != MOVED:
        return planned
    try:
        if os.path.isdir(destination):
            merge_directory_contents(source, destination)
        else:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.move(source, destination)
    except OSError as exc:
        return MoveResult(FAILED, destination, detail=str(exc))
    return MoveResult(MOVED, destination)
