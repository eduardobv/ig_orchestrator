"""Folder-tree processing of one account (port of ``sc2`` ``folder_processor.py`` + ``file_utils`` renaming).

All disk effects go through a ``FileOps`` object so the very same code path serves:

* ``DryOps`` - computes what would happen (preview) without touching the disk, and
* ``RealOps`` - applies it.

With the same random seed and clock both produce the same names.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ig_orchestrator.renaming.files import (
    FILENAME_MANUAL_RE,
    ConsultItem,
    consult_files_structure,
    find_media_files,
    group_manual_files_by_prefix,
)
from ig_orchestrator.renaming.timeline import (
    TimelineContext,
    assign_dates_for_new_entries,
    assign_dates_to_manual_tuples,
    build_combined_timeline,
    build_new_basename,
    generate_descending_times,
    user_id_of_entry,
)

Emit = Callable[[str], None]


class ConsultProvider(Protocol):
    def items(self, rel: str) -> list[ConsultItem] | None:
        """Reference files for the (sub)folder *rel* of the account, or ``None`` if that folder does not exist."""


class DiskConsultProvider:
    """Reference timeline read from the account folder in the library (what ``sc2`` does)."""

    def __init__(self, consult_folder: str) -> None:
        self.consult_folder = consult_folder

    def items(self, rel: str) -> list[ConsultItem] | None:
        path = os.path.join(self.consult_folder, rel) if rel else self.consult_folder
        if not os.path.isdir(path):
            return None
        return consult_files_structure(path)


class FileOps(Protocol):
    def exists(self, path: str) -> bool: ...

    def rename(self, old: str, new: str) -> None: ...


class RealOps:
    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def rename(self, old: str, new: str) -> None:
        os.rename(old, new)


class DryOps:
    """Pretends to rename: remembers virtual names so later ``exists`` checks see them."""

    def __init__(self) -> None:
        self._created: set[str] = set()
        self._removed: set[str] = set()

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.normpath(path))

    def exists(self, path: str) -> bool:
        key = self._key(path)
        if key in self._created:
            return True
        return key not in self._removed and os.path.exists(path)

    def rename(self, old: str, new: str) -> None:
        self._removed.add(self._key(old))
        self._created.discard(self._key(old))
        self._removed.discard(self._key(new))
        self._created.add(self._key(new))


@dataclass(slots=True)
class FileAction:
    kind: str  # RENAME | DUPLICATE
    old: str
    new: str
    date: str = ""


@dataclass(slots=True)
class NewUser:
    start_init: datetime | None
    user_id: str


@dataclass(slots=True)
class TreeResult:
    actions: list[FileAction] = field(default_factory=list)
    duplicated_files: list[str] = field(default_factory=list)
    renamed_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def rename_duplicate_manual_files(files, consult_num_ids, manual_path, ops: FileOps, result: TreeResult) -> list[dict]:
    """Downloaded files whose id already exists in the library become ``{id}_duplicated.ext``."""

    remaining = []
    for name in files:
        match = FILENAME_MANUAL_RE.match(name)
        if not match:
            continue
        num_id, ext = match.group(1), match.group(2)
        num_id_int = int(num_id)
        if num_id_int in consult_num_ids:
            old_path = os.path.join(manual_path, name)
            candidate = os.path.join(manual_path, f"{num_id}_duplicated.{ext}")
            k = 1
            while ops.exists(candidate):
                candidate = os.path.join(manual_path, f"{num_id}_duplicated({k}).{ext}")
                k += 1
            try:
                ops.rename(old_path, candidate)
                result.duplicated_files.append(candidate)
                result.actions.append(FileAction("DUPLICATE", old_path, candidate))
            except OSError as exc:
                result.errors.append(f"[Duplicado] Error renombrando {name} -> {os.path.basename(candidate)}: {exc}")
            continue
        remaining.append({"filename": name, "num_id": num_id_int, "ext": ext})
    return remaining


def build_manual_groups(manual_path, consult_num_ids, ops: FileOps, result: TreeResult) -> list[list[dict]]:
    files = find_media_files(manual_path)
    remaining = rename_duplicate_manual_files(files, consult_num_ids, manual_path, ops, result)
    return group_manual_files_by_prefix(remaining)


def find_unique_filepath(base_path: str, folder: str, ops: FileOps) -> str:
    if not ops.exists(base_path):
        return base_path
    base_name, ext = os.path.splitext(os.path.basename(base_path))
    i = 1
    while True:
        candidate = os.path.join(folder, f"{base_name}({i}){ext}")
        if not ops.exists(candidate):
            return candidate
        i += 1


def rename_manual_files(entries, manual_root, relpath, ops: FileOps, ctx: TimelineContext, result: TreeResult) -> None:
    for entry in entries:
        if entry["source"] != "manual":
            continue
        fecha = entry["fecha"]
        user_id = user_id_of_entry(entry, ctx)
        items = entry["items"]
        times = generate_descending_times(fecha, len(items))
        for item, item_time in zip(items, times):
            date_str = item_time.strftime("%Y-%m-%d %H.%M.%S")
            new_basename = build_new_basename(date_str, item["num_id"], user_id, item["ext"])
            folder = os.path.join(manual_root, relpath) if relpath else manual_root
            old_path = os.path.join(folder, item["filename"])
            new_path = find_unique_filepath(os.path.join(folder, new_basename), folder, ops)
            try:
                ops.rename(old_path, new_path)
                result.renamed_files.append(new_path)
                result.actions.append(FileAction("RENAME", old_path, new_path, date_str))
            except OSError as exc:
                result.errors.append(f"Error renombrando {item['filename']} -> {os.path.basename(new_path)}: {exc}")


def process_new_manual_files(manual_path, manual_root, relpath, new_user: NewUser, ops, ctx, result) -> None:
    start_date = new_user.start_init
    if not start_date:
        result.warnings.append("Cuenta nueva sin fecha de inicio: no se renombra")
        return
    end_date = ctx.now
    if end_date < start_date:
        result.warnings.append("startNowDate es anterior a la fecha de inicio de la cuenta: se usa la de inicio")
        end_date = start_date
    groups = build_manual_groups(manual_path, set(), ops, result)
    if not groups:
        return
    combined = build_combined_timeline([], groups)
    assign_dates_for_new_entries(combined, start_date, end_date)
    rename_manual_files(combined, manual_root, relpath, ops, ctx, result)


def process_folder_tree(
    manual_root: str,
    provider: ConsultProvider,
    ops: FileOps,
    ctx: TimelineContext,
    new_user: NewUser | None,
    result: TreeResult | None = None,
    relpath: str = "",
) -> TreeResult:
    result = result if result is not None else TreeResult()
    manual_path = os.path.join(manual_root, relpath) if relpath else manual_root
    if not os.path.isdir(manual_path):
        return result

    consult = provider.items(relpath)
    flag_new = ctx.flag_new and new_user is not None
    if consult is None:
        result.warnings.append(f"No existe la carpeta de referencia para '{relpath or '.'}'")
        if flag_new:
            process_new_manual_files(manual_path, manual_root, relpath, new_user, ops, ctx, result)
    else:
        consult_ids = {item.num_id for item in consult}
        groups = build_manual_groups(manual_path, consult_ids, ops, result)
        if groups and consult:
            combined = build_combined_timeline(consult, groups)
            assign_dates_to_manual_tuples(combined, ctx)
            rename_manual_files(combined, manual_root, relpath, ops, ctx, result)
        elif groups and not consult:
            if flag_new:
                process_new_manual_files(manual_path, manual_root, relpath, new_user, ops, ctx, result)
            else:
                result.warnings.append(f"La carpeta de referencia '{relpath or '.'}' no tiene ficheros validos: no se renombra")

    try:
        for entry in os.listdir(manual_path):
            if entry in (".", ".."):
                continue
            if os.path.isdir(os.path.join(manual_path, entry)):
                process_folder_tree(
                    manual_root, provider, ops, ctx, new_user, result, os.path.join(relpath, entry) if relpath else entry
                )
    except OSError as exc:
        result.errors.append(f"Error procesando subcarpetas de {manual_path}: {exc}")
    return result
