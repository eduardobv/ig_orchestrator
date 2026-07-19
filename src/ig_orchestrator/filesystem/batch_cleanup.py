from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BatchCleanupResult:
    deleted_temporary_files: tuple[Path, ...] = ()
    deleted_reel_duplicates: tuple[Path, ...] = ()
    errors: tuple[str, ...] = ()


def cleanup_batch_artifacts(
    *,
    telegram_download_folder: Path | str | None,
    account_folders: list[Path],
) -> BatchCleanupResult:
    """Remove leftover Telegram files and verified ``*_1.mp4`` reel copies."""

    deleted_temporary: list[Path] = []
    deleted_duplicates: list[Path] = []
    errors: list[str] = []

    if telegram_download_folder is not None:
        download_folder = Path(telegram_download_folder)
        if download_folder.is_dir():
            for candidate in sorted(download_folder.glob("telegram_media*")):
                if candidate.is_file():
                    _delete_file(candidate, deleted_temporary, errors)

    for account_folder in account_folders:
        reels_folder = Path(account_folder) / "reels"
        if not reels_folder.is_dir():
            continue
        for duplicate in sorted(reels_folder.glob("*_1.mp4")):
            original = duplicate.with_name(f"{duplicate.stem[:-2]}.mp4")
            if duplicate.is_file() and original.is_file():
                _delete_file(duplicate, deleted_duplicates, errors)

    return BatchCleanupResult(
        deleted_temporary_files=tuple(deleted_temporary),
        deleted_reel_duplicates=tuple(deleted_duplicates),
        errors=tuple(errors),
    )


def _delete_file(path: Path, deleted: list[Path], errors: list[str]) -> None:
    try:
        path.unlink()
    except OSError as exc:
        errors.append(f"Could not delete {path}: {exc}")
    else:
        deleted.append(path)


__all__ = ["BatchCleanupResult", "cleanup_batch_artifacts"]
