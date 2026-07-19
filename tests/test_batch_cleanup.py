from pathlib import Path

from ig_orchestrator.filesystem import cleanup_batch_artifacts


def test_cleanup_removes_top_level_telegram_media_files(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    temporary = downloads / "telegram_media_42-20260718.mp4"
    temporary.write_bytes(b"temporary")
    nested = downloads / "account" / "telegram_media_actual.mp4"
    nested.parent.mkdir()
    nested.write_bytes(b"keep")

    result = cleanup_batch_artifacts(
        telegram_download_folder=downloads,
        account_folders=[nested.parent],
    )

    assert result.deleted_temporary_files == (temporary,)
    assert not temporary.exists()
    assert nested.is_file()


def test_cleanup_removes_verified_reel_suffix_duplicate_only(tmp_path: Path) -> None:
    account = tmp_path / "account"
    reels = account / "reels"
    reels.mkdir(parents=True)
    original = reels / "3933684510196101750.mp4"
    duplicate = reels / "3933684510196101750_1.mp4"
    orphan = reels / "orphan_1.mp4"
    outside = account / "outside_1.mp4"
    for path in (original, duplicate, orphan, outside):
        path.write_bytes(path.name.encode())

    result = cleanup_batch_artifacts(
        telegram_download_folder=None,
        account_folders=[account],
    )

    assert result.deleted_reel_duplicates == (duplicate,)
    assert original.is_file()
    assert not duplicate.exists()
    assert orphan.is_file()
    assert outside.is_file()
    assert result.errors == ()
