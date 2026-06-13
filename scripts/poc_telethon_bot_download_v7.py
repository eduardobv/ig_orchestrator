import asyncio
import hashlib
import os
import re
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


WINDOWS_INVALID_FILENAME_CHARS = r'<>:"/\|?*'


@dataclass
class DownloadResult:
    message_id: int
    telegram_media_id: Optional[str]
    original_file_name: Optional[str]
    file_path: Optional[Path]
    temp_path: Optional[Path]
    file_hash: Optional[str]
    file_size: Optional[int]
    duplicated: bool
    skipped: bool
    provisional: bool
    error: Optional[str]


@dataclass
class AttemptResult:
    attempt_number: int
    success: bool
    retryable: bool
    reason: str
    downloaded_count: int
    duplicated_count: int
    error_text: Optional[str]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_retry_delays() -> list[int]:
    raw_value = os.getenv("POC_RETRY_DELAYS_SECONDS", "5,10,15")
    delays = []

    for item in raw_value.split(","):
        item = item.strip()
        if item:
            delays.append(int(item))

    return delays


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


def sanitize_windows_filename(file_name: str) -> str:
    clean_name = file_name.strip()

    for char in WINDOWS_INVALID_FILENAME_CHARS:
        clean_name = clean_name.replace(char, "_")

    clean_name = re.sub(r"[\r\n\t]", "_", clean_name)
    clean_name = clean_name.rstrip(" .")

    if not clean_name:
        clean_name = "telegram_media"

    return clean_name


def get_original_file_name_from_message(message) -> Optional[str]:
    document = getattr(message, "document", None)

    if not document:
        return None

    for attribute in getattr(document, "attributes", []) or []:
        file_name = getattr(attribute, "file_name", None)
        if file_name:
            return sanitize_windows_filename(file_name)

    return None


def get_file_extension_from_message(message) -> str:
    original_file_name = get_original_file_name_from_message(message)

    if original_file_name:
        extension = Path(original_file_name).suffix.lower()
        if extension:
            return extension

    document = getattr(message, "document", None)

    if document:
        mime_type = getattr(document, "mime_type", "") or ""

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


def get_preferred_final_file_name(message) -> str:
    original_file_name = get_original_file_name_from_message(message)

    if original_file_name:
        return original_file_name

    extension = get_file_extension_from_message(message)
    return f"{message.id}{extension}"


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
    print(f"original_file_name: {get_original_file_name_from_message(message)}")
    print(f"preferred_final_file_name: {get_preferred_final_file_name(message) if message.media else '<none>'}")

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


def unique_final_path(download_folder: Path, preferred_name: str) -> Path:
    preferred_name = sanitize_windows_filename(preferred_name)
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


async def sleep_with_countdown(seconds: int, reason: str) -> None:
    for remaining in range(seconds, 0, -1):
        print(f"\rRetry sleep {remaining:>3}s - {reason}", end="", flush=True)
        await asyncio.sleep(1)

    print("\r" + " " * 120 + "\r", end="", flush=True)


async def download_message_media(
    client: TelegramClient,
    message,
    download_folder: Path,
    temp_folder: Path,
    provisional_folder: Path,
    downloaded_hashes: dict[str, Path],
    processed_media_ids: set[str],
) -> DownloadResult:
    message_id = message.id
    telegram_media_id = get_telegram_media_id(message)
    original_file_name = get_original_file_name_from_message(message)
    preferred_final_file_name = get_preferred_final_file_name(message)
    has_original_file_name = bool(original_file_name)

    print("")
    print("========== DOWNLOAD START ==========")
    print(f"message_id: {message_id}")
    print(f"telegram_media_id: {telegram_media_id}")
    print(f"original_file_name: {original_file_name}")
    print(f"preferred_final_file_name: {preferred_final_file_name}")
    print(f"has_original_file_name: {has_original_file_name}")

    if telegram_media_id and telegram_media_id in processed_media_ids:
        print("Result: skipped, Telegram media id already processed.")
        print("====================================")
        return DownloadResult(
            message_id=message_id,
            telegram_media_id=telegram_media_id,
            original_file_name=original_file_name,
            file_path=None,
            temp_path=None,
            file_hash=None,
            file_size=None,
            duplicated=False,
            skipped=True,
            provisional=False,
            error=None,
        )

    if telegram_media_id:
        processed_media_ids.add(telegram_media_id)

    extension = get_file_extension_from_message(message)

    if has_original_file_name:
        temp_file = temp_folder / f"msg_{message_id}{extension}"
    else:
        temp_file = provisional_folder / f"msg_{message_id}{extension}"

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
            print("Deleting duplicate temp/provisional file.")

            downloaded_temp_path.unlink(missing_ok=True)

            print("========== DOWNLOAD END: DUPLICATED ==========")

            return DownloadResult(
                message_id=message_id,
                telegram_media_id=telegram_media_id,
                original_file_name=original_file_name,
                file_path=original_file,
                temp_path=None,
                file_hash=file_hash,
                file_size=file_size,
                duplicated=True,
                skipped=False,
                provisional=False,
                error=None,
            )

        # Cambio clave v7:
        # Si NO trae nombre original, se queda provisional y NO se mueve a Telegram Desktop.
        if not has_original_file_name:
            print("")
            print("Media has no original filename.")
            print("Keeping it as provisional. It will not be visible in the main download folder.")
            print(f"Provisional path: {downloaded_temp_path}")
            print("========== DOWNLOAD END: PROVISIONAL ==========")

            return DownloadResult(
                message_id=message_id,
                telegram_media_id=telegram_media_id,
                original_file_name=original_file_name,
                file_path=None,
                temp_path=downloaded_temp_path,
                file_hash=file_hash,
                file_size=file_size,
                duplicated=False,
                skipped=False,
                provisional=True,
                error=None,
            )

        final_path = unique_final_path(download_folder, preferred_final_file_name)

        print(f"Final target path: {final_path}")

        shutil.move(str(downloaded_temp_path), str(final_path))

        downloaded_hashes[file_hash] = final_path

        print(f"Moved temp file to final path: {final_path}")
        print("========== DOWNLOAD END: OK ==========")

        return DownloadResult(
            message_id=message_id,
            telegram_media_id=telegram_media_id,
            original_file_name=original_file_name,
            file_path=final_path,
            temp_path=None,
            file_hash=file_hash,
            file_size=file_size,
            duplicated=False,
            skipped=False,
            provisional=False,
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
            original_file_name=original_file_name,
            file_path=None,
            temp_path=None,
            file_hash=None,
            file_size=None,
            duplicated=False,
            skipped=False,
            provisional=False,
            error=repr(exc),
        )


async def drain_queue(message_queue: asyncio.Queue) -> None:
    while not message_queue.empty():
        try:
            message_queue.get_nowait()
            message_queue.task_done()
        except asyncio.QueueEmpty:
            break


def cleanup_or_promote_provisional_files(
    download_results: list[DownloadResult],
    download_folder: Path,
    downloaded_hashes: dict[str, Path],
) -> None:
    """
    v7:
    - Si hay archivos finales con nombre original, eliminamos los provisionales.
    - Si NO hay ningún archivo final, promovemos los provisionales a la carpeta final
      usando fallback message_id.ext.
    """
    final_results = [
        result for result in download_results
        if result.file_path and not result.duplicated and not result.error and not result.provisional
    ]

    provisional_results = [
        result for result in download_results
        if result.provisional and result.temp_path and result.temp_path.exists()
    ]

    if not provisional_results:
        print("")
        print("No provisional files to clean.")
        return

    print("")
    print("========== PROVISIONAL CLEANUP ==========")
    print(f"final_files_with_original_name: {len(final_results)}")
    print(f"provisional_files: {len(provisional_results)}")

    if final_results:
        print("Final files exist. Deleting provisional files without original filename.")

        for result in provisional_results:
            print(f"Deleting provisional: {result.temp_path}")
            result.temp_path.unlink(missing_ok=True)

        print("========== PROVISIONAL CLEANUP END ==========")
        return

    print("No final files with original filename exist.")
    print("Promoting provisional files to final folder using message_id fallback names.")

    for result in provisional_results:
        if not result.temp_path or not result.temp_path.exists():
            continue

        suffix = result.temp_path.suffix or ".bin"
        fallback_name = f"{result.message_id}{suffix}"
        final_path = unique_final_path(download_folder, fallback_name)

        print(f"Promoting provisional: {result.temp_path}")
        print(f"Final path: {final_path}")

        shutil.move(str(result.temp_path), str(final_path))

        result.file_path = final_path
        result.temp_path = None
        result.provisional = False

        if result.file_hash:
            downloaded_hashes[result.file_hash] = final_path

    print("========== PROVISIONAL CLEANUP END ==========")


async def process_single_attempt(
    *,
    attempt_number: int,
    max_attempts: int,
    client: TelegramClient,
    bot,
    instagram_url: str,
    message_queue: asyncio.Queue,
    download_folder: Path,
    temp_folder: Path,
    provisional_folder: Path,
    downloaded_hashes: dict[str, Path],
    processed_media_ids: set[str],
    download_results: list[DownloadResult],
    total_timeout_seconds: int,
    quiet_seconds_after_last_message: int,
) -> AttemptResult:
    await drain_queue(message_queue)

    attempt_start_time = datetime.now(timezone.utc)
    attempt_started_loop_time = asyncio.get_event_loop().time()
    last_bot_message_time = attempt_started_loop_time

    first_media_downloaded = False
    attempt_downloaded_count = 0
    attempt_duplicated_count = 0

    print("")
    print("############################################################")
    print(f"ATTEMPT {attempt_number}/{max_attempts}")
    print("############################################################")
    print("Sending URL to bot:")
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
        elapsed = int(now - attempt_started_loop_time)

        if elapsed >= total_timeout_seconds:
            print("")
            print(f"Attempt timeout reached: {total_timeout_seconds}s.")

            return AttemptResult(
                attempt_number=attempt_number,
                success=first_media_downloaded,
                retryable=not first_media_downloaded,
                reason="TIMEOUT",
                downloaded_count=attempt_downloaded_count,
                duplicated_count=attempt_duplicated_count,
                error_text="Timeout waiting for bot response/media",
            )

        try:
            message = await asyncio.wait_for(message_queue.get(), timeout=1)

            message_date = message.date
            if message_date and message_date.tzinfo is None:
                message_date = message_date.replace(tzinfo=timezone.utc)

            if message_date and message_date < attempt_start_time:
                print(f"Skipping message from previous attempt: id={message.id}")
                message_queue.task_done()
                continue

            last_bot_message_time = asyncio.get_event_loop().time()

            describe_message(message)

            text = (message.raw_text or "").lower()

            matched_error = None
            for known_error in KNOWN_ERRORS:
                if known_error in text:
                    matched_error = known_error
                    break

            if matched_error:
                print("")
                print("Known bot error detected.")
                print(f"matched_error: {matched_error}")
                print(f"bot_text: {message.raw_text}")

                message_queue.task_done()

                if first_media_downloaded:
                    print("Error arrived after media was already downloaded. Treating attempt as success.")
                    return AttemptResult(
                        attempt_number=attempt_number,
                        success=True,
                        retryable=False,
                        reason="SUCCESS_WITH_LATE_ERROR",
                        downloaded_count=attempt_downloaded_count,
                        duplicated_count=attempt_duplicated_count,
                        error_text=message.raw_text,
                    )

                return AttemptResult(
                    attempt_number=attempt_number,
                    success=False,
                    retryable=True,
                    reason="KNOWN_RETRYABLE_BOT_ERROR",
                    downloaded_count=attempt_downloaded_count,
                    duplicated_count=attempt_duplicated_count,
                    error_text=message.raw_text,
                )

            if message.media:
                result = await download_message_media(
                    client=client,
                    message=message,
                    download_folder=download_folder,
                    temp_folder=temp_folder,
                    provisional_folder=provisional_folder,
                    downloaded_hashes=downloaded_hashes,
                    processed_media_ids=processed_media_ids,
                )

                download_results.append(result)

                if (
                    (result.file_path or result.temp_path)
                    and not result.duplicated
                    and not result.error
                ):
                    first_media_downloaded = True
                    attempt_downloaded_count += 1

                if result.duplicated:
                    attempt_duplicated_count += 1

                if result.error and not first_media_downloaded:
                    message_queue.task_done()

                    return AttemptResult(
                        attempt_number=attempt_number,
                        success=False,
                        retryable=True,
                        reason="DOWNLOAD_ERROR",
                        downloaded_count=attempt_downloaded_count,
                        duplicated_count=attempt_duplicated_count,
                        error_text=result.error,
                    )

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
                        f"and queue is empty. Attempt finished successfully."
                    )

                    return AttemptResult(
                        attempt_number=attempt_number,
                        success=True,
                        retryable=False,
                        reason="SUCCESS",
                        downloaded_count=attempt_downloaded_count,
                        duplicated_count=attempt_duplicated_count,
                        error_text=None,
                    )

                print(
                    f"\rWaiting for extra bot media... "
                    f"attempt={attempt_number}/{max_attempts}, "
                    f"queue={queue_size}, quiet countdown={quiet_remaining:>3}s",
                    end="",
                    flush=True
                )
            else:
                remaining_total = total_timeout_seconds - elapsed
                print(
                    f"\rWaiting first bot media/message... "
                    f"attempt={attempt_number}/{max_attempts}, "
                    f"queue={queue_size}, total timeout in={remaining_total:>3}s",
                    end="",
                    flush=True
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
    provisional_folder = temp_folder / "_provisional_no_original_name"

    temp_folder.mkdir(parents=True, exist_ok=True)
    provisional_folder.mkdir(parents=True, exist_ok=True)

    total_timeout_seconds = int(os.getenv("POC_TOTAL_TIMEOUT_SECONDS", "180"))
    quiet_seconds_after_last_message = int(os.getenv("POC_QUIET_SECONDS_AFTER_FIRST_DOWNLOAD", "20"))
    retry_delays_seconds = parse_retry_delays()

    max_attempts = 1 + len(retry_delays_seconds)

    client = TelegramClient(session_name, api_id, api_hash)
    await ensure_login(client)

    me = await client.get_me()
    print(f"Logged in as: {me.username or me.first_name} / id={me.id}")

    bot = await client.get_entity(bot_username)

    message_queue: asyncio.Queue = asyncio.Queue()
    processed_message_ids: set[int] = set()
    processed_media_ids: set[str] = set()
    downloaded_hashes: dict[str, Path] = {}
    download_results: list[DownloadResult] = []
    attempt_results: list[AttemptResult] = []

    @client.on(events.NewMessage(chats=bot))
    async def handler(event):
        message = event.message

        if message.id in processed_message_ids:
            print(f"Skipping already queued message id={message.id}")
            return

        processed_message_ids.add(message.id)

        print("")
        print(f"[QUEUE] New bot message queued: id={message.id}, has_media={bool(message.media)}")

        await message_queue.put(message)

    try:
        final_attempt_result: Optional[AttemptResult] = None

        for index in range(max_attempts):
            attempt_number = index + 1

            attempt_result = await process_single_attempt(
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                client=client,
                bot=bot,
                instagram_url=instagram_url,
                message_queue=message_queue,
                download_folder=download_folder,
                temp_folder=temp_folder,
                provisional_folder=provisional_folder,
                downloaded_hashes=downloaded_hashes,
                processed_media_ids=processed_media_ids,
                download_results=download_results,
                total_timeout_seconds=total_timeout_seconds,
                quiet_seconds_after_last_message=quiet_seconds_after_last_message,
            )

            attempt_results.append(attempt_result)
            final_attempt_result = attempt_result

            print("")
            print("========== ATTEMPT RESULT ==========")
            print(f"attempt: {attempt_result.attempt_number}/{max_attempts}")
            print(f"success: {attempt_result.success}")
            print(f"retryable: {attempt_result.retryable}")
            print(f"reason: {attempt_result.reason}")
            print(f"downloaded_count: {attempt_result.downloaded_count}")
            print(f"duplicated_count: {attempt_result.duplicated_count}")
            print(f"error_text: {attempt_result.error_text}")
            print("====================================")

            if attempt_result.success:
                print("")
                print("URL processed successfully. No more retries needed.")
                break

            if not attempt_result.retryable:
                print("")
                print("Error is not retryable. Stopping.")
                break

            if index >= len(retry_delays_seconds):
                print("")
                print("No retry delays left. Stopping.")
                break

            delay_seconds = retry_delays_seconds[index]

            print("")
            print(f"Retryable error detected. Retrying in {delay_seconds}s...")
            await sleep_with_countdown(
                delay_seconds,
                reason=f"before attempt {attempt_number + 1}/{max_attempts}"
            )

        print("\r" + " " * 120 + "\r", end="", flush=True)

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
                    provisional_folder=provisional_folder,
                    downloaded_hashes=downloaded_hashes,
                    processed_media_ids=processed_media_ids,
                )
                download_results.append(result)

            message_queue.task_done()

        cleanup_or_promote_provisional_files(
            download_results=download_results,
            download_folder=download_folder,
            downloaded_hashes=downloaded_hashes,
        )

        print("")
        print("POC finished.")
        print("")

        ok_results = [r for r in download_results if r.file_path and not r.duplicated and not r.error]
        duplicated_results = [r for r in download_results if r.duplicated]
        skipped_results = [r for r in download_results if r.skipped]
        provisional_results = [r for r in download_results if r.provisional]
        error_results = [r for r in download_results if r.error]

        print("========== FINAL RESULT ==========")
        if final_attempt_result:
            print(f"final_success: {final_attempt_result.success}")
            print(f"final_reason: {final_attempt_result.reason}")
            print(f"final_error_text: {final_attempt_result.error_text}")
        else:
            print("final_success: False")
            print("final_reason: NO_ATTEMPT_EXECUTED")
        print("==================================")

        print("")
        print("========== ATTEMPTS ==========")
        for result in attempt_results:
            print(
                f"- attempt={result.attempt_number}, "
                f"success={result.success}, "
                f"retryable={result.retryable}, "
                f"reason={result.reason}, "
                f"downloads={result.downloaded_count}, "
                f"duplicates={result.duplicated_count}, "
                f"error={result.error_text}"
            )
        print("==============================")

        print("")
        print("========== DOWNLOAD SUMMARY ==========")
        print(f"Downloaded unique final files: {len(ok_results)}")
        print(f"Duplicated files ignored: {len(duplicated_results)}")
        print(f"Skipped media ids: {len(skipped_results)}")
        print(f"Provisional files handled: {len(provisional_results)}")
        print(f"Download errors: {len(error_results)}")
        print("======================================")

        print("")
        print("Downloaded files:")
        for result in ok_results:
            print(f"- message_id={result.message_id}")
            print(f"  telegram_media_id={result.telegram_media_id}")
            print(f"  original_file_name={result.original_file_name}")
            print(f"  path={result.file_path}")
            print(f"  size={result.file_size}")
            print(f"  sha256={result.file_hash}")

        if duplicated_results:
            print("")
            print("Duplicated ignored:")
            for result in duplicated_results:
                print(f"- message_id={result.message_id}")
                print(f"  telegram_media_id={result.telegram_media_id}")
                print(f"  original_file_name={result.original_file_name}")
                print(f"  matched_path={result.file_path}")
                print(f"  size={result.file_size}")
                print(f"  sha256={result.file_hash}")

        if error_results:
            print("")
            print("Errors:")
            for result in error_results:
                print(f"- message_id={result.message_id}")
                print(f"  telegram_media_id={result.telegram_media_id}")
                print(f"  original_file_name={result.original_file_name}")
                print(f"  error={result.error}")

        try:
            if provisional_folder.exists() and not any(provisional_folder.iterdir()):
                provisional_folder.rmdir()

            if temp_folder.exists() and not any(temp_folder.iterdir()):
                temp_folder.rmdir()
        except Exception:
            pass

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())