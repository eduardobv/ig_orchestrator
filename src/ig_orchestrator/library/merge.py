"""Merge one account folder into another without losing files (pure filesystem, no DB).

Rules per source file (``rel`` is its path inside the source folder):

* destination has the same name **and** size -> ``IDENTICAL``: the source copy is removed;
* destination has the same name, different size -> ``SUFFIXED``: moved as ``name_1.ext``...;
* destination has the same ``media_id`` under another name (same sub-folder) -> ``DUPLICATE``:
  moved to ``<dest>/_duplicates/<rel>`` (never deleted);
* otherwise -> ``MOVED``.

Every decision is recorded so the merge can be undone while the files are still in place.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

MEDIA_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2} (\d+)_(\d+)")
DUPLICATES_DIR = "_duplicates"

MOVED, SUFFIXED, DUPLICATE, IDENTICAL = "MOVED", "SUFFIXED", "DUPLICATE", "IDENTICAL"


@dataclass(frozen=True, slots=True)
class MergeMove:
    src: str  # relative to the source folder
    dst: str  # relative to the destination folder ('' for IDENTICAL when it was removed)
    kind: str
    size: int = 0


@dataclass(slots=True)
class MergeReport:
    moves: list[MergeMove] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(1 for m in self.moves if m.kind == kind)

    @property
    def total(self) -> int:
        return len(self.moves)

    def summary(self) -> str:
        return (
            f"{self.count(MOVED)} se mueven, {self.count(IDENTICAL)} identicos (se retiran del origen), "
            f"{self.count(DUPLICATE)} duplicados semanticos (a {DUPLICATES_DIR}), "
            f"{self.count(SUFFIXED)} con sufijo por conflicto de tamano"
        )

    def to_json(self) -> str:
        return json.dumps([[m.src, m.dst, m.kind, m.size] for m in self.moves], ensure_ascii=False)

    @staticmethod
    def from_json(text: str) -> "MergeReport":
        return MergeReport([MergeMove(a, b, c, int(d)) for a, b, c, d in json.loads(text)])


def media_id(name: str) -> str | None:
    match = MEDIA_ID_RE.match(name)
    return match.group(1) if match else None


def _walk(folder: Path):
    base = str(folder)
    for current, _dirs, names in os.walk(base):
        for name in names:
            full = os.path.join(current, name)
            yield os.path.relpath(full, base), full


def _unique(path_rel: str, taken: set[str], exists) -> str:
    stem, ext = os.path.splitext(path_rel)
    counter = 1
    candidate = path_rel
    while candidate.lower() in taken or exists(candidate):
        candidate = f"{stem}_{counter}{ext}"
        counter += 1
    return candidate


def plan_merge(src_dir: Path, dst_dir: Path) -> MergeReport:
    """Decide every move without touching the disk."""

    dst_files: dict[str, int] = {}
    ids: dict[tuple[str, str], set[str]] = {}
    for rel, full in _walk(dst_dir):
        dst_files[rel.lower()] = os.path.getsize(full)
        mid = media_id(os.path.basename(rel))
        if mid:
            ids.setdefault((_sub(rel), mid), set()).add(os.path.basename(rel).lower())
    taken: set[str] = set(dst_files)
    report = MergeReport()
    for rel, full in sorted(_walk(src_dir)):
        size = os.path.getsize(full)
        name = os.path.basename(rel)
        key = rel.lower()
        if key in dst_files:
            if dst_files[key] == size:
                report.moves.append(MergeMove(rel, "", IDENTICAL, size))
                continue
            target = _unique(rel, taken, lambda c: False)
            taken.add(target.lower())
            report.moves.append(MergeMove(rel, target, SUFFIXED, size))
            continue
        mid = media_id(name)
        same_media = ids.get((_sub(rel), mid)) if mid else None
        if same_media and name.lower() not in same_media:
            target = _unique(os.path.join(DUPLICATES_DIR, rel), taken, lambda c: False)
            taken.add(target.lower())
            report.moves.append(MergeMove(rel, target, DUPLICATE, size))
            continue
        taken.add(key)
        report.moves.append(MergeMove(rel, rel, MOVED, size))
    return report


def _sub(rel: str) -> str:
    parts = rel.replace("/", os.sep).split(os.sep)
    return parts[0].lower() if len(parts) > 1 else ""


def execute_merge(src_dir: Path, dst_dir: Path) -> MergeReport:
    """Run the merge (re-planned on the current state, so it is safe to resume)."""

    report = plan_merge(src_dir, dst_dir)
    for move in report.moves:
        source = src_dir / move.src
        if move.kind == IDENTICAL:
            os.remove(source)
            continue
        target = dst_dir / move.dst
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(source, target)
        except OSError:
            shutil.move(str(source), str(target))
    prune_empty(src_dir)
    return report


def prune_empty(folder: Path) -> None:
    """Remove *folder* and its empty sub-folders (stops at the first one with content)."""

    for current, _dirs, _names in os.walk(folder, topdown=False):
        try:
            os.rmdir(current)
        except OSError:
            pass


def can_undo(
    report: MergeReport, src_dir: Path, dst_dir: Path, *, check_src: bool = True
) -> tuple[bool, str]:
    """True while every moved file is still where the merge left it.

    ``check_src=False`` skips the "source is free" test (the folder is about to be vacated by an undo of a later step).
    """

    for move in report.moves:
        if move.kind == IDENTICAL:
            if not (dst_dir / move.src).exists():
                return False, f"Falta la copia identica en el destino: {move.src}"
            continue
        if not (dst_dir / move.dst).exists():
            return False, f"El fichero ya no esta donde lo dejo la fusion: {move.dst}"
        if check_src and (src_dir / move.src).exists():
            return False, f"El origen ya existe de nuevo: {move.src}"
    return True, ""


def undo_merge(report: MergeReport, src_dir: Path, dst_dir: Path) -> int:
    """Put every file back; identical files are recreated from the surviving copy."""

    restored = 0
    src_dir.mkdir(parents=True, exist_ok=True)
    for move in report.moves:
        source = src_dir / move.src
        source.parent.mkdir(parents=True, exist_ok=True)
        if move.kind == IDENTICAL:
            shutil.copy2(dst_dir / move.src, source)
        else:
            try:
                os.rename(dst_dir / move.dst, source)
            except OSError:
                shutil.move(str(dst_dir / move.dst), str(source))
        restored += 1
    duplicates = dst_dir / DUPLICATES_DIR
    if duplicates.is_dir():
        prune_empty(duplicates)
    return restored
