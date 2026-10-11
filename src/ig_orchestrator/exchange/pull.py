"""Plan and execute a verified copy/move of account folders into WORKING."""

from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ig_orchestrator.exchange.inbox_scan import (
    PART_SUFFIX,
    ExchangeFolder,
    iter_files,
    long_path,
)


class PullPolicy(StrEnum):
    MERGE_SKIP_IDENTICAL = "merge_skip_identical"
    ABORT = "abort"


class FileAction(StrEnum):
    COPY = "COPY"
    SKIP_IDENTICAL = "SKIP_IDENTICAL"
    COPY_SUFFIXED = "COPY_SUFFIXED"


@dataclass(frozen=True, slots=True)
class FilePlan:
    source: Path
    destination: Path
    size: int
    action: FileAction


@dataclass(slots=True)
class FolderPlan:
    folder: ExchangeFolder
    destination: Path
    files: list[FilePlan] = field(default_factory=list)
    blocked_reason: str = ""

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files if f.action is not FileAction.SKIP_IDENTICAL)


@dataclass(slots=True)
class PullPlan:
    folders: list[FolderPlan]
    keep_source: bool
    policy: PullPolicy
    required_bytes: int = 0
    free_bytes: int | None = None

    @property
    def has_enough_space(self) -> bool:
        return self.free_bytes is None or self.free_bytes >= self.required_bytes


@dataclass(slots=True)
class FolderResult:
    name: str
    copied: int = 0
    skipped_identical: int = 0
    renamed: int = 0
    bytes_copied: int = 0
    errors: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    completed: bool = False


@dataclass(slots=True)
class PullResult:
    folders: list[FolderResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not self.cancelled and all(
            f.completed and not f.errors for f in self.folders if not f.blocked_reason
        )


ProgressCallback = Callable[[str, int, int], None]  # folder, files_done, files_total


def _unique_destination(path: Path, taken: set[str]) -> Path:
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not os.path.exists(long_path(candidate)) and str(candidate) not in taken:
            return candidate
        counter += 1


def _existing_case_variant(dest_root: Path, name: str) -> Path:
    """Reuse an existing destination folder that differs only by case."""

    direct = dest_root / name
    if not dest_root.is_dir():
        return direct
    folded = name.casefold()
    try:
        with os.scandir(dest_root) as scan:
            for entry in scan:
                if entry.name.casefold() == folded and entry.is_dir():
                    return dest_root / entry.name
    except OSError:
        pass
    return direct


def plan_pull(
    folders: list[ExchangeFolder],
    dest_root: Path,
    policy: PullPolicy = PullPolicy.MERGE_SKIP_IDENTICAL,
    *,
    keep_source: bool = False,
) -> PullPlan:
    """Decide, per file, whether it is copied, skipped or renamed (``_1`` suffix)."""

    plans: list[FolderPlan] = []
    for folder in folders:
        dest = _existing_case_variant(dest_root, folder.name)
        plan = FolderPlan(folder=folder, destination=dest)
        if folder.is_empty:
            plan.blocked_reason = "Vacia"
        elif dest.exists() and policy is PullPolicy.ABORT:
            plan.blocked_reason = "Ya existe en destino"
        else:
            taken: set[str] = set()
            for rel, size, _mtime in iter_files(folder.path):
                target = dest / rel
                action = FileAction.COPY
                if os.path.exists(long_path(target)):
                    if os.stat(long_path(target)).st_size == size:
                        action = FileAction.SKIP_IDENTICAL
                    else:
                        target = _unique_destination(target, taken)
                        action = FileAction.COPY_SUFFIXED
                taken.add(str(target))
                plan.files.append(FilePlan(folder.path / rel, target, size, action))
        plans.append(plan)

    required = sum(p.total_bytes for p in plans if not p.blocked_reason)
    try:
        probe = dest_root if dest_root.exists() else dest_root.parent
        free: int | None = shutil.disk_usage(probe).free
    except OSError:
        free = None
    return PullPlan(plans, keep_source, policy, required_bytes=required, free_bytes=free)


def _remove_orphan_parts(folder: Path) -> None:
    if not folder.is_dir():
        return
    for current, _dirs, names in os.walk(long_path(folder)):
        for name in names:
            if name.endswith(PART_SUFFIX):
                try:
                    os.remove(os.path.join(current, name))
                except OSError:
                    pass


def _copy_verified(source: Path, destination: Path, size: int) -> None:
    os.makedirs(long_path(destination.parent), exist_ok=True)
    part = Path(str(destination) + PART_SUFFIX)
    try:
        shutil.copy2(long_path(source), long_path(part))
        if os.stat(long_path(part)).st_size != size:
            raise OSError(f"Tamano distinto tras copiar: {source.name}")
        os.replace(long_path(part), long_path(destination))
    except BaseException:
        try:
            os.remove(long_path(part))
        except OSError:
            pass
        raise


def _prune_empty_dirs(folder: Path) -> None:
    for current, _dirs, _files in os.walk(long_path(folder), topdown=False):
        try:
            os.rmdir(current)  # fails (and is ignored) while the folder has content
        except OSError:
            pass


def execute_pull(
    plan: PullPlan,
    *,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> PullResult:
    """Run the plan. Cancelling leaves unprocessed source files and no ``.part`` files."""

    result = PullResult()
    cancel = cancel_event or threading.Event()
    for folder_plan in plan.folders:
        folder_result = FolderResult(name=folder_plan.folder.name)
        result.folders.append(folder_result)
        if folder_plan.blocked_reason:
            folder_result.blocked_reason = folder_plan.blocked_reason
            continue
        if cancel.is_set():
            result.cancelled = True
            break
        _remove_orphan_parts(folder_plan.destination)
        total = len(folder_plan.files)
        for index, file_plan in enumerate(folder_plan.files, start=1):
            if cancel.is_set():
                result.cancelled = True
                break
            try:
                if file_plan.action is FileAction.SKIP_IDENTICAL:
                    folder_result.skipped_identical += 1
                else:
                    _copy_verified(file_plan.source, file_plan.destination, file_plan.size)
                    folder_result.copied += 1
                    folder_result.bytes_copied += file_plan.size
                    if file_plan.action is FileAction.COPY_SUFFIXED:
                        folder_result.renamed += 1
                if not plan.keep_source:
                    os.remove(long_path(file_plan.source))
            except OSError as exc:
                folder_result.errors.append(f"{file_plan.source.name}: {exc}")
            if progress is not None:
                progress(folder_plan.folder.name, index, total)
        if result.cancelled:
            break
        folder_result.completed = not folder_result.errors
        if not plan.keep_source and folder_result.completed:
            _prune_empty_dirs(folder_plan.folder.path)
    return result
