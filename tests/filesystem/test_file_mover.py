from __future__ import annotations

from pathlib import Path

from ig_orchestrator.filesystem import (
    move_downloaded_files,
    resolve_publication_type_after_download,
)
from ig_orchestrator.models import (
    DownloadFile,
    DownloadFileStatus,
    MediaType,
    PublicationType,
)


def _download_file(path: Path, media_type: MediaType, url_job_id: int = 1) -> DownloadFile:
    return DownloadFile(
        url_job_id=url_job_id,
        original_path=path,
        media_type=media_type,
        file_extension=path.suffix,
        status=DownloadFileStatus.DETECTED,
        file_size=path.stat().st_size,
    )


def test_move_downloaded_files_moves_reel_video_to_reels(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")

    moved = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.REEL,
        download_files=[_download_file(source, MediaType.VIDEO)],
    )

    destination = tmp_path / "working" / "example_user" / "reels" / "clip.mp4"
    assert moved[0].working_path == destination
    assert moved[0].status is DownloadFileStatus.CLASSIFIED_AS_REEL
    assert destination.read_bytes() == b"video"
    assert not source.exists()


def test_move_downloaded_files_moves_post_image_to_account_root(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"image")

    moved = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.POST,
        download_files=[_download_file(source, MediaType.IMAGE)],
    )

    destination = tmp_path / "working" / "example_user" / "photo.jpg"
    assert moved[0].working_path == destination
    assert moved[0].status is DownloadFileStatus.CLASSIFIED_AS_POST
    assert destination.read_bytes() == b"image"
    assert not (destination.parent / "story").exists()
    assert not (destination.parent / "reels").exists()
    assert not (destination.parent / "highlights").exists()


def test_move_downloaded_files_moves_story_and_highlights_to_subfolders(
    tmp_path: Path,
) -> None:
    story = tmp_path / "story.jpg"
    highlight = tmp_path / "highlight.mp4"
    story.write_bytes(b"story")
    highlight.write_bytes(b"highlight")

    moved_story = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.STORY,
        download_files=[_download_file(story, MediaType.IMAGE)],
    )
    moved_highlight = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.HIGHLIGHTS,
        download_files=[_download_file(highlight, MediaType.VIDEO, url_job_id=2)],
    )

    assert moved_story[0].working_path == (
        tmp_path / "working" / "example_user" / "story" / "story.jpg"
    )
    assert moved_story[0].status is DownloadFileStatus.CLASSIFIED_AS_STORY
    assert moved_highlight[0].working_path == (
        tmp_path / "working" / "example_user" / "highlights" / "highlight.mp4"
    )
    assert moved_highlight[0].status is DownloadFileStatus.CLASSIFIED_AS_HIGHLIGHTS


def test_move_downloaded_files_adds_safe_suffix_when_destination_exists(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"new")
    existing = tmp_path / "working" / "example_user" / "photo.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")

    moved = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.POST,
        download_files=[_download_file(source, MediaType.IMAGE)],
    )

    safe_destination = tmp_path / "working" / "example_user" / "photo_1.jpg"
    assert moved[0].working_path == safe_destination
    assert existing.read_bytes() == b"old"
    assert safe_destination.read_bytes() == b"new"


def test_reel_with_only_images_is_resolved_as_post_and_moved_to_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.webp"
    source.write_bytes(b"image")
    download_file = _download_file(source, MediaType.IMAGE)

    assert (
        resolve_publication_type_after_download(
            PublicationType.REEL,
            [download_file],
        )
        is PublicationType.POST
    )

    moved = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.REEL,
        download_files=[download_file],
    )

    assert moved[0].working_path == tmp_path / "working" / "example_user" / "photo.webp"
    assert moved[0].status is DownloadFileStatus.CLASSIFIED_AS_POST


def test_reel_with_mixed_media_keeps_video_in_reels_and_image_in_root(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "photo.jpg"
    video = tmp_path / "video.mp4"
    photo.write_bytes(b"image")
    video.write_bytes(b"video")

    moved = move_downloaded_files(
        username="example_user",
        working_folder=tmp_path / "working",
        publication_type=PublicationType.REEL,
        download_files=[
            _download_file(photo, MediaType.IMAGE),
            _download_file(video, MediaType.VIDEO, url_job_id=2),
        ],
    )

    assert moved[0].working_path == tmp_path / "working" / "example_user" / "photo.jpg"
    assert moved[0].status is DownloadFileStatus.CLASSIFIED_AS_POST
    assert moved[1].working_path == (
        tmp_path / "working" / "example_user" / "reels" / "video.mp4"
    )
    assert moved[1].status is DownloadFileStatus.CLASSIFIED_AS_REEL
