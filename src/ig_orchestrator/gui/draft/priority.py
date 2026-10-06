"""Account priority ranks for the current-batch table.

Rank ``0`` means unprioritized. Rank ``1`` is first in the list. The UI today
exposes a single exclusive rank-1 checkbox; ``assign_exclusive_priority``
clears any other account that already has that rank. A later UI can call it
with rank 2, 3, … or replace it with a shift-down helper without changing
``AccountDraft.priority``.
"""

from __future__ import annotations

from dataclasses import replace

from ig_orchestrator.gui.draft.models import AccountDraft
from ig_orchestrator.gui.draft.service import normalize_username

PRIORITY_NONE = 0
PRIORITY_HIGHEST = 1


def clamp_priority(value: object) -> int:
    try:
        rank = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return PRIORITY_NONE
    return rank if rank > 0 else PRIORITY_NONE


def username_key(username: str) -> str:
    return normalize_username(username).casefold()


def assign_exclusive_priority(
    accounts: list[AccountDraft],
    username: str,
    rank: int = PRIORITY_HIGHEST,
) -> list[AccountDraft]:
    """Set *username* to *rank* and clear anyone else that currently has *rank*."""

    target_rank = clamp_priority(rank)
    if target_rank == PRIORITY_NONE:
        updated = [
            replace(account, priority=PRIORITY_NONE)
            if username_key(account.username) == username_key(username)
            else account
            for account in accounts
        ]
        return ordered_accounts_for_display(updated)

    target = username_key(username)
    updated: list[AccountDraft] = []
    for account in accounts:
        if username_key(account.username) == target:
            updated.append(replace(account, priority=target_rank))
        elif clamp_priority(account.priority) == target_rank:
            updated.append(replace(account, priority=PRIORITY_NONE))
        else:
            updated.append(account)
    return ordered_accounts_for_display(updated)


def ordered_accounts_for_display(
    accounts: list[AccountDraft],
) -> list[AccountDraft]:
    """Ranked accounts first (1, 2, 3…); the rest keep their relative order."""

    ranked: list[tuple[int, int, AccountDraft]] = []
    rest: list[AccountDraft] = []
    for index, account in enumerate(accounts):
        priority = clamp_priority(account.priority)
        if priority > 0:
            ranked.append((priority, index, account))
        else:
            rest.append(account)
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [account for _priority, _index, account in ranked] + rest


__all__ = [
    "PRIORITY_HIGHEST",
    "PRIORITY_NONE",
    "assign_exclusive_priority",
    "clamp_priority",
    "ordered_accounts_for_display",
    "username_key",
]
