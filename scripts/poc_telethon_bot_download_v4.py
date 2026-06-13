import asyncio
import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError


KNOWN_ERRORS = [
    "service is overloaded",
    "geoblock_required",
    "media not found or unavailable",
]


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass
class DownloadResult:
    message_id: int
    telegram_media_id: Optional[str]
    file_path: Optional[Path]
    file_hash: Optional[str]
    file_size: Optional[int]
    duplicated: bool
    skipped: bool
    error: Optional[str]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def ensure_login(client: TelegramClient) -> None:
    await client.connect()

    if await client.is_user_authorized():
        return

    phone = input("Enter your phone number with country code, for example +34600111222: ").strip()
    await client.send_code_request(phone)

    code = input("Enter the Telegram login code: ").strip()

    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        password = input("Two-step verification enabled. Enter your Telegram password: ").strip()
        await client.sign_in(password=password)


def sha256_file(path: Path) -> str:
    hash_obj = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


def safe_text(value) -> str:
    if value is None:
        return "<none>"
    return str(value)


def get_file_extension_from_message(message) -> str:
    document = getattr(message, "document", None)

    if document:
        mime_type = getattr(document, "mime_type", "") or ""

        for attribute in getattr(document, "attributes", []) or []:
            file_name = getattr(attribute, "file_name", None)
            if file_name:
                return Path(file_name).suffix.lower()

        if mime_type == "video/mp4":
            return ".mp4"
        if mime_type == "image/jpeg":
            return ".jpg"
        if mime_type == "image/png":
            return ".png"
        if mime_type == "image/webp":
            return ".webp"

    photo = getattr(message, "photo", None)
    if photo:
        return ".jpg"

    return ".bin"


def get_telegram_media_id(message) -> Optional[str]:
    document = getattr(message, "document", None)
    if document:
        return f"document:{document.id}"

    photo = getattr(message, "photo", None)
    if photo:
        return f"photo:{photo.id}"

    return None


def describe_message(message) -> None:
    print("")
    print("========== BOT MESSAGE ==========")
    print(f"id: {message.id}")
    print(f"date: {message.date}")
    print(f"has_media: {bool(message.media)}")
    print(f"text: {message.raw_text or '<empty>'}")

    media = getattr(message, "media", None)
    document = getattr(message, "document", None)
    photo = getattr(message, "photo", None)

    print("----- media debug -----")
    print(f"media_type: {type(media).__name__ if media else '<none>'}")
    print(f"telegram_media_id: {get_telegram_media_id(message)}")

    if document:
        print(f"document.id: {document.id}")
        print(f"document.size: {getattr(document, 'size', '<unknown>')}")
        print(f"document.mime_type: {getattr(document, 'mime_type', '<unknown>')}")

        attributes = getattr(document, "attributes", []) or []
        print(f"document.attributes.count: {len(attributes)}")

        for index, attribute in enumerate(attributes):
            print(f"attribute[{index}].type: {type(attribute).__name__}")

            file_name = getattr(attribute, "file_name", None)
            duration = getattr(attribute, "duration", None)
            w = getattr(attribute, "w", None)
            h = getattr(attribute, "h", None)

            if file_name:
                print(f"attribute[{index}].file_name: {file_name}")
            if duration is not None:
                print(f"attribute[{index}].duration: {duration}")
            if w is not None or h is not None:
                print(f"attribute[{index}].size: {safe_text(w)}x{safe_text(h)}")

    if photo:
        print(f"photo.id: {photo.id}")

    print("===============================")


async def sleep_with_trace(seconds: int, reason: str) -> None:
    for remaining in range(seconds, 0, -1):
        print(f"\rSleeping {remaining:>3}s - {reason}", end="", flush=True)
        await asyncio.sleep(1)

    print("\r" + " " * 120 + "\r", end="", flush=True)


def unique_final_path(download_folder: Path, preferred_name: str) -> Path:
    candidate = download_folder / preferred_name

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix

    counter = 1
    while True:
        candidate = download_folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


async def download_message_media(
    client: TelegramClient,
    message,
    download_folder: Path,
    temp_folder: Path,
    downloaded_hashes: dict[str, Path],
    processed_media_ids: set[str],
) -> DownloadResult:
    message_id = message.id
    telegram_media_id = get_telegram_media_id(message)

    print("")
    print("========== DOWNLOAD START ==========")
    print(f"message_id: {message_id}")
    print(f"telegram_media_id: {telegram_media_id}")

    if telegram_media_id and telegram_media_id in processed_media_ids:
        print("Result: skipped, Telegram media id already processed.")
        print("====================================")
        return DownloadResult(
            message_id=message_id,
            telegram_media_id=telegram_media_id,
            file_path=None,
            file_hash=None,
            file_size=None,
            duplicated=False,
            skipped=True,
            error=None,
        )

    if telegram_media_id:
        processed_media_ids.add(telegram_media_id)

    extension = get_file_extension_from_message(message)
    temp_file = temp_folder / f"msg_{message_id}{extension}"

    if temp_file.exists():
        temp_file.unlink()

    try:
        print(f"Temporary download target: {temp_file}")

        downloaded_path_raw = await client.download_media(
            message,
            file=str(temp_file)
        )

        if not downloaded_path_raw:
            raise RuntimeError("Telethon returned empty downloaded path.")

        downloaded_temp_path = Path(downloaded_path_raw)

        if not downloaded_temp_path.exists():
            raise RuntimeError(f"Downloaded file does not exist: {downloaded_temp_path}")

        file_size = downloaded_temp_path.stat().st_size
        file_hash = sha256_file(downloaded_temp_path)

        print(f"Downloaded temp file: {downloaded_temp_path}")
        print(f"Downloaded temp size: {file_size}")
        print(f"Downloaded temp sha256: {file_hash}")

        if file_hash in downloaded_hashes:
            original_file = downloaded_hashes[file_hash]

            print("")
            print("Duplicated file detected by SHA-256.")
            print(f"Original:  {original_file}")
            print(f"Duplicate: {downloaded_temp_path}")
            print("Deleting duplicate temp file.")

            downloaded_temp_path.unlink(missing_ok=True)

            print("========== DOWNLOAD END: DUPLICATED ==========")

            return DownloadResult(
                message_id=message_id,
                telegram_media_id=telegram_media_id,
                file_path=original_file,
                file_hash=file_hash,
                file_size=file_size,
                duplicated=True,
                skipped=False,
                error=None,
            )

        final_name = f"{message_id}{extension}"
        final_path = unique_final_path(download_folder, final_name)

        shutil.move(str(downloaded_temp_path), str(final_path))

        downloaded_hashes[file_hash] = final_path

        print(f"Moved temp file to final path: {final_path}")
        print("========== DOWNLOAD END: OK ==========")

        return DownloadResult(
            message_id=message_id,
            telegram_media_id=telegram_media_id,
            file_path=final_path,
            file_hash=file_hash,
            file_size=file_size,
            duplicated=False,
            skipped=False,
            error=None,
        )

    except Exception as exc:
        print("")
        print("Download failed.")
        print(f"message_id: {message_id}")
        print(f"error: {repr(exc)}")

        if temp_file.exists():
            try:
                print(f"Deleting partial temp file: {temp_file}")
                temp_file.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                print(f"Could not delete partial temp file: {repr(cleanup_exc)}")

        print("========== DOWNLOAD END: ERROR ==========")

        return DownloadResult(
            message_id=message_id,
            telegram_media_id=telegram_media_id,
            file_path=None,
            file_hash=None,
            file_size=None,
            duplicated=False,
            skipped=False,
            error=repr(exc),
        )


async def main() -> None:
    load_dotenv()

    api_id = int(require_env("TELEGRAM_API_ID"))
    api_hash = require_env("TELEGRAM_API_HASH")
    session_name = os.getenv("TELETHON_SESSION_NAME", "telegram_user_session")

    bot_username = require_env("TELEGRAM_DOWNLOAD_BOT_USERNAME")
    instagram_url = require_env("POC_INSTAGRAM_URL")

    download_folder = Path(require_env("POC_DOWNLOAD_FOLDER"))
    download_folder.mkdir(parents=True, exist_ok=True)

    temp_folder = download_folder / "_tmp_telethon_poc"
    temp_folder.mkdir(parents=True, exist_ok=True)

    total_timeout_seconds = int(os.getenv("POC_TOTAL_TIMEOUT_SECONDS", "180"))
    quiet_seconds_after_last_message = int(os.getenv("POC_QUIET_SECONDS_AFTER_FIRST_DOWNLOAD", "20"))

    client = TelegramClient(session_name, api_id, api_hash)
    await ensure_login(client)

    me = await client.get_me()
    print(f"Logged in as: {me.username or me.first_name} / id={me.id}")

    bot = await client.get_entity(bot_username)

    start_time = datetime.now(timezone.utc)

    message_queue: asyncio.Queue = asyncio.Queue()
    processed_message_ids: set[int] = set()
    processed_media_ids: set[str] = set()
    downloaded_hashes: dict[str, Path] = {}
    download_results: list[DownloadResult] = []

    first_media_downloaded = False
    stop_requested = False

    last_bot_message_time = asyncio.get_event_loop().time()
    started_waiting = asyncio.get_event_loop().time()

    @client.on(events.NewMessage(chats=bot))
    async def handler(event):
        nonlocal last_bot_message_time

        message = event.message

        message_date = message.date
        if message_date and message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)

        if message_date and message_date < start_time:
            print(f"Skipping old bot message id={message.id}")
            return

        if message.id in processed_message_ids:
            print(f"Skipping already queued message id={message.id}")
            return

        processed_message_ids.add(message.id)
        last_bot_message_time = asyncio.get_event_loop().time()

        print("")
        print(f"[QUEUE] New bot message queued: id={message.id}, has_media={bool(message.media)}")

        await message_queue.put(message)

    print("")
    print(f"Sending URL to bot {bot_username}:")
    print(instagram_url)

    sent = await client.send_message(bot, instagram_url)

    print("")
    print("========== SENT MESSAGE ==========")
    print(f"message_id: {sent.id}")
    print(f"date: {sent.date}")
    print(f"text: {sent.raw_text}")
    print("==================================")

    print("")
    print(f"Waiting for bot responses for up to {total_timeout_seconds} seconds...")

    while True:
        now = asyncio.get_event_loop().time()
        elapsed = int(now - started_waiting)

        if elapsed >= total_timeout_seconds:
            print("")
            print(f"Total timeout reached: {total_timeout_seconds}s.")
            break

        if stop_requested:
            print("")
            print("Stop requested. Finishing.")
            break

        try:
            message = await asyncio.wait_for(message_queue.get(), timeout=1)

            describe_message(message)

            text = (message.raw_text or "").lower()

            if any(error in text for error in KNOWN_ERRORS):
                print("Known bot error detected:")
                print(message.raw_text)
                stop_requested = True
                message_queue.task_done()
                continue

            if message.media:
                result = await download_message_media(
                    client=client,
                    message=message,
                    download_folder=download_folder,
                    temp_folder=temp_folder,
                    downloaded_hashes=downloaded_hashes,
                    processed_media_ids=processed_media_ids,
                )

                download_results.append(result)

                if result.file_path and not result.duplicated and not result.error:
                    first_media_downloaded = True

            message_queue.task_done()

        except asyncio.TimeoutError:
            queue_size = message_queue.qsize()
            now = asyncio.get_event_loop().time()

            if first_media_downloaded and queue_size == 0:
                quiet_elapsed = int(now - last_bot_message_time)
                quiet_remaining = quiet_seconds_after_last_message - quiet_elapsed

                if quiet_elapsed >= quiet_seconds_after_last_message:
                    print("")
                    print(
                        f"No new bot messages for {quiet_seconds_after_last_message}s "
                        f"and queue is empty. Finishing."
                    )
                    break

                print(
                    f"\rWaiting for extra bot media... "
                    f"queue={queue_size}, quiet countdown={quiet_remaining:>3}s",
                    end="",
                    flush=True
                )
            else:
                remaining_total = total_timeout_seconds - elapsed
                print(
                    f"\rWaiting first bot media/message... "
                    f"queue={queue_size}, total timeout in={remaining_total:>3}s",
                    end="",
                    flush=True
                )

    print("\r" + " " * 120 + "\r", end="", flush=True)

    # Asegurar que no quedan mensajes sin procesar.
    pending_queue = message_queue.qsize()
    if pending_queue > 0:
        print(f"Warning: {pending_queue} messages still in queue. Processing before disconnect...")

    while not message_queue.empty():
        message = await message_queue.get()
        describe_message(message)

        if message.media:
            result = await download_message_media(
                client=client,
                message=message,
                download_folder=download_folder,
                temp_folder=temp_folder,
                downloaded_hashes=downloaded_hashes,
                processed_media_ids=processed_media_ids,
            )
            download_results.append(result)

        message_queue.task_done()

    print("")
    print("POC finished.")
    print("")

    ok_results = [r for r in download_results if r.file_path and not r.duplicated and not r.error]
    duplicated_results = [r for r in download_results if r.duplicated]
    skipped_results = [r for r in download_results if r.skipped]
    error_results = [r for r in download_results if r.error]

    print("========== SUMMARY ==========")
    print(f"Downloaded unique files: {len(ok_results)}")
    print(f"Duplicated files ignored: {len(duplicated_results)}")
    print(f"Skipped media ids: {len(skipped_results)}")
    print(f"Download errors: {len(error_results)}")
    print("=============================")

    print("")
    print("Downloaded files:")
    for result in ok_results:
        print(f"- message_id={result.message_id}")
        print(f"  telegram_media_id={result.telegram_media_id}")
        print(f"  path={result.file_path}")
        print(f"  size={result.file_size}")
        print(f"  sha256={result.file_hash}")

    if duplicated_results:
        print("")
        print("Duplicated ignored:")
        for result in duplicated_results:
            print(f"- message_id={result.message_id}")
            print(f"  telegram_media_id={result.telegram_media_id}")
            print(f"  matched_path={result.file_path}")
            print(f"  size={result.file_size}")
            print(f"  sha256={result.file_hash}")

    if error_results:
        print("")
        print("Errors:")
        for result in error_results:
            print(f"- message_id={result.message_id}")
            print(f"  telegram_media_id={result.telegram_media_id}")
            print(f"  error={result.error}")

    try:
        if temp_folder.exists() and not any(temp_folder.iterdir()):
            temp_folder.rmdir()
    except Exception:
        pass

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())