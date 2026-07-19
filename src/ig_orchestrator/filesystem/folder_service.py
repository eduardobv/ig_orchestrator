from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AccountFolderPaths:
    root: Path
    story: Path
    reels: Path
    highlights: Path


def ensure_account_folders(username: str, working_folder: Path | str) -> AccountFolderPaths:
    """Ensure the account root exists without creating speculative subfolders."""
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be blank")

    base_folder = Path(working_folder)
    account_root = base_folder / normalized_username
    paths = AccountFolderPaths(
        root=account_root,
        story=account_root / "story",
        reels=account_root / "reels",
        highlights=account_root / "highlights",
    )

    paths.root.mkdir(parents=True, exist_ok=True)

    return paths
