from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RenameCompletionDecision:
    """What the GUI should do after the external rename process exits."""

    mark_completed: bool
    keep_rename_enabled: bool
    leftover_folders: tuple[Path, ...] = ()


def list_unmoved_account_folders(working_folder: Path | str | None) -> list[Path]:
    """Return first-level account folders still present after a rename+move.

    The external renamer changes folder names before moving them, so this
    cannot filter by original usernames. Any remaining non-hidden directory
    in ``working_folder`` is treated as a leftover that still needs rename
    or ``--move-renamed``.
    """

    if working_folder is None:
        return []
    root = Path(working_folder)
    if not root.is_dir():
        return []

    leftovers: list[Path] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    for entry in sorted(entries, key=lambda item: item.name.casefold()):
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        if entry.name.startswith("."):
            continue
        leftovers.append(entry)
    return leftovers


def has_unmoved_account_folders(working_folder: Path | str | None) -> bool:
    return bool(list_unmoved_account_folders(working_folder))


def decide_rename_completion(
    *,
    exit_code: int,
    leftover_folders: list[Path] | tuple[Path, ...] = (),
) -> RenameCompletionDecision:
    """Decide whether a rename run can close the batch.

    Leftover folders always keep Renombrar enabled and block COMPLETED,
    even when the script exited 0 (move conflicts, unmatched folders).
    """

    leftovers = tuple(leftover_folders)
    if leftovers:
        return RenameCompletionDecision(
            mark_completed=False,
            keep_rename_enabled=True,
            leftover_folders=leftovers,
        )
    if exit_code == 0:
        return RenameCompletionDecision(
            mark_completed=True,
            keep_rename_enabled=False,
        )
    return RenameCompletionDecision(
        mark_completed=False,
        keep_rename_enabled=True,
    )


__all__ = [
    "RenameCompletionDecision",
    "decide_rename_completion",
    "has_unmoved_account_folders",
    "list_unmoved_account_folders",
]
