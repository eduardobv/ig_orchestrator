from __future__ import annotations

from pathlib import Path

import pytest

from ig_orchestrator.filesystem import AccountFolderPaths, ensure_account_folders


def test_ensure_account_folders_creates_only_account_root(tmp_path: Path) -> None:
    paths = ensure_account_folders("example_user", tmp_path)

    assert paths == AccountFolderPaths(
        root=tmp_path / "example_user",
        story=tmp_path / "example_user" / "story",
        reels=tmp_path / "example_user" / "reels",
        highlights=tmp_path / "example_user" / "highlights",
    )
    assert paths.root.is_dir()
    assert not paths.story.exists()
    assert not paths.reels.exists()
    assert not paths.highlights.exists()


def test_ensure_account_folders_preserves_existing_content(tmp_path: Path) -> None:
    root = tmp_path / "example_user"
    root.mkdir()
    existing_file = root / "already_downloaded.jpg"
    existing_file.write_text("keep me", encoding="utf-8")

    ensure_account_folders("example_user", tmp_path)

    assert existing_file.read_text(encoding="utf-8") == "keep me"


def test_ensure_account_folders_preserves_existing_subfolders_without_adding_others(
    tmp_path: Path,
) -> None:
    root = tmp_path / "example_user"
    (root / "story").mkdir(parents=True)

    paths = ensure_account_folders("example_user", tmp_path)

    assert paths.story.is_dir()
    assert not paths.reels.exists()
    assert not paths.highlights.exists()


def test_ensure_account_folders_rejects_blank_username(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="username"):
        ensure_account_folders("  ", tmp_path)
