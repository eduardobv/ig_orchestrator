from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from ig_orchestrator.filesystem.folder_service import ensure_account_folders
from ig_orchestrator.models import (
    DownloadFile,
    DownloadFileStatus,
    MediaType,
    PublicationType,
)
from ig_orchestrator.models.download_file import utc_now


def resolve_publication_type_after_download(
    publication_type: PublicationType,
    download_files: list[DownloadFile],
) -> PublicationType:
    """Return the final URL type after inspecting downloaded files."""

    if (
        publication_type is PublicationType.REEL
        and download_files
        and all(file.media_type is MediaType.IMAGE for file in download_files)
    ):
        return PublicationType.POST
    return publication_type


def move_downloaded_files(
    username: str,
    working_folder: Path | str,
    publication_type: PublicationType,
    download_files: list[DownloadFile],
) -> list[DownloadFile]:
    """Move downloaded files into the account folder and return updated models."""

    if not isinstance(publication_type, PublicationType):
        raise ValueError("publication_type must be a PublicationType")

    account_folders = ensure_account_folders(username, working_folder)
    effective_type = resolve_publication_type_after_download(
        publication_type,
        download_files,
    )

    moved_files: list[DownloadFile] = []
    for download_file in download_files:
        if not download_file.original_path.is_file():
            raise FileNotFoundError(
                f"downloaded file does not exist: {download_file.original_path}"
            )

        target_folder, status = _destination_for_file(
            account_root=account_folders.root,
            story_folder=account_folders.story,
            reels_folder=account_folders.reels,
            highlights_folder=account_folders.highlights,
            publication_type=effective_type,
            media_type=download_file.media_type,
        )
        destination = _safe_destination(target_folder / download_file.original_path.name)
        shutil.move(str(download_file.original_path), str(destination))

        moved_files.append(
            replace(
                download_file,
                working_path=destination,
                status=status,
                file_size=destination.stat().st_size,
                updated_at=utc_now(),
            )
        )

    return moved_files


def _destination_for_file(
    *,
    account_root: Path,
    story_folder: Path,
    reels_folder: Path,
    highlights_folder: Path,
    publication_type: PublicationType,
    media_type: MediaType,
) -> tuple[Path, DownloadFileStatus]:
    if publication_type is PublicationType.STORY:
        return story_folder, DownloadFileStatus.CLASSIFIED_AS_STORY
    if publication_type is PublicationType.HIGHLIGHTS:
        return highlights_folder, DownloadFileStatus.CLASSIFIED_AS_HIGHLIGHTS
    if publication_type is PublicationType.REEL and media_type is MediaType.VIDEO:
        return reels_folder, DownloadFileStatus.CLASSIFIED_AS_REEL
    if publication_type in {PublicationType.POST, PublicationType.REEL}:
        return account_root, DownloadFileStatus.CLASSIFIED_AS_POST
    return account_root, DownloadFileStatus.MOVED_TO_WORKING_FOLDER


def _safe_destination(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
