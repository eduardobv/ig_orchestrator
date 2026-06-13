import asyncio
import hashlib
import os
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


def print_message(message) -> None:
    print("")
    print("========== BOT MESSAGE ==========")
    print(f"id: {message.id}")
    print(f"date: {message.date}")
    print(f"has_media: {bool(message.media)}")
    print("text:")
    print(message.raw_text or "<empty>")
    print("=================================")


def sha256_file(path: Path) -> str:
    hash_obj = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


def get_telegram_media_id(message) -> Optional[str]:
    """
    Intenta obtener un identificador estable del media de Telegram.
    No siempre será suficiente para detectar duplicados, por eso también usamos SHA-256.
    """
    media = getattr(message, "media", None)

    if not media:
        return None

    document = getattr(message, "document", None)
    if document:
        return f"document:{document.id}"

    photo = getattr(message, "photo", None)
    if photo:
        return f"photo:{photo.id}"

    return None


async def sleep_countdown(seconds: int, reason: str) -> None:
    for remaining in range(seconds, 0, -1):
        print(f"\rSleeping {remaining:>3}s - {reason}", end="", flush=True)
        await asyncio.sleep(1)

    print("\r" + " " * 80 + "\r", end="", flush=True)


async def main() -> None:
    load_dotenv()

    api_id = int(require_env("TELEGRAM_API_ID"))
    api_hash = require_env("TELEGRAM_API_HASH")
    session_name = os.getenv("TELETHON_SESSION_NAME", "telegram_user_session")

    bot_username = require_env("TELEGRAM_DOWNLOAD_BOT_USERNAME")
    instagram_url = require_env("POC_INSTAGRAM_URL")

    download_folder = Path(require_env("POC_DOWNLOAD_FOLDER"))
    download_folder.mkdir(parents=True, exist_ok=True)

    total_timeout_seconds = int(os.getenv("POC_TOTAL_TIMEOUT_SECONDS", "180"))
    quiet_seconds_after_first_download = int(os.getenv("POC_QUIET_SECONDS_AFTER_FIRST_DOWNLOAD", "20"))

    client = TelegramClient(session_name, api_id, api_hash)
    await ensure_login(client)

    me = await client.get_me()
    print(f"Logged in as: {me.username or me.first_name} / id={me.id}")

    bot = await client.get_entity(bot_username)

    start_time = datetime.now(timezone.utc)

    downloaded_files: list[Path] = []
    downloaded_hashes: dict[str, Path] = {}
    processed_message_ids: set[int] = set()
    processed_media_ids: set[str] = set()

    first_download_done = asyncio.Event()
    stop_event = asyncio.Event()

    last_activity_timestamp = asyncio.get_event_loop().time()

    download_lock = asyncio.Lock()

    @client.on(events.NewMessage(chats=bot))
    async def handler(event):
        nonlocal last_activity_timestamp

        message = event.message

        if message.id in processed_message_ids:
            print(f"Skipping already processed message id={message.id}")
            return

        processed_message_ids.add(message.id)

        message_date = message.date
        if message_date and message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)

        # Ignorar mensajes antiguos.
        if message_date and message_date < start_time:
            return

        last_activity_timestamp = asyncio.get_event_loop().time()

        print_message(message)

        text = (message.raw_text or "").lower()

        if any(error in text for error in KNOWN_ERRORS):
            print("Known bot error detected:")
            print(message.raw_text)
            stop_event.set()
            return

        if not message.media:
            return

        media_id = get_telegram_media_id(message)

        if media_id and media_id in processed_media_ids:
            print(f"Skipping duplicated Telegram media id: {media_id}")
            return

        if media_id:
            processed_media_ids.add(media_id)

        async with download_lock:
            try:
                print("Media detected. Downloading with Telethon...")
                downloaded_path_raw = await client.download_media(
                    message,
                    file=str(download_folder)
                )

                if not downloaded_path_raw:
                    print("Media was present, but Telethon did not return a file path.")
                    return

                downloaded_path = Path(downloaded_path_raw)
                file_hash = sha256_file(downloaded_path)

                if file_hash in downloaded_hashes:
                    original_file = downloaded_hashes[file_hash]
                    print("")
                    print("Duplicated file detected by SHA-256.")
                    print(f"Original:  {original_file}")
                    print(f"Duplicate: {downloaded_path}")
                    print("Deleting duplicate downloaded file.")

                    downloaded_path.unlink(missing_ok=True)
                    return

                downloaded_hashes[file_hash] = downloaded_path
                downloaded_files.append(downloaded_path)

                print(f"Downloaded by Telethon: {downloaded_path}")
                print(f"SHA-256: {file_hash}")

                first_download_done.set()

            except Exception as exc:
                print("")
                print("Error downloading media:")
                print(repr(exc))
                stop_event.set()

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

    started_waiting = asyncio.get_event_loop().time()

    while True:
        now = asyncio.get_event_loop().time()
        elapsed = int(now - started_waiting)

        if stop_event.is_set():
            print("Stop event received. Finishing.")
            break

        if elapsed >= total_timeout_seconds:
            print(f"Total timeout reached: {total_timeout_seconds}s.")
            break

        if first_download_done.is_set():
            seconds_since_last_activity = int(now - last_activity_timestamp)

            if seconds_since_last_activity >= quiet_seconds_after_first_download:
                print(
                    f"No new bot messages for {quiet_seconds_after_first_download}s "
                    f"after first download. Finishing."
                )
                break

            remaining_quiet = quiet_seconds_after_first_download - seconds_since_last_activity
            print(
                f"\rWaiting for possible extra media... "
                f"quiet countdown: {remaining_quiet:>3}s",
                end="",
                flush=True
            )
        else:
            remaining_total = total_timeout_seconds - elapsed
            print(
                f"\rWaiting first bot media/message... "
                f"total timeout in: {remaining_total:>3}s",
                end="",
                flush=True
            )

        await asyncio.sleep(1)

    print("\r" + " " * 100 + "\r", end="", flush=True)

    print("")
    print("POC finished.")
    print(f"Downloaded unique files: {len(downloaded_files)}")

    for file_path in downloaded_files:
        print(f"- {file_path}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())